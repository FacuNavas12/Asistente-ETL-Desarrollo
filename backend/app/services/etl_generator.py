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
from app.services.ddl_validation import validate_and_correct_ddl
from app.services.ktr_builder import (
    build_ktr,
    compute_cut,
    derive_dimension_step_type,
    enforce_dimension_step_policy,
    normalize_step_configs,
    repair_integrity_gaps,
    repair_ktr_steps,
    split_ktr_by_cut,
    STEP_TYPE_ALIASES,
)
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


def _format_dim_contracts(dim_contracts: list) -> str:
    """Texto embebido en el prompt STG→DWH: nombres EXACTOS que Dimension
    lookup/update debe usar por dimensión — fuente de verdad que reemplaza la
    deducción por parseo del DDL (bug original: columna deducida mal o
    inexistente, step apunta a algo que no existe y PDI falla en runtime,
    no al guardar el .ktr)."""
    if not dim_contracts:
        return (
            "(vacío — modelo normalizado sin dimensiones, o el contrato no llegó. "
            "Si dwh_model SÍ declara tablas dim_*, NO derives technical_key/version_field/"
            "date_from/date_to por convención de nombres: reportá un `warning` en "
            "`validaciones` señalando que falta el contrato para esa dimensión.)"
        )
    lines = []
    for c in dim_contracts:
        # step_requerido (Parte 4, bloque A): el step ya está decidido acá —
        # deriva determinísticamente de scd_type, no es un juicio del modelo.
        # Un override (volumen alto, matching difuso, full refresh) es válido
        # pero tiene que registrarse en `validaciones` con el prefijo
        # OVERRIDE_STEP_PREFIX y campo=<tabla> — ver system_etl.txt.
        step_requerido = derive_dimension_step_type(c.scd_type)
        line = (
            f"- {c.table}: step_requerido={step_requerido}, technical_key={c.technical_key}, "
            f"version_field={c.version_field}, date_from={c.date_from}, date_to={c.date_to}, "
            f"natural_keys={list(c.natural_keys)}, unknown_key_value={c.unknown_key_value}, "
            f"scd_type={c.scd_type}"
        )
        lines.append(line)
    return "\n".join(lines)


def _dim_contracts_anomaly_warning(dwh_ddl: str, dim_contracts: list) -> list[str]:
    """Señal explícita cuando dwh_model declara tablas dim_* pero dim_contracts
    llega vacío: sin esto, la fase de steps degrada en silencio al parseo por
    convención de nombres (el bug que dim_contracts reemplaza) y una corrida
    con el contrato perdido se ve idéntica a una corrida sana. model_type ya
    no está disponible para detectar el caso (ver Parte 1) — la detección se
    apoya en el propio DDL."""
    if dim_contracts:
        return []
    if not dwh_ddl or not dwh_ddl.strip():
        return []
    try:
        schemas = parse_ddl(dwh_ddl, dialect=None)
    except Exception as exc:
        _log.warning("No se pudo parsear dwh_model para chequeo de dim_contracts: %s", exc)
        return []
    dim_tables = [s.source_name for s in schemas if s.source_name.lower().startswith("dim_")]
    if not dim_tables:
        return []
    return [
        f"dim_contracts llegó vacío pero el DWH declara dimensiones ({', '.join(dim_tables)}) — "
        "la fase de generación de steps va a deducir technical_key/version_field/date_from/"
        "date_to por convención de nombres en vez del contrato explícito. Verificar por qué "
        "no llegó (¿la inferencia lo omitió? ¿se perdió camino al request de generación?)."
    ]


