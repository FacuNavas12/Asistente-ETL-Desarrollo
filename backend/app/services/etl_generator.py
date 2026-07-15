"""
RF5 — Interpretar relaciones entre capas (origen → staging → DWH)
RF6 — Generar proceso ETL completo
RF7 — Sugerir steps concretos de Pentaho PDI
RF14 — Sugerir visualizaciones para Apache Superset
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal, Optional

_log = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from app.models.llm_base import BaseLLM, LLMResponse
from app.schemas.etl_schemas import ETLRequest, ETLFromInferenceRequest, ETLGenerateResponse, MetadataResponse, Validacion
from app.schemas.llm_output_schemas import ETL_OUTPUT_SCHEMA
from app.services import context_builder
from app.services.adapters.ddl_adapter import parse_ddl
from app.services.ktr_builder import build_ktr, repair_integrity_gaps, repair_ktr_steps
from app.services.ktr_builder.build import _sanitize
from app.services.ktr_builder.fields_validate import FIELD_INTEGRITY_PREFIX
from app.services.lineage_builder import build_lineage, stitch_lineage


def _split_integrity_warnings(warnings: list[str]) -> tuple[list[str], list[Validacion]]:
    """Separa las advertencias de integridad de campos (ver FIELD_INTEGRITY_PREFIX
    en fields_validate.py) del resto de warnings cosméticos. Las de integridad
    se promueven a Validacion tipo="error" — la severidad más alta que
    EtlDetail sabe renderizar — en vez de perderse entre las buenas prácticas."""
    plain: list[str] = []
    integridad: list[Validacion] = []
    for w in warnings:
        if w.startswith(FIELD_INTEGRITY_PREFIX):
            integridad.append(Validacion(
                tipo="error",
                campo="integridad_campos",
                mensaje=w[len(FIELD_INTEGRITY_PREFIX):],
            ))
        else:
            plain.append(w)
    return plain, integridad


def _required_columns_from_ddl(*ddls: str) -> dict[str, list[str]]:
    """Parsea DDL(s) de staging/DWH y devuelve {tabla: [columnas NOT NULL sin
    default]} — insumo del validador de campos obligatorios en build_ktr().
    Best-effort: un DDL no parseable solo se loggea, nunca corta el flujo."""
    result: dict[str, list[str]] = {}
    for ddl in ddls:
        if not ddl or not ddl.strip():
            continue
        try:
            schemas = parse_ddl(ddl, dialect=None)
        except Exception as exc:
            _log.warning("No se pudo parsear DDL para chequeo de campos obligatorios: %s", exc)
            continue
        for schema in schemas:
            cols = [
                f.name for f in schema.fields
                if f.constraints.required and f.default_kind is None
            ]
            if cols:
                result[schema.source_name] = cols
    return result


def _column_types_from_ddl(ddl: str) -> dict[str, str]:
    """{columna_lower: CanonicalType.value} agregando todas las tablas del DDL
    (best-effort: DDL no parseable -> {}, solo loggeado). Cuando el mismo
    nombre de columna aparece en más de una tabla con tipos distintos, se
    queda con el primero — heurística de nombre, no resuelve ambigüedad real.
    Insumo de _type_mismatch_warnings()."""
    result: dict[str, str] = {}
    if not ddl or not ddl.strip():
        return result
    try:
        schemas = parse_ddl(ddl, dialect=None)
    except Exception as exc:
        _log.warning("No se pudo parsear DDL para chequeo de tipos: %s", exc)
        return result
    for schema in schemas:
        for f in schema.fields:
            result.setdefault(f.name.lower(), f.type.value)
    return result


# Pares de familia de tipo considerados de riesgo real de incompatibilidad
# (comparación/insert silenciosamente incorrecto) si una columna del mismo
# nombre cruza de una familia a otra entre staging y DWH sin cast explícito.
_RISKY_TYPE_PAIRS = {
    frozenset({"string", "integer"}),
    frozenset({"string", "number"}),
    frozenset({"string", "boolean"}),
}


def _type_mismatch_warnings(stg_ddl: str, dwh_ddl: str, ktr_data: dict) -> list[str]:
    """Heurística best-effort, NO bloqueante: columnas que aparecen en STAGING
    y en DWH con el mismo NOMBRE pero familia de tipo incompatible (string vs
    integer/number/boolean), y para las que ningún `SelectValues` del ktr
    declara un `cast` explícito — señal de que falta castear antes de usar la
    columna en un lookup/join/insert (caso del diagnóstico: cod_sucursal
    string en origen/staging vs INTEGER en la dimensión). Solo compara nombre
    + familia de tipo entre los DDL de staging/DWH ya parseados por el
    caller — no tiene visibilidad de tipos de origen, así que no detecta
    incoherencias que ya existan entre origen y staging."""
    stg_types = _column_types_from_ddl(stg_ddl)
    dwh_types = _column_types_from_ddl(dwh_ddl)
    if not stg_types or not dwh_types:
        return []

    casted: set[str] = set()
    for step in ktr_data.get("steps", []):
        if step.get("type") not in ("SelectValues", "Select values"):
            continue
        cfg = step.get("config", {})
        if not isinstance(cfg, dict):
            continue
        for c in cfg.get("cast", []) or []:
            if isinstance(c, dict) and c.get("name"):
                casted.add(str(c["name"]).lower())

    warnings: list[str] = []
    for col, stg_type in stg_types.items():
        dwh_type = dwh_types.get(col)
        if not dwh_type or dwh_type == stg_type or col in casted:
            continue
        if frozenset({stg_type, dwh_type}) not in _RISKY_TYPE_PAIRS:
            continue
        warnings.append(
            f"Posible incoherencia de tipos: columna '{col}' es {stg_type} en staging pero "
            f"{dwh_type} en DWH — verificar un cast explícito (SelectValues > cast) antes de "
            "usarla en un lookup, join o insert. Sin el cast, PDI puede fallar o comparar "
            "valores de tipos distintos de forma silenciosa."
        )
    return warnings


def _staging_table_names_from_ddl(stg_ddl: str) -> list[str]:
    """Parsea el DDL de staging y devuelve los nombres de tabla declarados (orden
    de aparición, sin duplicados). Best-effort: DDL no parseable → lista vacía,
    solo loggeado — nunca corta el flujo. Insumo para fijar los mismos nombres
    de tabla STG en ambas llamadas al modelo del flujo de 2 KTR (origen→STG y
    STG→DWH) y para costurar el linaje entre ambos archivos."""
    if not stg_ddl or not stg_ddl.strip():
        return []
    try:
        schemas = parse_ddl(stg_ddl, dialect=None)
    except Exception as exc:
        _log.warning("No se pudo parsear DDL de staging para extraer nombres de tabla: %s", exc)
        return []
    return [schema.source_name for schema in schemas]


def _build_job_plan(ktr1_filename: str, ktr2_filename: str, process_name: str) -> "JobPlan":
    """Arma el JobPlan del .kjb orquestador del flujo de 2 KTR en Python puro —
    el orden STG-antes-que-DWH es siempre fijo, no hay ambigüedad que amerite
    una llamada al modelo (a diferencia del flujo CreateJob, que sí la usa
    porque orquesta .ktr arbitrarios subidos por el usuario). Reutiliza
    build_kjb_xml() de job_analyzer.py sin modificarlo."""
    from app.schemas.job_schemas import JobEntry, JobPlan

    name = process_name or "Proceso_ETL"
    return JobPlan(
        job_name=f"{name}_job",
        description=f"Orquesta {name}: origen→STAGING (KTR_1) y STAGING→DWH (KTR_2) en secuencia.",
        overall_rationale=(
            "Job generado por el flujo de 2 KTR: orden fijo STG-antes-que-DWH, "
            "sin ambigüedad de secuencia — no requiere razonamiento del modelo."
        ),
        execution_order=[
            JobEntry(order=1, transformation_name="KTR_1_origen_stg", filename=ktr1_filename,
                      rationale="Carga origen → STAGING. Debe completar antes de KTR_2."),
            JobEntry(order=2, transformation_name="KTR_2_stg_dwh", filename=ktr2_filename,
                      rationale="Carga STAGING → DWH. Corre solo si KTR_1 finalizó."),
        ],
    )


class KtrBuildError(Exception):
    """El modelo respondió correctamente pero build_ktr() falló al serializar el XML.
    Conserva raw_data (el JSON crudo del modelo) para que el caller no lo pierda."""
    def __init__(self, raw_data: dict, original_error: Exception):
        self.raw_data = raw_data
        self.original_error = original_error
        super().__init__(str(original_error))


def _load_system(filename: str) -> str:
    return (Path(__file__).resolve().parent.parent.parent / "prompts" / filename).read_text(encoding="utf-8")


def _build_prompt(req: ETLRequest, origen_txt: str) -> str:
    staging_txt = ""
    for t in req.stagingDef:
        origen_ref = f" (origen: {t.origenVinculado})" if t.origenVinculado else ""
        cols = "\n".join(
            (
                f"    - {c.origenColumna} → {c.nombre} ({c.tipo})"
                if c.origenColumna and c.origenColumna != c.nombre
                else f"    - {c.nombre} ({c.tipo})"
            ) + (f" | reglas: {', '.join(c.reglas)}" if c.reglas else "")
            + f" | dato no válido: {c.datoNoValido}"
            for c in t.columns
        )
        staging_txt += f"\n  Tabla: {t.tableName}{origen_ref}\n{cols}\n"

    dwh_txt = ""
    for t in req.dwhModel.tables:
        origen_ref = f" | origen: {t.origenVinculado}" if t.origenVinculado else ""
        cols = "\n".join(
            (
                f"    - {c.origenColumna} → {c.nombre} ({c.tipo}){' [SK]' if c.esSurrogateKey else ''}"
                if c.origenColumna and c.origenColumna != c.nombre
                else f"    - {c.nombre} ({c.tipo}){' [SK]' if c.esSurrogateKey else ''}"
            )
            for c in t.columnas
        )
        dwh_txt += f"\n  Tabla {t.tipo}: {t.nombre}{origen_ref}\n{cols}\n"

    reglas  = req.reglasNegocio.strip() or "No se especificaron reglas de negocio adicionales."
    objetivo = req.descripcionObjetivo.strip() or "No especificado."

    return f"""## OBJETIVO DEL PROCESO ETL
{objetivo}