def _build_ktr_stage(
    ktr_data: dict,
    base_name: str,
    **build_kwargs,
) -> tuple[list[tuple[dict, str, str]], list[str]]:
    """F3 punto 1 (03-plan.md, H20): entre repair_integrity_gaps y build_ktr(),
    corta ktr_data en 1..N sub-transformaciones vía compute_cut() y llama
    build_ktr() una vez por grupo, en el orden de ejecución que el corte exige
    (escritor de una tabla-disparadora antes que su lector/otro-escritor —
    dims antes que hechos, per err1.ktr/err2.ktr/H21).

    Devuelve ([(ktr_data_del_grupo, xml, filename), ...], warnings) — warnings
    incluye las notificaciones D15 del corte (V2/ciclo patológico) más las de
    cada build_ktr(). 1 solo grupo (caso universal hoy, D6-bis) -> 1 sola
    llamada a build_ktr(), mismo nombre/xml/filename que antes de este punto.

    Capacidad de servicio completa y probada (test_fragmentation_wiring.py) —
    NO todavía conectada a la respuesta HTTP (ETLGenerateResponse sigue fija
    a ktr_xml/ktr2_xml/kjb_xml, 2 KTR + 1 KJB; ver hueco documentado en
    03-plan.md). Los call sites del flujo en vivo (_build_response_from_*)
    llaman compute_cut() por separado solo para sus notificaciones, sin
    invocar esta función todavía — ver comentario en esos call sites."""
    sub_dicts, notifications = split_ktr_by_cut(ktr_data, STEP_TYPE_ALIASES)
    built: list[tuple[dict, str, str]] = []
    warnings: list[str] = list(notifications)
    for i, sub in enumerate(sub_dicts):
        name = base_name if len(sub_dicts) == 1 else f"{base_name}_{i + 1}"
        xml, filename, w = build_ktr(sub, name, **build_kwargs)
        built.append((sub, xml, filename))
        warnings.extend(w)
    return built, warnings


def _cut_pending_warning(label: str, groups: list[list[str]]) -> str:
    """F3: compute_cut() detectó que la etapa `label` necesita partirse en
    len(groups) sub-transformaciones (condición C1/C1-bis — misma clase de
    carrera/doble-escritor que err1.ktr/err2.ktr, H21) pero ETLGenerateResponse
    todavía no tiene dónde poner más de 1 archivo por etapa (hueco documentado
    en 03-plan.md, no resuelto por F3 punto 1-3). Se entrega el .ktr SIN
    partir — este warning es la señal explícita de que ese archivo entero
    contiene el patrón de carrera, para que se revise a mano en Spoon en vez
    de fallar en silencio."""
    grupos_txt = "; ".join(f"grupo {i + 1}: {', '.join(g)}" for i, g in enumerate(groups))
    return (
        f"{FIELD_INTEGRITY_PREFIX}Corte estructural pendiente en la etapa {label}: el motor de "
        f"fragmentación (F3, ver docs/refactor/03-plan.md) identificó {len(groups)} sub-transformaciones "
        f"necesarias ({grupos_txt}) por una tabla escrita y leída (o escrita dos veces) por steps "
        "distintos en el mismo archivo — el mismo patrón de carrera/doble-escritor que err1.ktr/"
        "err2.ktr (H21). La generación multi-archivo por HTTP todavía no está soportada (hueco de "
        "ETLGenerateResponse, ver 03-plan.md) — este .ktr se entrega SIN partir; revisar manualmente "
        "en Spoon el riesgo de carrera antes de ejecutar."
    )