## ESQUEMA DE ORIGEN (perfilado — sin datos crudos)
{origen_txt}
## ESQUEMA DE STAGING
{staging_txt}
## MODELO DE DWH
{dwh_txt}
## REGLAS DE NEGOCIO

{reglas}

---

Genera el proceso ETL completo respetando estrictamente el objetivo indicado.
El mapeo "origen → nombre" indica que el campo se renombra entre capas; respetá los nombres destino exactos.
Aplica todas las reglas de limpieza definidas en cada columna de staging.
Verifica la consistencia de tipos y nombres entre las tres capas.

Antes de escribir el objeto `ktr`, determiná en orden:
**Etapa 1 — Diseño del grafo:** listá mentalmente todos los steps necesarios (nombre, tipo) y sus conexiones (hops) para ESTE proceso específico, sin entrar en configs internas. Verificá grafo completo: ningún step aislado.
**Etapa 2 — Configuración interna:** solo después del grafo completo, poblá el `config` de cada step en orden topológico (entrada → salida).
No mezcles las etapas — configura solo cuando el grafo esté cerrado.
"""


def _build_response_from_data(
    data: dict,
    metadata: MetadataResponse,
    real_connections: dict[str, dict] | None = None,
    connection_warnings: list[str] | None = None,
    required_columns_by_table: dict[str, list[str]] | None = None,
    extra_warnings: list[str] | None = None,
) -> ETLGenerateResponse:
    process_name = data.get("proceso_etl", {}).get("nombre", "")
    ktr_data = data.get("ktr", {})

    # El modelo puede devolver tool_use incompleto (Anthropic no garantiza
    # "required" del schema como OpenAI strict mode) — sobre todo con modelos
    # livianos (Haiku) ante un schema grande. Si falta "ktr" o "proceso_etl",
    # NO hay nada que construir: fallar acá con un mensaje claro en vez de
    # seguir y terminar con build_status=built + ktr_xml vacío (falso positivo).
    missing_keys = [k for k in ("proceso_etl", "ktr") if not data.get(k)]
    if missing_keys:
        raise ValueError(
            f"El modelo devolvió una respuesta incompleta — faltan o están vacías las claves "
            f"{missing_keys} del JSON esperado. Con modelos livianos (ej. Haiku) esto pasa cuando "
            f"el schema de salida es grande para su capacidad — probá con un modelo más grande "
            f"(ANTHROPIC_MODEL) o reintentá."
        )

    # Diagnóstico de causa raíz: mostrar los primeros steps del JSON crudo del modelo
    import json as _json
    _log.info("=== KTR JSON CRUDO (primeros 3 steps) ===")
    for s in ktr_data.get("steps", [])[:3]:
        _log.info("STEP_RAW: %s", _json.dumps(s, ensure_ascii=False))

    # Diagnóstico: loggear config de cada step antes de construir el KTR
    import json as _json2
    for s in ktr_data.get("steps", []):
        raw = s.get("config", {})
        if isinstance(raw, str):
            try:
                cfg = _json2.loads(raw) if raw.strip() else {}
            except Exception:
                cfg = {}
        else:
            cfg = raw or {}
        _log.info(
            "KTR_DIAG step='%s' type='%s' cfg_type=%s table=%r returnfield=%r step1=%r step2=%r cfg_keys=%s",
            s.get("name"), s.get("type"), type(raw).__name__,
            cfg.get("table") or cfg.get("target_table") or cfg.get("table_name"),
            cfg.get("returnfield") or cfg.get("return_field"),
            cfg.get("step1") or cfg.get("reference"),
            cfg.get("step2") or cfg.get("compare"),
            list(cfg.keys()),
        )

    try:
        ktr_xml, ktr_filename, ktr_warnings = build_ktr(
            ktr_data, process_name,
            real_connections=real_connections,
            required_columns_by_table=required_columns_by_table,
        )
    except Exception as e:
        _log.error("build_ktr failed: %s — conservando raw_data para reintento manual", str(e))
        raise KtrBuildError(data, e) from e

    advertencias, integridad_validaciones = _split_integrity_warnings([
        *data.get("advertencias_buenas_practicas", []),
        *(connection_warnings or []),
        *(extra_warnings or []),
        *ktr_warnings,
    ])

    _log.info("dwh_sample keys: %s", list(data.get("dwh_sample", {}).keys()))
    return ETLGenerateResponse(
        proceso_etl=data["proceso_etl"],
        validaciones=[*data.get("validaciones", []), *integridad_validaciones],
        documentacion=data.get("documentacion", ""),
        advertencias_buenas_practicas=advertencias,
        dwh_sample=data.get("dwh_sample", {}),
        ktr_xml=ktr_xml,
        ktr_filename=ktr_filename,
        lineage=build_lineage(ktr_data),
        metadata=metadata,
    )


def _build_response_from_two_ktr_data(
    data_1: dict,
    data_2: dict,
    metadata: MetadataResponse,
    real_connections: dict[str, dict] | None = None,
    connection_warnings: list[str] | None = None,
    required_columns_by_table: dict[str, list[str]] | None = None,
    extra_warnings: list[str] | None = None,
    strict_connections: bool = False,
) -> ETLGenerateResponse:
    """Construye la respuesta del flujo de 2 KTR + 1 .kjb (origen→STG / STG→DWH).
    No reusa _build_response_from_data() porque cada build_ktr() acá necesita
    pass_source_connection/pass_dest_connection (rol de pase) y hay que costurar
    el linaje y armar el .kjb después de tener ambos XML."""
    process_name = (
        data_1.get("proceso_etl", {}).get("nombre", "")
        or data_2.get("proceso_etl", {}).get("nombre", "")
    )

    missing_1 = [k for k in ("proceso_etl", "ktr") if not data_1.get(k)]
    missing_2 = [k for k in ("proceso_etl", "ktr") if not data_2.get(k)]
    if missing_1 or missing_2:
        raise ValueError(
            f"El modelo devolvió una respuesta incompleta — KTR_1 faltan {missing_1 or 'ninguna'}, "
            f"KTR_2 faltan {missing_2 or 'ninguna'}. Con modelos livianos (ej. Haiku) esto pasa cuando "
            f"el schema de salida es grande para su capacidad — probá con un modelo más grande "
            f"(ANTHROPIC_MODEL) o reintentá."
        )

    ktr_data_1 = data_1["ktr"]
    ktr_data_2 = data_2["ktr"]

    try:
        ktr1_xml, ktr1_filename, warnings_1 = build_ktr(
            ktr_data_1, f"{process_name}_origen_stg" if process_name else "KTR_1_origen_stg",
            real_connections=real_connections,
            required_columns_by_table=required_columns_by_table,
            pass_source_connection="conn_origen",
            pass_dest_connection="conn_staging",
            strict_connections=strict_connections,
        )
    except Exception as e:
        _log.error("build_ktr (KTR_1 origen→STG) failed: %s — conservando raw_data para reintento manual", str(e))
        raise KtrBuildError({"ktr_1": data_1, "ktr_2": data_2}, e) from e

    try:
        ktr2_xml, ktr2_filename, warnings_2 = build_ktr(
            ktr_data_2, f"{process_name}_stg_dwh" if process_name else "KTR_2_stg_dwh",
            real_connections=real_connections,
            required_columns_by_table=required_columns_by_table,
            pass_source_connection="conn_staging",
            pass_dest_connection="conn_dwh",
            strict_connections=strict_connections,
        )
    except Exception as e:
        _log.error("build_ktr (KTR_2 STG→DWH) failed: %s — conservando raw_data para reintento manual", str(e))
        raise KtrBuildError({"ktr_1": data_1, "ktr_2": data_2}, e) from e

    # proceso_etl.steps es el resumen legible que consume el frontend (conteo de
    # steps por tipo/orden en ChartPanel) — combinar ambos tramos y renumerar
    # secuencialmente, si no solo se ve la mitad (origen→STG) del proceso.
    proceso_1 = data_1.get("proceso_etl", {})
    proceso_2 = data_2.get("proceso_etl", {})
    merged_steps = [
        {**s, "orden": i + 1}
        for i, s in enumerate([*proceso_1.get("steps", []), *proceso_2.get("steps", [])])
    ]
    proceso_etl_merged = {
        "nombre": proceso_1.get("nombre") or proceso_2.get("nombre", ""),
        "descripcion": proceso_1.get("descripcion", ""),
        "steps": merged_steps,
    }

    from app.services.job_analyzer import build_kjb_xml

    job_plan = _build_job_plan(ktr1_filename, ktr2_filename, process_name)
    kjb_xml = build_kjb_xml(job_plan)
    kjb_filename = f"{_sanitize(process_name or 'Proceso_ETL')}_job.kjb"

    lineage = stitch_lineage(ktr_data_1, ktr_data_2)

    advertencias, integridad_validaciones = _split_integrity_warnings([
        *data_1.get("advertencias_buenas_practicas", []),
        *data_2.get("advertencias_buenas_practicas", []),
        *(connection_warnings or []),
        *(extra_warnings or []),
        *warnings_1,
        *warnings_2,
    ])

    return ETLGenerateResponse(
        proceso_etl=proceso_etl_merged,
        validaciones=[*data_1.get("validaciones", []), *data_2.get("validaciones", []), *integridad_validaciones],
        documentacion=data_1.get("documentacion", "") or data_2.get("documentacion", ""),
        advertencias_buenas_practicas=advertencias,
        dwh_sample={},
        ktr_xml=ktr1_xml,
        ktr_filename=ktr1_filename,
        ktr2_xml=ktr2_xml,
        ktr2_filename=ktr2_filename,
        kjb_xml=kjb_xml,
        kjb_filename=kjb_filename,
        lineage=lineage,
        metadata=metadata,
    )


def _build_response(
    resp: LLMResponse,
    required_columns_by_table: dict[str, list[str]] | None = None,
    extra_warnings: list[str] | None = None,
) -> ETLGenerateResponse:
    # json_data is always populated when schema= was passed to llm.complete()
    data = resp.json_data
    if data is None:
        _log.error("LLM returned no json_data. raw=%r", (resp.content or "")[:200])
        raise ValueError("LLM returned no structured data — cannot parse ETL response")

    metadata = MetadataResponse(
        modelo_usado=resp.model,
        tokens_input=resp.input_tokens,
        tokens_output=resp.output_tokens,
        region_inferencia=resp.provider,
    )
    return _build_response_from_data(
        data, metadata,
        required_columns_by_table=required_columns_by_table,
        extra_warnings=extra_warnings,
    )


async def build_etl_from_raw(raw_llm_data: dict, llm: BaseLLM | None = None) -> ETLGenerateResponse:
    """Reconstruye el ETL a partir de una respuesta cruda del modelo guardada previamente
    (p. ej. tras un fallo de build_ktr).

    raw_llm_data trae uno de dos shapes según qué flujo falló:
    - flujo legacy monolítico: dict plano con "proceso_etl"/"ktr" en el nivel top.
    - flujo de 2 KTR: {"ktr_1": {...plano...}, "ktr_2": {...plano...}} (ver
      KtrBuildError en _build_response_from_two_ktr_data).

    llm=None (default): no llama al LLM para repair_ktr_steps() (comportamiento
    histórico). llm=<instancia>: antes de construir, corre repair_ktr_steps()
    sobre cada ktr para intentar salvar steps con config incompleto — este es
    precisamente el caso de uso más común de este endpoint ("Reutilizar
    respuesta" tras un fallo de build_ktr por config incompleto). Sin
    req.stg_definition/dwh_model disponibles acá (no viajan en raw_llm_data),
    el contexto de esquema para la reparación queda vacío — la corrección se
    apoya solo en los few-shot de STEP_FEWSHOT, no en nombres reales de columna.

    repair_integrity_gaps() corre SIEMPRE (con o sin llm) — su fallback
    determinístico no llama al modelo, así que aplica igual en el llm=None
    histórico: cierra huecos de campo atribuibles a un Constant con config
    vacío en vez de dejar que build_ktr aborte con el mismo error otra vez."""
    metadata = MetadataResponse(
        modelo_usado="(respuesta reutilizada)",
        tokens_input=0,
        tokens_output=0,
        region_inferencia="local",
    )
    extra_warnings: list[str] = []
    if "ktr_1" in raw_llm_data and "ktr_2" in raw_llm_data:
        if llm is not None:
            raw_llm_data["ktr_1"]["ktr"], w1 = await repair_ktr_steps(raw_llm_data["ktr_1"]["ktr"], llm, "")
            raw_llm_data["ktr_2"]["ktr"], w2 = await repair_ktr_steps(raw_llm_data["ktr_2"]["ktr"], llm, "")
            extra_warnings = [*w1, *w2]
        raw_llm_data["ktr_1"]["ktr"], w3 = await repair_integrity_gaps(raw_llm_data["ktr_1"]["ktr"], llm, "")
        raw_llm_data["ktr_2"]["ktr"], w4 = await repair_integrity_gaps(raw_llm_data["ktr_2"]["ktr"], llm, "")
        extra_warnings = [*extra_warnings, *w3, *w4]
        return _build_response_from_two_ktr_data(
            raw_llm_data["ktr_1"], raw_llm_data["ktr_2"], metadata, extra_warnings=extra_warnings,
        )
    if llm is not None and raw_llm_data.get("ktr"):
        raw_llm_data["ktr"], extra_warnings = await repair_ktr_steps(raw_llm_data["ktr"], llm, "")
    if raw_llm_data.get("ktr"):
        raw_llm_data["ktr"], integrity_warnings = await repair_integrity_gaps(raw_llm_data["ktr"], llm, "")
        extra_warnings = [*extra_warnings, *integrity_warnings]
    return _build_response_from_data(raw_llm_data, metadata, extra_warnings=extra_warnings)


async def generate_etl(
    req: ETLRequest,
    llm: BaseLLM,
    db: Optional[Session] = None,
) -> ETLGenerateResponse:
    ctx        = context_builder.build_model_context(req.origenTables, db)
    origen_txt = context_builder.format_model_context_for_prompt(ctx)
    prompt     = _build_prompt(req, origen_txt)
    resp       = await llm.complete(prompt, _load_system("system_etl.txt"), schema=ETL_OUTPUT_SCHEMA)

    repair_warnings: list[str] = []
    if resp.json_data and resp.json_data.get("ktr"):
        context_text = f"{req.stagingDef!r}\n\n{req.dwhModel!r}"
        resp.json_data["ktr"], repair_warnings = await repair_ktr_steps(resp.json_data["ktr"], llm, context_text)
        resp.json_data["ktr"], integrity_warnings = await repair_integrity_gaps(resp.json_data["ktr"], llm, context_text)
        repair_warnings = [*repair_warnings, *integrity_warnings]

    return _build_response(resp, extra_warnings=repair_warnings)


def _build_prompt_from_inference(
    req: ETLFromInferenceRequest,
    origen_txt: str,
    mode: Literal["origen_stg", "stg_dwh"] | None = None,
    staging_tables: list[str] | None = None,
) -> str:
    """
    mode=None (default): comportamiento actual sin cambios — prompt monolítico
    de 3 capas (origen→STG→DWH) en una sola llamada.

    mode="origen_stg" / "stg_dwh": prompts recortados para el flujo de 2 KTR.
    staging_tables fija los mismos nombres de tabla STG en ambas llamadas
    (extraídos una sola vez de req.stg_definition vía _staging_table_names_from_ddl,
    no dejados a criterio del modelo) — evita que KTR_2 lea de una tabla con
    nombre distinto a la que KTR_1 escribió.
    """
    objetivo = req.descripcionObjetivo.strip() or "No especificado."
    reglas   = req.reglasNegocio.strip() or "No se especificaron reglas de negocio adicionales."
    tablas_stg_txt = ", ".join(staging_tables) if staging_tables else "(ver DDL de staging abajo)"

    if mode is None:
        return f"""## OBJETIVO DEL PROCESO ETL
{objetivo}

## ESQUEMA DE ORIGEN (perfilado — sin datos crudos)
{origen_txt}
## STAGING (inferido y confirmado por el usuario)
{req.stg_definition}

## MODELO DWH (inferido y confirmado por el usuario)
{req.dwh_model}

## REGLAS DE NEGOCIO
{reglas}

---

Genera el proceso ETL completo respetando estrictamente el objetivo indicado.
Las estructuras STG y DWH ya fueron validadas por el usuario — usá exactamente esos nombres de tablas y columnas.
Verifica la consistencia de tipos y nombres entre las tres capas.

Antes de escribir el objeto `ktr`, determiná en orden:
**Etapa 1 — Diseño del grafo:** listá mentalmente todos los steps necesarios (nombre, tipo) y sus conexiones (hops) para ESTE proceso específico, sin entrar en configs internas. Verificá grafo completo: ningún step aislado.
**Etapa 2 — Configuración interna:** solo después del grafo completo, poblá el `config` de cada step en orden topológico (entrada → salida).
No mezcles las etapas — configura solo cuando el grafo esté cerrado.
"""

    if mode == "origen_stg":
        return f"""## OBJETIVO DEL PROCESO ETL
{objetivo}

## ALCANCE DE ESTA LLAMADA [CRÍTICO]
Esta transformación cubre ÚNICAMENTE origen → STAGING. Es KTR_1 de 2 archivos
separados que un .kjb orquesta en secuencia. NO generes steps ni hops que lean
o escriban tablas de DWH (dim_*, fact_*) — eso lo cubre KTR_2 en otra llamada.
Cada tabla de staging listada abajo DEBE recibirse en un step `TableOutput`
(sink) al final de su rama — no hay ningún step posterior que la consuma en
este archivo.

## ESQUEMA DE ORIGEN (perfilado — sin datos crudos)
{origen_txt}
## STAGING — nombres de tabla FIJOS, usar EXACTAMENTE estos (destino de esta llamada)
{tablas_stg_txt}

Definición completa (inferida y confirmada por el usuario):
{req.stg_definition}

## REGLAS DE NEGOCIO
{reglas}

---

Genera el tramo origen→STAGING respetando estrictamente el objetivo indicado.
Usá exactamente los nombres de tabla STG listados arriba — no los alteres ni generes otros.
Verifica la consistencia de tipos y nombres entre origen y staging.

Antes de escribir el objeto `ktr`, determiná en orden:
**Etapa 1 — Diseño del grafo:** listá mentalmente todos los steps necesarios (nombre, tipo) y sus conexiones (hops) para ESTE tramo, sin entrar en configs internas. Verificá grafo completo: ningún step aislado.
**Etapa 2 — Configuración interna:** solo después del grafo completo, poblá el `config` de cada step en orden topológico (entrada → salida).
No mezcles las etapas — configura solo cuando el grafo esté cerrado.
"""

    # mode == "stg_dwh"
    return f"""## OBJETIVO DEL PROCESO ETL
{objetivo}

## ALCANCE DE ESTA LLAMADA [CRÍTICO]
Esta transformación cubre ÚNICAMENTE STAGING → DWH. Es KTR_2 de 2 archivos
separados que un .kjb orquesta en secuencia, corre después de KTR_1 (que ya
pobló las tablas de staging). NO generes steps que lean de tablas de origen
operacional — el único punto de entrada de este archivo es un `TableInput`
que lee de las tablas de staging listadas abajo. NO leas ni referencies ninguna
tabla que no esté en esa lista.

## STAGING — nombres de tabla FIJOS, usar EXACTAMENTE estos (origen de esta llamada, ya poblados por KTR_1)
{tablas_stg_txt}

Definición completa (inferida y confirmada por el usuario):
{req.stg_definition}

## MODELO DWH (inferido y confirmado por el usuario)
{req.dwh_model}

## REGLAS DE NEGOCIO
{reglas}

---

Genera el tramo STAGING→DWH respetando estrictamente el objetivo indicado.
Usá exactamente los nombres de tabla STG listados arriba como fuente — no los alteres ni generes otros.
Verifica la consistencia de tipos y nombres entre staging y DWH.

Antes de escribir el objeto `ktr`, determiná en orden:
**Etapa 1 — Diseño del grafo:** listá mentalmente todos los steps necesarios (nombre, tipo) y sus conexiones (hops) para ESTE tramo, sin entrar en configs internas. Verificá grafo completo: ningún step aislado.
**Etapa 2 — Configuración interna:** solo después del grafo completo, poblá el `config` de cada step en orden topológico (entrada → salida).
No mezcles las etapas — configura solo cuando el grafo esté cerrado.
"""


async def generate_etl_from_inference(
    req: ETLFromInferenceRequest,
    llm: BaseLLM,
    db: Optional[Session] = None,
    on_llm_done=None,
) -> ETLGenerateResponse:
    """Genera el proceso ETL como 2 KTR + 1 .kjb: KTR_1 (origen→STG) y KTR_2
    (STG→DWH), con los mismos nombres de tabla STG fijados en ambas llamadas
    al modelo (_staging_table_names_from_ddl) para que KTR_2 lea exactamente
    lo que KTR_1 escribió."""
    ctx            = context_builder.build_model_context(req.origenTables, db)
    origen_txt     = context_builder.format_model_context_for_prompt(ctx)
    staging_tables = _staging_table_names_from_ddl(req.stg_definition)
    system         = _load_system("system_etl.txt")

    prompt_1 = _build_prompt_from_inference(req, origen_txt, mode="origen_stg", staging_tables=staging_tables)
    resp_1   = await llm.complete(prompt_1, system, schema=ETL_OUTPUT_SCHEMA)

    prompt_2 = _build_prompt_from_inference(req, "", mode="stg_dwh", staging_tables=staging_tables)
    resp_2   = await llm.complete(prompt_2, system, schema=ETL_OUTPUT_SCHEMA)

    if on_llm_done is not None:
        await on_llm_done()

    data_1 = resp_1.json_data
    data_2 = resp_2.json_data
    if data_1 is None or data_2 is None:
        _log.error(
            "LLM returned no json_data. raw_1=%r raw_2=%r",
            (resp_1.content or "")[:200], (resp_2.content or "")[:200],
        )
        raise ValueError("LLM returned no structured data — cannot parse ETL response")

    context_text = f"{req.stg_definition}\n\n{req.dwh_model}"
    data_1["ktr"], repair_warnings_1 = await repair_ktr_steps(data_1["ktr"], llm, context_text)
    data_2["ktr"], repair_warnings_2 = await repair_ktr_steps(data_2["ktr"], llm, context_text)
    data_1["ktr"], integrity_warnings_1 = await repair_integrity_gaps(data_1["ktr"], llm, context_text)
    data_2["ktr"], integrity_warnings_2 = await repair_integrity_gaps(data_2["ktr"], llm, context_text)

    metadata = MetadataResponse(
        modelo_usado=resp_2.model,
        tokens_input=(resp_1.input_tokens or 0) + (resp_2.input_tokens or 0),
        tokens_output=(resp_1.output_tokens or 0) + (resp_2.output_tokens or 0),
        region_inferencia=resp_2.provider,
    )
    required_columns_by_table = _required_columns_from_ddl(req.stg_definition, req.dwh_model)
    type_warnings = _type_mismatch_warnings(req.stg_definition, req.dwh_model, data_2["ktr"])
    return _build_response_from_two_ktr_data(
        data_1, data_2, metadata,
        required_columns_by_table=required_columns_by_table,
        extra_warnings=[*repair_warnings_1, *repair_warnings_2, *integrity_warnings_1, *integrity_warnings_2, *type_warnings],
    )


# ─── Flujo async con conexiones en paralelo ───────────────────────────────────
# generate_etl_async corre en background (asyncio.create_task, disparado desde
# el router apenas el usuario confirma) mientras el cliente completa el
# formulario de conexiones destino. _try_build es la barrera: se llama tanto
# al terminar el modelo como al recibir conexiones, sin importar el orden.

def _try_build(job_id, db: Session) -> None:
    from app.models.ktr_build_job import KtrBuildJob, ModelStatus, KtrBuildStatus
    from app.services.ktr_builder import resolve_real_connections

    job = db.get(KtrBuildJob, job_id)
    if job is None:
        return  # TTL lo barrió, o nunca existió

    if job.model_status == ModelStatus.failed:
        job.build_status = KtrBuildStatus.failed
        db.commit()
        return

    if job.model_status != ModelStatus.done:
        return  # el modelo todavía no respondió — nada que hacer todavía

    if not job.connections_map:
        job.build_status = KtrBuildStatus.awaiting_connections
        db.commit()
        return

    real_connections, conn_warnings = resolve_real_connections(job.connections_map, db)
    metadata = MetadataResponse(**job.model_json["metadata"])

    try:
        result = _build_response_from_two_ktr_data(
            job.model_json["raw_data_1"],
            job.model_json["raw_data_2"],
            metadata,
            real_connections=real_connections,
            connection_warnings=conn_warnings,
            required_columns_by_table=job.model_json.get("required_columns_by_table"),
            extra_warnings=job.model_json.get("repair_warnings"),
            # Este es el único caller que ya intentó resolver conexiones reales
            # (resolve_real_connections arriba) — si algo queda placeholder acá
            # es un .ktr final roto, no un preview: abortar en vez de entregarlo.
            strict_connections=True,
        )
    except KtrBuildError as exc:
        job.build_status = KtrBuildStatus.failed
        job.model_error = str(exc.original_error)
        db.commit()
        return
    except Exception as exc:
        # Cualquier falla no anticipada (ej. bug en build_lineage) no debe dejar
        # el job colgado en un estado no terminal: el cliente polea /status
        # indefinidamente si build_status nunca llega a "failed".
        _log.error("_try_build: fallo no anticipado — %s", exc, exc_info=True)
        job.build_status = KtrBuildStatus.failed
        job.model_error = str(exc)
        db.commit()
        return

    job.result_json = result.model_dump(mode="json")
    job.build_status = KtrBuildStatus.built
    db.commit()


async def generate_etl_async(job_id, req: ETLFromInferenceRequest, llm: BaseLLM, session_factory) -> None:
    """Llama al modelo y persiste el resultado en ktr_build_jobs. Abre su propia
    sesión de DB porque corre en un asyncio.create_task separado del request
    original — la sesión del request ya cerró para cuando esto se ejecuta."""
    from app.models.ktr_build_job import KtrBuildJob, KtrBuildStatus, ModelStatus

    db = session_factory()
    try:
        ctx            = context_builder.build_model_context(req.origenTables, db)
        origen_txt     = context_builder.format_model_context_for_prompt(ctx)
        staging_tables = _staging_table_names_from_ddl(req.stg_definition)
        system         = _load_system("system_etl.txt")

        prompt_1 = _build_prompt_from_inference(req, origen_txt, mode="origen_stg", staging_tables=staging_tables)
        prompt_2 = _build_prompt_from_inference(req, "", mode="stg_dwh", staging_tables=staging_tables)

        try:
            resp_1 = await llm.complete(prompt_1, system, schema=ETL_OUTPUT_SCHEMA)
            resp_2 = await llm.complete(prompt_2, system, schema=ETL_OUTPUT_SCHEMA)
            data_1 = resp_1.json_data
            data_2 = resp_2.json_data
            if data_1 is None or data_2 is None:
                raise ValueError("El modelo no devolvió datos estructurados.")

            context_text = f"{req.stg_definition}\n\n{req.dwh_model}"
            data_1["ktr"], repair_warnings_1 = await repair_ktr_steps(data_1["ktr"], llm, context_text)
            data_2["ktr"], repair_warnings_2 = await repair_ktr_steps(data_2["ktr"], llm, context_text)
            data_1["ktr"], integrity_warnings_1 = await repair_integrity_gaps(data_1["ktr"], llm, context_text)
            data_2["ktr"], integrity_warnings_2 = await repair_integrity_gaps(data_2["ktr"], llm, context_text)
        except Exception as exc:
            job = db.get(KtrBuildJob, job_id)
            if job is not None:
                job.model_status = ModelStatus.failed
                # build_status default es "awaiting_model" — sin esto el frontend
                # nunca ve un build_status terminal y polea /status hasta el techo
                # de 30 min (POLL_MAX_ATTEMPTS) en vez de cortar apenas el modelo falla.
                job.build_status = KtrBuildStatus.failed
                job.model_error = str(exc)
                db.commit()
            return

        metadata = MetadataResponse(
            modelo_usado=resp_2.model,
            tokens_input=(resp_1.input_tokens or 0) + (resp_2.input_tokens or 0),
            tokens_output=(resp_1.output_tokens or 0) + (resp_2.output_tokens or 0),
            region_inferencia=resp_2.provider,
        )

        type_warnings = _type_mismatch_warnings(req.stg_definition, req.dwh_model, data_2["ktr"])

        job = db.get(KtrBuildJob, job_id)
        if job is None:
            return  # el usuario abandonó y el TTL ya barrió la fila
        job.model_status = ModelStatus.done
        job.model_json = {
            "raw_data_1": data_1,
            "raw_data_2": data_2,
            "metadata": metadata.model_dump(),
            "required_columns_by_table": _required_columns_from_ddl(req.stg_definition, req.dwh_model),
            "repair_warnings": [*repair_warnings_1, *repair_warnings_2, *integrity_warnings_1, *integrity_warnings_2, *type_warnings],
        }
        db.commit()

        _try_build(job_id, db)
    except Exception as exc:
        # Red de seguridad: cualquier falla no anticipada por fuera del try/except
        # puntual de arriba (ej. build_model_context, _try_build) tampoco debe
        # dejar el job colgado en "awaiting_model" para siempre.
        _log.error("generate_etl_async: fallo no anticipado — %s", exc, exc_info=True)
        job = db.get(KtrBuildJob, job_id)
        if job is not None:
            job.model_status = ModelStatus.failed
            job.build_status = KtrBuildStatus.failed
            job.model_error = str(exc)
            db.commit()
    finally:
        db.close()