def _build_job_plan(
    stages: list[tuple[str, list[tuple[dict, str, str]]]],
    process_name: str,
) -> tuple["JobPlan", list[tuple[str, str]]]:
    """Arma la jerarquía de jobs del flujo de N KTR en Python puro — el orden
    entre etapas es siempre fijo (origen→STG antes que STG→DWH) y, dentro de
    una etapa, el que ya determinó compute_cut() (F2/F3) — no hay ambigüedad
    que amerite una llamada al modelo (a diferencia del flujo CreateJob, que
    sí la usa porque orquesta .ktr arbitrarios subidos por el usuario).

    stages: [(etiqueta_etapa, [(ktr_data, xml, filename), ...]), ...] en
    orden de ejecución — cada lista de archivos ya viene en el orden que
    _build_ktr_stage()/compute_cut() exige dentro de esa etapa.

    Etapa con 1 archivo -> entry_type="trans" directo al .ktr (comportamiento
    histórico, sin wrapper). Etapa con N>1 -> entry_type="job" (F2.5/H7)
    apuntando a un .kjb intermedio que orquesta esos N .ktr en secuencia
    (jerarquía de 3 niveles: job_master -> job_<etapa> -> ktrs).

    Devuelve (job_plan_maestro, sub_kjbs) — sub_kjbs = [(kjb_xml, kjb_filename), ...]
    de los .kjb intermedios que alguna etapa haya necesitado (vacío si ninguna
    etapa tiene más de 1 archivo — caso universal hoy, D6-bis)."""
    from app.schemas.job_schemas import JobEntry, JobPlan
    from app.services.job_analyzer import build_kjb_xml

    name = process_name or "Proceso_ETL"
    master_entries: list[JobEntry] = []
    sub_kjbs: list[tuple[str, str]] = []
    order = 0
    for label, files in stages:
        if not files:
            continue
        order += 1
        if len(files) == 1:
            _, _, filename = files[0]
            master_entries.append(JobEntry(
                order=order, transformation_name=f"KTR_{label}", filename=filename,
                rationale=f"Carga {label}. Corre en secuencia con el resto de las etapas.",
            ))
            continue

        inner_entries = [
            JobEntry(
                order=i + 1, transformation_name=f"KTR_{label}_{i + 1}", filename=filename,
                rationale=(
                    f"Sub-transformación {i + 1}/{len(files)} de {label} — corte estructural "
                    "(F2/F3, ver 03-plan.md)."
                ),
            )
            for i, (_, _, filename) in enumerate(files)
        ]
        inner_plan = JobPlan(
            job_name=f"{name}_job_{label}",
            description=f"Orquesta las {len(files)} sub-transformaciones de {label} en el orden del corte.",
            overall_rationale=(
                "Job intermedio generado por el motor de corte (F3) — jerarquía de 3 "
                "niveles (H7/F2.5)."
            ),
            execution_order=inner_entries,
        )
        inner_kjb_filename = f"{_sanitize(name)}_job_{label}.kjb"
        sub_kjbs.append((build_kjb_xml(inner_plan), inner_kjb_filename))
        master_entries.append(JobEntry(
            order=order, transformation_name=f"JOB_{label}", filename=inner_kjb_filename,
            rationale=f"Orquesta las {len(files)} sub-transformaciones de {label}.",
            entry_type="job",
        ))

    master_plan = JobPlan(
        job_name=f"{name}_job",
        description=f"Orquesta {name}: " + " → ".join(label for label, files in stages if files) + " en secuencia.",
        overall_rationale=(
            "Job generado por el flujo de N KTR (F3): orden fijo entre etapas, dentro de cada "
            "etapa el orden que exige compute_cut() — no requiere razonamiento del modelo."
        ),
        execution_order=master_entries,
    )
    return master_plan, sub_kjbs


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

    # F3 punto 1 (H20): mismo punto que en el flujo de 2 KTR — ver comentario
    # equivalente en _build_response_from_two_ktr_data. Acá el ktr_data es el
    # proceso monolítico completo (origen→STG→DWH en 1 archivo), así que un
    # corte real acá es aún más significativo (el patrón de err1.ktr/err2.ktr
    # vive todo en el mismo archivo).
    cut = compute_cut(ktr_data, STEP_TYPE_ALIASES)
    cut_warnings = list(cut["notifications"])
    if len(cut["groups"]) > 1:
        cut_warnings.append(_cut_pending_warning("proceso completo", cut["groups"]))

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
        *cut_warnings,
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
    extra_validaciones: list[Validacion] | None = None,
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

    # F3 punto 1 (H20, 03-plan.md): compute_cut() ya corre acá, entre la
    # reparación de integridad (arriba, en el caller) y build_ktr() (abajo).
    # La partición física en N archivos (_build_ktr_stage, service-ready y
    # probada en test_fragmentation_wiring.py) todavía NO se aplica en este
    # flujo en vivo — ETLGenerateResponse sigue fija a 1 KTR por etapa (hueco
    # nuevo, no listado en la lista original de "archivos a tocar" de F3, ver
    # 03-plan.md). Mientras tanto, cada corte real detectado (condición C1/
    # C1-bis) se promueve a Validacion tipo="error" en vez de pasar en
    # silencio — es la misma clase de carrera/doble-escritor de err1.ktr/
    # err2.ktr (H21) que motivó todo este refactor.
    cut_warnings: list[str] = []
    for label, ktr_data in (("origen→STG", ktr_data_1), ("STAGING→DWH", ktr_data_2)):
        cut = compute_cut(ktr_data, STEP_TYPE_ALIASES)
        cut_warnings.extend(cut["notifications"])
        if len(cut["groups"]) > 1:
            cut_warnings.append(_cut_pending_warning(label, cut["groups"]))

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

    # Cada etapa se pasa como 1 solo archivo — _build_job_plan soporta N por
    # etapa (F3 punto 2), pero este flujo en vivo todavía no aplica el corte
    # (ver comentario arriba), así que sub_kjbs siempre da vacío acá.
    job_plan, _sub_kjbs = _build_job_plan(
        [
            ("origen_stg", [(ktr_data_1, ktr1_xml, ktr1_filename)]),
            ("stg_dwh", [(ktr_data_2, ktr2_xml, ktr2_filename)]),
        ],
        process_name,
    )
    kjb_xml = build_kjb_xml(job_plan)
    kjb_filename = f"{_sanitize(process_name or 'Proceso_ETL')}_job.kjb"

    lineage = stitch_lineage(ktr_data_1, ktr_data_2)

    advertencias, integridad_validaciones = _split_integrity_warnings([
        *data_1.get("advertencias_buenas_practicas", []),
        *data_2.get("advertencias_buenas_practicas", []),
        *(connection_warnings or []),
        *(extra_warnings or []),
        *cut_warnings,
        *warnings_1,
        *warnings_2,
    ])

    return ETLGenerateResponse(
        proceso_etl=proceso_etl_merged,
        validaciones=[
            *data_1.get("validaciones", []), *data_2.get("validaciones", []),
            *integridad_validaciones, *(extra_validaciones or []),
        ],
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


async def build_etl_from_raw(
    raw_llm_data: dict,
    llm: BaseLLM | None = None,
    dim_contracts: list | None = None,
) -> ETLGenerateResponse:
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
    vacío en vez de dejar que build_ktr aborte con el mismo error otra vez.

    dim_contracts (opcional): a diferencia de repair_*, este camino NO corre
    validate_and_correct_ddl() (audita el DDL contra el contrato — llama al
    modelo, y el punto de "reutilizar respuesta" es evitar esa llamada) pero
    SÍ corre enforce_dimension_step_policy() si dim_contracts llega — es
    determinístico, no llama al modelo, y hoy era la única fase de las tres de
    la serie dim_contracts que este camino se saltaba por completo. Sin
    dim_contracts (llamadas viejas, o datos guardados antes de este parámetro)
    se omite sin error — comportamiento histórico preservado."""
    metadata = MetadataResponse(
        modelo_usado="(respuesta reutilizada)",
        tokens_input=0,
        tokens_output=0,
        region_inferencia="local",
    )
    extra_warnings: list[str] = []
    if "ktr_1" in raw_llm_data and "ktr_2" in raw_llm_data:
        raw_llm_data["ktr_1"]["ktr"], cfg_w1 = normalize_step_configs(raw_llm_data["ktr_1"]["ktr"])
        raw_llm_data["ktr_2"]["ktr"], cfg_w2 = normalize_step_configs(raw_llm_data["ktr_2"]["ktr"])
        extra_warnings = [*cfg_w1, *cfg_w2]
        if llm is not None:
            raw_llm_data["ktr_1"]["ktr"], w1 = await repair_ktr_steps(raw_llm_data["ktr_1"]["ktr"], llm, "")
            raw_llm_data["ktr_2"]["ktr"], w2 = await repair_ktr_steps(raw_llm_data["ktr_2"]["ktr"], llm, "")
            extra_warnings = [*extra_warnings, *w1, *w2]
        raw_llm_data["ktr_1"]["ktr"], w3 = await repair_integrity_gaps(raw_llm_data["ktr_1"]["ktr"], llm, "")
        raw_llm_data["ktr_2"]["ktr"], w4 = await repair_integrity_gaps(raw_llm_data["ktr_2"]["ktr"], llm, "")
        extra_warnings = [*extra_warnings, *w3, *w4]
        if dim_contracts:
            step_policy_results = enforce_dimension_step_policy(
                raw_llm_data["ktr_2"]["ktr"], dim_contracts, STEP_TYPE_ALIASES,
                raw_llm_data["ktr_2"].get("validaciones", []),
            )
            raw_llm_data["ktr_2"].setdefault("validaciones", []).extend(step_policy_results)
        return _build_response_from_two_ktr_data(
            raw_llm_data["ktr_1"], raw_llm_data["ktr_2"], metadata, extra_warnings=extra_warnings,
        )
    if raw_llm_data.get("ktr"):
        raw_llm_data["ktr"], extra_warnings = normalize_step_configs(raw_llm_data["ktr"])
    if llm is not None and raw_llm_data.get("ktr"):
        raw_llm_data["ktr"], w = await repair_ktr_steps(raw_llm_data["ktr"], llm, "")
        extra_warnings = [*extra_warnings, *w]
    if raw_llm_data.get("ktr"):
        raw_llm_data["ktr"], integrity_warnings = await repair_integrity_gaps(raw_llm_data["ktr"], llm, "")
        extra_warnings = [*extra_warnings, *integrity_warnings]
        if dim_contracts:
            step_policy_results = enforce_dimension_step_policy(
                raw_llm_data["ktr"], dim_contracts, STEP_TYPE_ALIASES,
                raw_llm_data.get("validaciones", []),
            )
            raw_llm_data.setdefault("validaciones", []).extend(step_policy_results)
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
        resp.json_data["ktr"], cfg_warnings = normalize_step_configs(resp.json_data["ktr"])
        context_text = f"{req.stagingDef!r}\n\n{req.dwhModel!r}"
        resp.json_data["ktr"], repair_warnings = await repair_ktr_steps(resp.json_data["ktr"], llm, context_text)
        resp.json_data["ktr"], integrity_warnings = await repair_integrity_gaps(resp.json_data["ktr"], llm, context_text)
        repair_warnings = [*cfg_warnings, *repair_warnings, *integrity_warnings]

    return _build_response(resp, extra_warnings=repair_warnings)


def _build_prompt_from_inference(
    req: ETLFromInferenceRequest,
    origen_txt: str,
    mode: Literal["origen_stg", "stg_dwh"] | None = None,
    staging_tables: list[str] | None = None,
    dwh_ddl: str | None = None,
) -> str:
    """
    mode=None (default): comportamiento actual sin cambios — prompt monolítico
    de 3 capas (origen→STG→DWH) en una sola llamada.

    mode="origen_stg" / "stg_dwh": prompts recortados para el flujo de 2 KTR.
    staging_tables fija los mismos nombres de tabla STG en ambas llamadas
    (extraídos una sola vez de req.stg_definition vía _staging_table_names_from_ddl,
    no dejados a criterio del modelo) — evita que KTR_2 lea de una tabla con
    nombre distinto a la que KTR_1 escribió.

    dwh_ddl: DDL del DWH a usar en el prompt. None (default) usa req.dwh_model
    tal cual llegó en el request. El caller pasa el DDL final que devuelve
    ddl_validation.validate_and_correct_ddl() (Parte 3) — el .ktr se arma
    contra ese, no contra el crudo de la inferencia.
    """
    objetivo = req.descripcionObjetivo.strip() or "No especificado."
    reglas   = req.reglasNegocio.strip() or "No se especificaron reglas de negocio adicionales."
    tablas_stg_txt = ", ".join(staging_tables) if staging_tables else "(ver DDL de staging abajo)"
    dwh_ddl_txt = dwh_ddl if dwh_ddl is not None else req.dwh_model

    if mode is None:
        return f"""## OBJETIVO DEL PROCESO ETL
{objetivo}

## ESQUEMA DE ORIGEN (perfilado — sin datos crudos)
{origen_txt}
## STAGING (inferido y confirmado por el usuario)
{req.stg_definition}

## MODELO DWH (inferido y confirmado por el usuario)
{dwh_ddl_txt}

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
{dwh_ddl_txt}

## CONTRATOS DE DIMENSION (dim_contracts — fuente de verdad para Dimension lookup/update, NO derivar del DDL)
{_format_dim_contracts(req.dim_contracts)}

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
    lo que KTR_1 escribió.

    Antes de armar los prompts, corre validate_and_correct_ddl() (Parte 3):
    el .ktr se construye contra el DDL final que devuelve esa auditoría, no
    contra req.dwh_model crudo — ver ddl_validation.py."""
    ddl_result = await validate_and_correct_ddl(req.dwh_model, req.dim_contracts, llm)
    dwh_ddl    = ddl_result.dwh_ddl

    ctx            = context_builder.build_model_context(req.origenTables, db)
    origen_txt     = context_builder.format_model_context_for_prompt(ctx)
    staging_tables = _staging_table_names_from_ddl(req.stg_definition)
    system         = _load_system("system_etl.txt")

    prompt_1 = _build_prompt_from_inference(req, origen_txt, mode="origen_stg", staging_tables=staging_tables)
    resp_1   = await llm.complete(prompt_1, system, schema=ETL_OUTPUT_SCHEMA)

    prompt_2 = _build_prompt_from_inference(req, "", mode="stg_dwh", staging_tables=staging_tables, dwh_ddl=dwh_ddl)
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

    data_1["ktr"], cfg_warnings_1 = normalize_step_configs(data_1["ktr"])
    data_2["ktr"], cfg_warnings_2 = normalize_step_configs(data_2["ktr"])
    context_text = f"{req.stg_definition}\n\n{dwh_ddl}"
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
    required_columns_by_table = _required_columns_from_ddl(req.stg_definition, dwh_ddl)
    type_warnings = _type_mismatch_warnings(req.stg_definition, dwh_ddl, data_2["ktr"])
    dim_contract_warnings = _dim_contracts_anomaly_warning(dwh_ddl, req.dim_contracts)
    ddl_change_warnings = [f"DDL (Parte 3): {c}" for c in ddl_result.cambios_aplicados]
    step_policy_results = enforce_dimension_step_policy(
        data_2["ktr"], req.dim_contracts, STEP_TYPE_ALIASES, data_2.get("validaciones", []),
    )
    return _build_response_from_two_ktr_data(
        data_1, data_2, metadata,
        required_columns_by_table=required_columns_by_table,
        extra_warnings=[
            *cfg_warnings_1, *cfg_warnings_2,
            *repair_warnings_1, *repair_warnings_2, *integrity_warnings_1, *integrity_warnings_2,
            *type_warnings, *dim_contract_warnings, *ddl_change_warnings,
        ],
        extra_validaciones=[*ddl_result.conflictos, *[Validacion(**r) for r in step_policy_results]],
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

    if job.connections_map is None:
        # None = el usuario todavía no terminó de decidir las conexiones
        # destino (ni "Completar en Spoon" ni el formulario). Un dict vacío
        # {} (todas las capas dejadas para Spoon) SÍ es una decisión final —
        # a diferencia de antes, ya no bloquea el build.
        job.build_status = KtrBuildStatus.awaiting_connections
        db.commit()
        return

    real_connections, conn_warnings = resolve_real_connections(job.connections_map, db, owner=job.owner_id)
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
            extra_validaciones=[
                Validacion(**c) for c in [
                    *job.model_json.get("ddl_conflictos", []),
                    *job.model_json.get("step_policy_conflictos", []),
                ]
            ],
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

    # Superset a configuración manual (ver decisión de diseño de no-custodia
    # de credenciales): la conexión ETL_DWH ya no se auto-provisiona acá con
    # una URI real — no hay password del que armarla. El usuario la configura
    # una vez en Superset → Configuración → Conexiones a bases de datos (ver
    # get_or_create_database, que ya crea la entrada con placeholder cuando
    # no hay URI real — ese fallback siempre existió, ahora es el único camino).


async def generate_etl_async(job_id, req: ETLFromInferenceRequest, llm: BaseLLM, session_factory) -> None:
    """Llama al modelo y persiste el resultado en ktr_build_jobs. Abre su propia
    sesión de DB porque corre en un asyncio.create_task separado del request
    original — la sesión del request ya cerró para cuando esto se ejecuta."""
    from app.models.ktr_build_job import KtrBuildJob, KtrBuildStatus, ModelStatus

    db = session_factory()
    try:
        try:
            # Parte 3: el .ktr se arma contra el DDL final que sale de esta
            # auditoría, no contra req.dwh_model crudo — misma llamada que en
            # generate_etl_from_inference.
            ddl_result = await validate_and_correct_ddl(req.dwh_model, req.dim_contracts, llm)
            dwh_ddl    = ddl_result.dwh_ddl

            ctx            = context_builder.build_model_context(req.origenTables, db)
            origen_txt     = context_builder.format_model_context_for_prompt(ctx)
            staging_tables = _staging_table_names_from_ddl(req.stg_definition)
            system         = _load_system("system_etl.txt")

            prompt_1 = _build_prompt_from_inference(req, origen_txt, mode="origen_stg", staging_tables=staging_tables)
            prompt_2 = _build_prompt_from_inference(req, "", mode="stg_dwh", staging_tables=staging_tables, dwh_ddl=dwh_ddl)

            resp_1 = await llm.complete(prompt_1, system, schema=ETL_OUTPUT_SCHEMA)
            resp_2 = await llm.complete(prompt_2, system, schema=ETL_OUTPUT_SCHEMA)
            data_1 = resp_1.json_data
            data_2 = resp_2.json_data
            if data_1 is None or data_2 is None:
                raise ValueError("El modelo no devolvió datos estructurados.")

            data_1["ktr"], cfg_warnings_1 = normalize_step_configs(data_1["ktr"])
            data_2["ktr"], cfg_warnings_2 = normalize_step_configs(data_2["ktr"])
            context_text = f"{req.stg_definition}\n\n{dwh_ddl}"
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

        type_warnings = _type_mismatch_warnings(req.stg_definition, dwh_ddl, data_2["ktr"])
        dim_contract_warnings = _dim_contracts_anomaly_warning(dwh_ddl, req.dim_contracts)
        ddl_change_warnings = [f"DDL (Parte 3): {c}" for c in ddl_result.cambios_aplicados]
        # Muta data_2["ktr"] in-place cuando corrige un downgrade seguro — tiene
        # que correr ANTES de persistir raw_data_2, si no _try_build() reconstruye
        # el .ktr contra el step viejo (sin corregir).
        step_policy_results = enforce_dimension_step_policy(
            data_2["ktr"], req.dim_contracts, STEP_TYPE_ALIASES, data_2.get("validaciones", []),
        )

        job = db.get(KtrBuildJob, job_id)
        if job is None:
            return  # el usuario abandonó y el TTL ya barrió la fila
        job.model_status = ModelStatus.done
        job.model_json = {
            "raw_data_1": data_1,
            "raw_data_2": data_2,
            "metadata": metadata.model_dump(),
            "required_columns_by_table": _required_columns_from_ddl(req.stg_definition, dwh_ddl),
            "repair_warnings": [
                *cfg_warnings_1, *cfg_warnings_2,
                *repair_warnings_1, *repair_warnings_2, *integrity_warnings_1, *integrity_warnings_2,
                *type_warnings, *dim_contract_warnings, *ddl_change_warnings,
            ],
            # Persistido para que _try_build() (que corre después, cuando el
            # usuario confirma las conexiones) pueda incluirlos en la
            # respuesta final sin volver a llamar a validate_and_correct_ddl /
            # enforce_dimension_step_policy.
            "ddl_conflictos": [c.model_dump() for c in ddl_result.conflictos],
            "step_policy_conflictos": step_policy_results,
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
