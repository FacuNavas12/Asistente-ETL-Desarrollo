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
from app.schemas.etl_schemas import (
    ArchivoKtr,
    ETLFromInferenceRequest,
    ETLGenerateResponse,
    EtapaOutput,
    MetadataResponse,
    Validacion,
)
from app.schemas.llm_output_schemas import ETL_OUTPUT_SCHEMA
from app.services import context_builder
from app.services.adapters.sql_table_resolver import resolve_sql_tables
from app.services.ddl_checks import (
    _dim_contracts_anomaly_warning,
    _dims_with_inferred_member,
    _dwh_column_check_constraints,
    _dwh_numeric_scale,
    _known_table_names,
    _required_columns_from_ddl,
    _scd_zero_calendar_guard,
    _staging_table_names_from_ddl,
    _type_mismatch_warnings,
)
from app.services.ddl_validation import synthesize_missing_seed_rows, validate_and_correct_ddl
from app.services.ktr_builder import (
    apply_dimension_contracts,
    build_ktr,
    normalize_step_configs,
    repair_integrity_gaps,
    repair_ktr_steps,
    split_ktr_by_cut,
    validate_stage_contract,
    STEP_TYPE_ALIASES,
    ValidationContext,
    run_passes,
    PRE_EMIT_ERROR_PREFIX,
    split_findings_by_severity,
    TABLE_RECOVERY_PASSES,
    VERIFY_PASSES,
)
from app.services.ktr_builder.build import _sanitize
from app.services.ktr_builder.contract_validate import CONTRACT_PREFIX, validate_ktr_contracts
from app.services.ktr_builder.error_catalog_checks import ERROR_CATALOG_PREFIX, MONEY_FIELD_HINTS
from app.services.ktr_builder.fields_validate import FIELD_INTEGRITY_PREFIX
from app.services.lineage_builder import stitch_lineage_many
from app.services.job_progress import ProgressSink, active_sink, current_sink


def _split_integrity_warnings(warnings: list[str]) -> tuple[list[str], list[Validacion]]:
    """Separa las advertencias de integridad de campos (ver FIELD_INTEGRITY_PREFIX
    en fields_validate.py), de contrato entre KTR (ver CONTRACT_PREFIX en
    contract_validate.py, D23), del catálogo E1-E14 (ver ERROR_CATALOG_PREFIX
    en error_catalog_checks.py, D50) y de los passes pre-emisión con severidad
    real (ver PRE_EMIT_ERROR_PREFIX en validators/base.py, D50) del resto de
    warnings cosméticos. Las cuatro se promueven a Validacion tipo="error" —
    la severidad más alta que EtlDetail sabe renderizar — en vez de perderse
    entre las buenas prácticas. D15/D23 punto 4: mismo canal de severidad,
    sin caso especial.

    Dedupe por string exacto (E-20, errores.md): PRE_EMIT_PASSES corre dos
    veces sobre el mismo step — una vez en _recover_table_keys() sobre
    ktr_data completo antes de compute_cut(), otra vez dentro de build_ktr()
    (build.py:187) sobre el sub-dict ya partido. Un finding insensible al
    corte (ej. check_dimension_lookup_fields) llega acá dos veces, byte a
    byte. Un duplicado exacto nunca es señal — se descarta antes de
    clasificar, no se corrige en el origen (requeriría que build_ktr() supiera
    qué ya corrió antes del corte, más caro que este dedupe)."""
    plain: list[str] = []
    integridad: list[Validacion] = []
    seen: set[str] = set()
    for w in warnings:
        if w in seen:
            continue
        seen.add(w)
        if w.startswith(FIELD_INTEGRITY_PREFIX):
            integridad.append(Validacion(
                tipo="error",
                campo="integridad_campos",
                mensaje=w[len(FIELD_INTEGRITY_PREFIX):],
            ))
        elif w.startswith(CONTRACT_PREFIX):
            integridad.append(Validacion(
                tipo="error",
                campo="contrato_ktr",
                mensaje=w[len(CONTRACT_PREFIX):],
            ))
        elif w.startswith(ERROR_CATALOG_PREFIX):
            integridad.append(Validacion(
                tipo="error",
                campo="catalogo_errores_ktr",
                mensaje=w[len(ERROR_CATALOG_PREFIX):],
            ))
        elif w.startswith(PRE_EMIT_ERROR_PREFIX):
            integridad.append(Validacion(
                tipo="error",
                campo="validacion_pre_emision",
                mensaje=w[len(PRE_EMIT_ERROR_PREFIX):],
            ))
        else:
            plain.append(w)
    return plain, integridad


def _narracion_modelo(validaciones: list[dict] | None) -> tuple[tuple[str, str], ...]:
    """(V-1/V-2, docs/refactor/plan-reparacion-etl.md, item 5) Extrae pares
    (campo, mensaje) de la narración CRUDA del modelo -- llamar SIEMPRE antes
    de que el caller mezcle esta lista con hallazgos deterministas (H29/D50),
    para que narration_crosscheck.py compare al modelo contra sí mismo, no
    contra sus propios findings ya promovidos."""
    return tuple(
        (str(v.get("campo") or ""), str(v.get("mensaje") or ""))
        for v in (validaciones or [])
        if isinstance(v, dict) and v.get("mensaje")
    )


def _recover_table_keys(
    ktr_data: dict,
    known_tables: frozenset[str],
    dwh_constraints: dict[str, dict[str, dict]] | None = None,
    narracion_modelo: list[dict] | None = None,
    dwh_numeric_scale: dict[str, tuple[int, int]] | None = None,
) -> list[str]:
    """Corre TABLE_RECOVERY_PASSES (H29 recover_table_key — ver
    validators/__init__.py) y devuelve los findings ya formateados como
    warnings — llamar SIEMPRE junto a normalize_step_configs(), ANTES de
    apply_dimension_contracts() y de split_ktr_by_cut() (build_rw_matrix):
    ambos necesitan ver 'table' ya recuperado (ver validators/README.md).

    O3 (docs/refactor/30-decision-python-llm.md): antes corría TODO
    PRE_EMIT_PASSES acá — incluidos los passes de VERIFICACIÓN
    (check_dimension_lookup_fields, check_narration_crosscheck...), que
    inspeccionaban el config que el MODELO había escrito. Ahora ese config
    está por ser reescrito por apply_dimension_contracts(): un finding sobre
    un valor a punto de pisarse es una señal falsa, no ruido inocuo. Los
    passes de verificación se movieron a _verify_emitted_ktr(), que corre
    DESPUÉS — ver el call site en cada flujo.

    dwh_constraints (Fase 2-ter, docs/refactor/03c-investigacion-vocabulario-
    dimension-kettle.md): {} si el caller no tiene DDL DWH disponible en este
    punto (ej. camino de reuso de respuesta LLM, H29 arriba) — check_constraint_
    filter_rows no-opea sin esto, mismo criterio best-effort que el resto del
    módulo.

    Fase 0 (D50): findings severity=="error" llevan PRE_EMIT_ERROR_PREFIX —
    _split_integrity_warnings los promueve a Validacion tipo=error en vez de
    perderse entre advertencias_buenas_practicas."""
    findings = run_passes(ValidationContext(
        ktr_data, STEP_TYPE_ALIASES, known_tables, dwh_constraints or {},
        _narracion_modelo(narracion_modelo), dwh_numeric_scale or {},
    ), passes=TABLE_RECOVERY_PASSES)
    return split_findings_by_severity(findings)


def _verify_emitted_ktr(
    ktr_data: dict,
    known_tables: frozenset[str],
    dwh_constraints: dict[str, dict[str, dict]] | None = None,
    narracion_modelo: list[dict] | None = None,
    dwh_numeric_scale: dict[str, tuple[int, int]] | None = None,
) -> list[str]:
    """O3 (docs/refactor/30-decision-python-llm.md): corre VERIFY_PASSES —
    la mitad de PRE_EMIT_PASSES que INSPECCIONA config en vez de recuperar
    'table'. Llamar SIEMPRE después de apply_dimension_contracts(), sobre el
    ktr_data ya sintetizado — es la estación 3 de la cadena corta de O3
    ("Python verifica"), y tiene destinatario real incluso para dimensiones:
    una regresión en la propia síntesis de Python, o un DimensionLookup
    sobre una tabla fuera de dim_contracts (donde no se sintetizó nada, el
    config sigue siendo 100% del modelo)."""
    findings = run_passes(ValidationContext(
        ktr_data, STEP_TYPE_ALIASES, known_tables, dwh_constraints or {},
        _narracion_modelo(narracion_modelo), dwh_numeric_scale or {},
    ), passes=VERIFY_PASSES)
    return split_findings_by_severity(findings)


def _format_dim_contracts(dim_contracts: list) -> str:
    """Texto embebido en el prompt STG→DWH — qué columnas mapear y contra
    qué nombre físico, nada de CÓMO configurarlas.

    O3 (docs/refactor/30-decision-python-llm.md): antes esta línea traía 11
    tokens (step_requerido, step_lookup_fk, scd_type, modo_por_atributo,
    version_field, date_from, unknown_key_value...) porque el modelo escribía
    el config COMPLETO del step de dimensión, y esos tokens eran la fuente de
    verdad para que lo escribiera bien. Ya no lo escribe —
    apply_dimension_contracts (dimension_step_policy.py) construye
    update/return_field/date_from/date_to/version_field/fields[].type
    SIEMPRE desde el DimContract, ignorando lo que el modelo haya puesto.
    Cada token que quedaba acá describiendo esa configuración era una
    invitación a que el modelo la reescribiera y la contradijera — se fueron
    todos menos los cuatro que el modelo sigue necesitando para lo que SÍ es
    su trabajo: decidir topología y mapear nombres de columna cuando no
    coinciden con el stream (ver system_etl.txt, bloque "STEP DE
    DIMENSIONES")."""
    if not dim_contracts:
        return (
            "(vacío — modelo normalizado sin dimensiones, o el contrato no llegó. "
            "Si dwh_model SÍ declara tablas dim_*, configurá el DimensionLookup completo "
            "(ver el primer ejemplo del catálogo de steps) y reportá un `warning` en "
            "`validaciones` señalando que falta el contrato para esa dimensión.)"
        )
    lines = []
    for c in dim_contracts:
        columnas_destino = list(c.attributes_scd1) + list(c.attributes_scd2)
        line = (
            f"- {c.table}: columnas_destino={columnas_destino}, "
            f"natural_keys={list(c.natural_keys)}, "
            f"campo_sk_en_stream={c.technical_key}, columna_vigencia={c.date_to}"
        )
        lines.append(line)
    return "\n".join(lines)


def _format_inferred_member_dims(dims: list[dict]) -> str:
    """Sección hermana de '## CONTRATOS DE DIMENSION' en el prompt STG→DWH —
    solo aparece cuando hay al menos una dimensión que la necesita (D21).
    Vacío en el caso común (sin FK NOT NULL hacia dim_contracts) no agrega
    nada al prompt."""
    if not dims:
        return ""
    lines = [
        "\n## DIMENSIONES CON MIEMBRO INFERIDO OBLIGATORIO (D21)",
        "Las siguientes dimensiones son referenciadas por una FK NOT NULL desde una tabla de "
        "hechos — ese lookup NUNCA puede devolver NULL. El step loader de cada una tiene que "
        "recibir, además del "
        "stream real de origen, las claves naturales de la tabla de hechos que todavía no están "
        "en la dimensión (anti-join previo, ej. TableInput/ExecSQL con NOT EXISTS) con atributos "
        "default e `inferred_member='Y'`, unidas (Union) al stream real — AMBOS alimentando el "
        "MISMO step loader, nunca un segundo writer separado para esta tabla. Ver 'PATRÓN "
        "MIEMBRO INFERIDO' en las especificaciones de steps para el ejemplo completo.",
    ]
    for d in dims:
        lines.append(
            f"- {d['dimension']}: referenciada por {d['fact_table']}.{d['fk_column']} (NOT NULL). "
            f"natural_keys={d['natural_keys']}"
        )
    return "\n".join(lines)


def _inferred_member_notifications(dims: list[dict]) -> list[str]:
    """Warnings accionables (D13/D15) — uno por dimensión que requiere el
    patrón de miembro inferido, para que quede visible en el registro de
    deltas de la corrida aunque el LLM lo haya implementado bien."""
    return [
        f"Miembro inferido (D21): '{d['dimension']}' referenciada por "
        f"{d['fact_table']}.{d['fk_column']} (NOT NULL) — el loader debe recibir claves "
        "naturales huérfanas vía anti-join+Union, no un segundo writer."
        for d in dims
    ]


# Fase 2-bis (03c-investigacion-vocabulario-dimension-kettle.md, mitigaciones
# 1 y 2): D44/R-K7 volvieron el step de carga de dimensión idéntico ("Dimension
# lookup/update") para todo scd_type — la Fase 2 sacó el síntoma visible de una
# misinferencia de scd_type (H44: no determinista sobre la misma entrada) y sin
# esto el sistema pasa a producir errores semánticos indetectables en
# artefactos impecables (03c:270, "no opcional respecto de la Fase 2"). Las dos
# funciones de abajo operan solo sobre dim_contracts — sin DDL, a diferencia de
# _scd_zero_calendar_guard — así que valen en TODO camino que tenga
# dim_contracts, incluido build_etl_from_raw (sin DDL disponible, ver su
# docstring).
def _scd_consequence_findings(dim_contracts: list) -> list[str]:
    """Mitigación 1 (03c:172): un finding por dimensión con la consecuencia
    concreta del scd_type elegido, no solo el número — convierte una decisión
    invisible en revisable. scd_type==0 queda afuera: la rama no-calendario ya
    la señala _scd_zero_calendar_guard como error, y la calendario no tiene
    atributo que cambie."""
    findings: list[str] = []
    for c in dim_contracts:
        if c.scd_type == 2:
            attrs = ", ".join(c.attributes_scd2) or "(ninguno declarado)"
            findings.append(
                f"'{c.table}' cargada como SCD2: cada cambio en {attrs} genera una versión "
                "nueva (histórico preservado, la tabla crece con cada cambio)."
            )
        elif c.scd_type == 1:
            attrs = ", ".join(c.attributes_scd1) or "(ninguno declarado)"
            findings.append(
                f"'{c.table}' cargada como SCD1: cambios en {attrs} sobrescriben el valor "
                "anterior (sin histórico)."
            )
    return findings


def _monetary_scd2_guard(dim_contracts: list) -> list[str]:
    """Mitigación 2 (03c:173): una columna de importe/monto no puede versionarse
    como atributo de dimensión — cambia con cada transacción, no es lentamente
    cambiante, y pertenece al hecho (cierra B-7). Reusa la misma señal que
    v11_monetario_sin_bignumber (error_catalog_checks.MONEY_FIELD_HINTS),
    aplicada acá al contrato antes de emitir en vez de al step ya emitido.
    PRE_EMIT_ERROR_PREFIX -> _split_integrity_warnings la promueve a
    Validacion tipo=error (D15: no aborta, pero no queda perdida entre buenas
    prácticas)."""
    findings: list[str] = []
    for c in dim_contracts:
        hits = [a for a in c.attributes_scd2 if any(h in a.lower() for h in MONEY_FIELD_HINTS)]
        if not hits:
            continue
        findings.append(
            f"{PRE_EMIT_ERROR_PREFIX}'{c.table}' tiene columna(s) de importe/monto en "
            f"attributes_scd2 ({', '.join(hits)}) — un valor monetario no debe versionarse como "
            "atributo de dimensión (cambia con cada transacción, no es lentamente cambiante); "
            "pertenece al hecho, no a la dimensión. Revisar el modelo."
        )
    return findings




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

    D20 (02-decisiones.md): conectada de verdad en _build_response_from_data /
    _build_response_from_two_ktr_data — el flujo HTTP en vivo ahora parte
    físicamente cuando compute_cut() detecta groups>1, en vez de solo
    notificarlo y entregar el .ktr sin partir.

    D45 punto 1: resolve_sql_tables real (sqlglot, services/adapters/
    sql_table_resolver.py) inyectado acá — el único punto de wiring entre el
    contrato de dominio (build_rw_matrix acepta un callable) y su
    implementación real, para que fragmentation.py (DOMAIN_MODULES) siga sin
    importar sqlglot."""
    sub_dicts, notifications = split_ktr_by_cut(ktr_data, STEP_TYPE_ALIASES, resolve_sql_tables)
    # D45 punto 6 (S-13): chequeo a nivel etapa sobre el CONJUNTO de sub_dicts
    # que acaba de salir del corte — ver validate_stage_contract() para qué
    # cubre (fragmento posterior que escribe lo que uno anterior ya lee) y
    # qué no repite (orden del job, hop cruzado — garantizados/cubiertos arriba).
    notifications = [*notifications, *validate_stage_contract(sub_dicts, STEP_TYPE_ALIASES, resolve_sql_tables)]
    built: list[tuple[dict, str, str]] = []
    # D50: notifications ya son Finding (severity real) — split_findings_by_severity
    # las vuelve string, marcando con PRE_EMIT_ERROR_PREFIX solo las severity=="error"
    # (mismo componente sin relación segura / ciclo de orden), para que
    # _split_integrity_warnings las promueva. V2 (lookup sin productor en esta
    # etapa) queda "warning" tal cual.
    warnings: list[str] = split_findings_by_severity(notifications)
    for i, sub in enumerate(sub_dicts):
        name = base_name if len(sub_dicts) == 1 else f"{base_name}_{i + 1}"
        # build_ktr() prioriza ktr_data["name"] por sobre el nombre que se le
        # pasa (build.py:188, `ktr_data.get("name") or process_name`) — el
        # KTR que el modelo devuelve siempre trae "name" (ETL_OUTPUT_SCHEMA lo
        # exige), así que sin este override los N sub-dicts de un corte real
        # comparten el mismo "name" heredado de split_ktr_by_cut() y build_ktr
        # los emite con el mismo <name>/filename (timestamp aparte). Solo se
        # pisa cuando hay más de 1 grupo — con 1 solo grupo `sub` es el mismo
        # ktr_data de siempre (D19: cero cambio de comportamiento).
        if len(sub_dicts) > 1:
            sub = {**sub, "name": name}
        xml, filename, w = build_ktr(sub, name, **build_kwargs)
        built.append((sub, xml, filename))
        warnings.extend(w)
    return built, warnings


def _etapa_output(
    files: list[tuple[dict, str, str]],
    sub_kjb: tuple[str, str] | None,
    nombre: str,
) -> EtapaOutput:
    """D20: empaqueta 1..N archivos ya construidos (_build_ktr_stage) en el
    shape de ETLGenerateResponse.etapas. sub_kjb viene de _build_job_plan()
    para la misma etapa — None cuando len(files)==1 (nada que orquestar),
    (kjb_xml, kjb_filename) cuando compute_cut() partió esa etapa en N.
    nombre (D28): etiqueta de la etapa, expuesta para que el frontend nombre
    la carpeta del ZIP cuando tipo="kjb"."""
    if sub_kjb is None:
        _, xml, filename = files[0]
        return EtapaOutput(tipo="ktr", nombre=nombre, archivo=ArchivoKtr(xml=xml, filename=filename))
    kjb_xml, kjb_filename = sub_kjb
    return EtapaOutput(
        tipo="kjb",
        nombre=nombre,
        kjb=ArchivoKtr(xml=kjb_xml, filename=kjb_filename),
        archivos=[ArchivoKtr(xml=xml, filename=filename) for _, xml, filename in files],
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


def _build_response_from_data(
    data: dict,
    metadata: MetadataResponse,
    real_connections: dict[str, dict] | None = None,
    connection_warnings: list[str] | None = None,
    required_columns_by_table: dict[str, list[str]] | None = None,
    extra_warnings: list[str] | None = None,
    strict_connections: bool = False,
    known_tables: frozenset[str] | None = None,
    dwh_ddl: str | None = None,
    stg_ddl: str | None = None,
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

    # F3 punto 1 (H20), D20: entre repair_integrity_gaps (en el caller) y este
    # punto, _build_ktr_stage() corta ktr_data en 1..N sub-transformaciones
    # reales vía compute_cut() y llama build_ktr() una vez por grupo. Acá
    # ktr_data es el proceso monolítico completo (origen→STG→DWH en 1
    # archivo) — 1 sola "etapa" en la respuesta, a diferencia del flujo de
    # inferencia (2 etapas, ver _build_response_from_two_ktr_data).
    try:
        built, ktr_warnings = _build_ktr_stage(
            ktr_data, process_name,
            real_connections=real_connections,
            required_columns_by_table=required_columns_by_table,
            strict_connections=strict_connections,
            known_tables=known_tables,
        )
    except Exception as e:
        _log.error("build_ktr failed: %s — conservando raw_data para reintento manual", str(e))
        raise KtrBuildError(data, e) from e

    # sub_kjb solo se arma cuando compute_cut() partió el proceso completo en
    # N>1 archivos — _build_job_plan() reusa la misma lógica de armar el .kjb
    # intermedio que usa el flujo de 2 etapas, sin necesidad de un job maestro
    # acá (1 sola etapa, nada que secuenciar por encima de ella).
    sub_kjb = None
    if len(built) > 1:
        _, sub_kjbs = _build_job_plan([("proceso", built)], process_name)
        sub_kjb = sub_kjbs[0]
    etapa = _etapa_output(built, sub_kjb, nombre="proceso")

    advertencias, integridad_validaciones = _split_integrity_warnings([
        *data.get("advertencias_buenas_practicas", []),
        *(connection_warnings or []),
        *(extra_warnings or []),
        *ktr_warnings,
    ])

    _log.info("dwh_sample keys: %s", list(data.get("dwh_sample", {}).keys()))
    # narracion_modelo (V-1/V-2, docs/refactor/plan-reparacion-etl.md, item 5):
    # canal separado de integridad_validaciones a propósito -- el primero es
    # narración libre del LLM, el segundo son hallazgos deterministas
    # (recover_table_key/check_constraint_filter_rows/etc). Mezclarlos sin
    # nombrar el origen es lo que impedía distinguir "el modelo dijo X" de
    # "el sistema detectó X" al leer el código.
    narracion_modelo = data.get("validaciones", [])
    return ETLGenerateResponse(
        proceso_etl=data["proceso_etl"],
        validaciones=[*narracion_modelo, *integridad_validaciones],
        documentacion=data.get("documentacion", ""),
        advertencias_buenas_practicas=advertencias,
        dwh_sample=data.get("dwh_sample", {}),
        etapas=[etapa],
        lineage=stitch_lineage_many([sub for sub, _, _ in built]),
        metadata=metadata,
        dwh_ddl=dwh_ddl,
        stg_ddl=stg_ddl,
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
    dwh_ddl: str | None = None,
    stg_ddl: str | None = None,
    known_tables: frozenset[str] | None = None,
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

    # F3 punto 1 (H20), D20 (02-decisiones.md): _build_ktr_stage() corta cada
    # etapa en 1..N sub-transformaciones reales vía compute_cut() y llama
    # build_ktr() una vez por grupo — ya no solo notifica el corte (D19), lo
    # aplica. Cada corte real detectado (condición C1/C1-bis, misma clase de
    # carrera/doble-escritor de err1.ktr/err2.ktr, H21) sale como N archivos
    # + un .kjb intermedio (ver _build_job_plan/_etapa_output abajo), no como
    # una advertencia sobre un .ktr sin partir.
    try:
        built_1, warnings_1 = _build_ktr_stage(
            ktr_data_1, f"{process_name}_origen_stg" if process_name else "KTR_1_origen_stg",
            real_connections=real_connections,
            required_columns_by_table=required_columns_by_table,
            pass_source_connection="conn_origen",
            pass_dest_connection="conn_staging",
            strict_connections=strict_connections,
            known_tables=known_tables,
        )
    except Exception as e:
        _log.error("build_ktr (KTR_1 origen→STG) failed: %s — conservando raw_data para reintento manual", str(e))
        raise KtrBuildError({"ktr_1": data_1, "ktr_2": data_2}, e) from e

    try:
        built_2, warnings_2 = _build_ktr_stage(
            ktr_data_2, f"{process_name}_stg_dwh" if process_name else "KTR_2_stg_dwh",
            real_connections=real_connections,
            required_columns_by_table=required_columns_by_table,
            pass_source_connection="conn_staging",
            pass_dest_connection="conn_dwh",
            strict_connections=strict_connections,
            known_tables=known_tables,
        )
    except Exception as e:
        # Bloque 3 (docs/refactor/10-estabilizar-emision.md): etapa 1 ya
        # construyó archivo real — no lo tiramos por un fallo estructural
        # (XML mal formado, ktr_data no-dict — D-N, "qué sigue abortando a
        # propósito") de la etapa 2. Se entrega origen→STG solo, con el
        # error de la etapa 2 como Validacion, en vez de forzar el
        # escenario "cero archivos" que motivó O1 desde el principio.
        _log.error("build_ktr (KTR_2 STG→DWH) failed: %s — entregando solo origen→STG, ya construida", str(e))
        from app.services.job_analyzer import build_kjb_xml
        job_plan_1, sub_kjbs_1 = _build_job_plan([("origen_stg", built_1)], process_name)
        kjb_master_1 = ArchivoKtr(
            xml=build_kjb_xml(job_plan_1),
            filename=f"{_sanitize(process_name or 'Proceso_ETL')}_job.kjb",
        )
        etapa_1_only = _etapa_output(built_1, sub_kjbs_1[0] if sub_kjbs_1 else None, nombre="origen_stg")
        advertencias_1, integridad_validaciones_1 = _split_integrity_warnings([
            *data_1.get("advertencias_buenas_practicas", []),
            *(connection_warnings or []), *(extra_warnings or []), *warnings_1,
        ])
        return ETLGenerateResponse(
            proceso_etl=data_1.get("proceso_etl", {}),
            validaciones=[
                *data_1.get("validaciones", []), *integridad_validaciones_1, *(extra_validaciones or []),
                Validacion(
                    tipo="error", campo="stg_dwh",
                    mensaje=f"Etapa Staging→DWH falló al construir el .ktr: {e}. Solo se entrega "
                    "Origen→Staging — reintentar la etapa Staging→DWH por separado.",
                ),
            ],
            documentacion=data_1.get("documentacion", ""),
            advertencias_buenas_practicas=advertencias_1,
            etapas=[etapa_1_only],
            kjb_master=kjb_master_1,
            metadata=metadata,
            dwh_ddl=dwh_ddl,
            stg_ddl=stg_ddl,
        )

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

    # D20: el job maestro siempre secuencia las 2 etapas (origen→STG antes que
    # STG→DWH), sin importar si alguna se partió — caso (d)/D20-punto3 cuando
    # ninguna partió, casos (a)/(b)/(c) cuando sí. sub_kjbs trae, en el mismo
    # orden que las etapas de abajo, un (kjb_xml, kjb_filename) por cada
    # etapa que compute_cut() partió en N>1 (y nada para la que no).
    job_plan, sub_kjbs = _build_job_plan(
        [("origen_stg", built_1), ("stg_dwh", built_2)],
        process_name,
    )
    kjb_master = ArchivoKtr(
        xml=build_kjb_xml(job_plan),
        filename=f"{_sanitize(process_name or 'Proceso_ETL')}_job.kjb",
    )

    sub_kjb_iter = iter(sub_kjbs)
    etapa_1 = _etapa_output(built_1, next(sub_kjb_iter) if len(built_1) > 1 else None, nombre="origen_stg")
    etapa_2 = _etapa_output(built_2, next(sub_kjb_iter) if len(built_2) > 1 else None, nombre="stg_dwh")

    lineage = stitch_lineage_many([
        *(sub for sub, _, _ in built_1),
        *(sub for sub, _, _ in built_2),
    ])

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
        validaciones=[
            *data_1.get("validaciones", []), *data_2.get("validaciones", []),
            *integridad_validaciones, *(extra_validaciones or []),
        ],
        documentacion=data_1.get("documentacion", "") or data_2.get("documentacion", ""),
        advertencias_buenas_practicas=advertencias,
        dwh_sample={},
        etapas=[etapa_1, etapa_2],
        kjb_master=kjb_master,
        lineage=lineage,
        metadata=metadata,
        dwh_ddl=dwh_ddl,
        stg_ddl=stg_ddl,
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
    real_connections: dict[str, dict] | None = None,
    connection_warnings: list[str] | None = None,
    stg_ddl: str | None = None,
    dwh_ddl: str | None = None,
) -> ETLGenerateResponse:
    """Reconstruye el ETL a partir de una respuesta cruda del modelo guardada previamente
    (p. ej. tras un fallo de build_ktr).

    raw_llm_data trae uno de dos shapes según qué flujo falló:
    - flujo legacy monolítico: dict plano con "proceso_etl"/"ktr" en el nivel top.
    - flujo de 2 KTR: {"ktr_1": {...plano...}, "ktr_2": {...plano...}} (ver
      KtrBuildError en _build_response_from_two_ktr_data).

    stg_ddl/dwh_ddl (opcional): a diferencia del resto de este docstring, esto
    NO alimenta ninguna reparación — es puro passthrough hacia
    ETLGenerateResponse.dwh_ddl/stg_ddl para que ResultView (EtlDetail) pinte
    la sección de DDL igual que en el flujo de generación normal. El frontend
    ya los tiene en memoria (inferResult.stg_ddl/dwh_ddl) cuando llama a este
    endpoint ("Reutilizar respuesta") — sin este parámetro, no había forma de
    que llegaran acá, y ResultView oculta la sección entera sin ellos.

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
    SÍ corre apply_dimension_contracts() si dim_contracts llega — es
    determinístico, no llama al modelo (O3: la síntesis del step de
    dimensión nunca necesitó LLM, la única llamada que este camino evitaba
    era la del repair de mapeo de campos, y esa estación ya no existe — ver
    docs/refactor/30-decision-python-llm.md). Sin dim_contracts (llamadas
    viejas, o datos guardados antes de este parámetro) se omite sin error —
    comportamiento histórico preservado.

    real_connections/connection_warnings (opcional): mismo shape que arma
    resolve_real_connections() (ver ktr_builder/connection.py) — antes este
    camino no tenía forma de recibir conexiones y el .ktr salía siempre con
    placeholder, aunque el usuario ya las hubiera completado (ver
    docs/refactor/02-decisiones.md). None (default) preserva el comportamiento
    histórico. strict_connections se activa solo cuando real_connections llega
    (mismo criterio que _try_build): revisa placeholder sin resolver y lo deja
    como warning, nunca aborta (D15)."""
    _log.info(
        "build_etl_from_raw: llm=%s, dim_contracts=%s tabla(s) %s",
        "presente" if llm is not None else "None",
        len(dim_contracts or []),
        [c.table for c in (dim_contracts or [])],
    )
    metadata = MetadataResponse(
        modelo_usado="(respuesta reutilizada)",
        tokens_input=0,
        tokens_output=0,
        region_inferencia="local",
    )
    extra_warnings: list[str] = []
    # H29: sin DDL en este camino (ver docstring arriba) — dim_contracts es la
    # única fuente de nombres de tabla reales disponible acá.
    known_tables = frozenset(c.table.strip().lower() for c in (dim_contracts or []) if c.table)
    if "ktr_1" in raw_llm_data and "ktr_2" in raw_llm_data:
        raw_llm_data["ktr_1"]["ktr"], cfg_w1 = normalize_step_configs(raw_llm_data["ktr_1"]["ktr"])
        raw_llm_data["ktr_2"]["ktr"], cfg_w2 = normalize_step_configs(raw_llm_data["ktr_2"]["ktr"])
        table_w1 = _recover_table_keys(
            raw_llm_data["ktr_1"]["ktr"], known_tables,
            narracion_modelo=raw_llm_data["ktr_1"].get("validaciones", []),
        )
        table_w2 = _recover_table_keys(
            raw_llm_data["ktr_2"]["ktr"], known_tables,
            narracion_modelo=raw_llm_data["ktr_2"].get("validaciones", []),
        )
        extra_warnings = [*cfg_w1, *cfg_w2, *table_w1, *table_w2]
        if llm is not None:
            raw_llm_data["ktr_1"]["ktr"], w1 = await repair_ktr_steps(raw_llm_data["ktr_1"]["ktr"], llm, "")
            raw_llm_data["ktr_2"]["ktr"], w2 = await repair_ktr_steps(raw_llm_data["ktr_2"]["ktr"], llm, "")
            extra_warnings = [*extra_warnings, *w1, *w2]
        raw_llm_data["ktr_1"]["ktr"], w3 = await repair_integrity_gaps(raw_llm_data["ktr_1"]["ktr"], llm, "")
        raw_llm_data["ktr_2"]["ktr"], w4 = await repair_integrity_gaps(raw_llm_data["ktr_2"]["ktr"], llm, "")
        extra_warnings = [*extra_warnings, *w3, *w4]
        if not dim_contracts:
            _log.warning(
                "build_etl_from_raw: dim_contracts vacío/ausente en el request — "
                "apply_dimension_contracts NO corre."
            )
        if dim_contracts:
            step_policy_results = apply_dimension_contracts(
                raw_llm_data["ktr_2"]["ktr"], dim_contracts, STEP_TYPE_ALIASES,
                raw_llm_data["ktr_2"].get("validaciones", []),
            )
            verify_warnings_2 = _verify_emitted_ktr(
                raw_llm_data["ktr_2"]["ktr"], known_tables,
                narracion_modelo=raw_llm_data["ktr_2"].get("validaciones", []),
            )
            raw_llm_data["ktr_2"].setdefault("validaciones", []).extend(step_policy_results)
            extra_warnings = [
                *extra_warnings,
                *verify_warnings_2,
                *_scd_consequence_findings(dim_contracts),
                *_monetary_scd2_guard(dim_contracts),
            ]
        return _build_response_from_two_ktr_data(
            raw_llm_data["ktr_1"], raw_llm_data["ktr_2"], metadata,
            real_connections=real_connections,
            connection_warnings=connection_warnings,
            extra_warnings=extra_warnings,
            strict_connections=bool(real_connections),
            known_tables=known_tables,
            stg_ddl=stg_ddl,
            dwh_ddl=dwh_ddl,
        )
    if raw_llm_data.get("ktr"):
        raw_llm_data["ktr"], extra_warnings = normalize_step_configs(raw_llm_data["ktr"])
        extra_warnings = [*extra_warnings, *_recover_table_keys(
            raw_llm_data["ktr"], known_tables,
            narracion_modelo=raw_llm_data.get("validaciones", []),
        )]
    if llm is not None and raw_llm_data.get("ktr"):
        raw_llm_data["ktr"], w = await repair_ktr_steps(raw_llm_data["ktr"], llm, "")
        extra_warnings = [*extra_warnings, *w]
    if raw_llm_data.get("ktr"):
        raw_llm_data["ktr"], integrity_warnings = await repair_integrity_gaps(raw_llm_data["ktr"], llm, "")
        extra_warnings = [*extra_warnings, *integrity_warnings]
        if not dim_contracts:
            _log.warning(
                "build_etl_from_raw: dim_contracts vacío/ausente en el request — "
                "apply_dimension_contracts NO corre."
            )
        if dim_contracts:
            step_policy_results = apply_dimension_contracts(
                raw_llm_data["ktr"], dim_contracts, STEP_TYPE_ALIASES,
                raw_llm_data.get("validaciones", []),
            )
            verify_warnings = _verify_emitted_ktr(
                raw_llm_data["ktr"], known_tables,
                narracion_modelo=raw_llm_data.get("validaciones", []),
            )
            raw_llm_data.setdefault("validaciones", []).extend(step_policy_results)
            extra_warnings = [
                *extra_warnings,
                *verify_warnings,
                *_scd_consequence_findings(dim_contracts),
                *_monetary_scd2_guard(dim_contracts),
            ]
    return _build_response_from_data(
        raw_llm_data, metadata,
        real_connections=real_connections,
        connection_warnings=connection_warnings,
        extra_warnings=extra_warnings,
        strict_connections=bool(real_connections),
        known_tables=known_tables,
        stg_ddl=stg_ddl,
        dwh_ddl=dwh_ddl,
    )


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
Staging es un contenedor FIEL del origen (truncate + load, copia estructural).
Este tramo NO conoce reglas de negocio — no recibiste ninguna a propósito. NO
generes `FilterRows` ni ningún otro step de validación/filtrado de datos por
regla de negocio: eso se materializa exclusivamente en KTR_2 (staging→DWH).
Los únicos steps además de lectura/escritura permitidos acá son de
transformación técnica (tipos, renombres, campos de auditoría/metadata).

## ESQUEMA DE ORIGEN (perfilado — sin datos crudos)
{origen_txt}
## STAGING — nombres de tabla FIJOS, usar EXACTAMENTE estos (destino de esta llamada)
{tablas_stg_txt}

Definición completa (inferida y confirmada por el usuario):
{req.stg_definition}

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
{_format_inferred_member_dims(_dims_with_inferred_member(dwh_ddl_txt, req.dim_contracts))}

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
    # P1-4 (docs/refactor/plan-reparacion-etl.md): tercera línea de defensa
    # sobre I8/V5 — sintetiza el INSERT sembrado solo si ninguna de las dos
    # llamadas al modelo de arriba lo dejó en el DDL.
    dwh_ddl, seed_warnings = synthesize_missing_seed_rows(dwh_ddl, req.dim_contracts)

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
    # H29 — corre ANTES de apply_dimension_contracts (más abajo) y del
    # split_ktr_by_cut interno de _build_response_from_two_ktr_data: ambos
    # necesitan 'table' ya recuperado (ver validators/README.md).
    known_tables = _known_table_names(req.stg_definition, dwh_ddl)
    dwh_constraints = _dwh_column_check_constraints(dwh_ddl)
    dwh_numeric_scale = _dwh_numeric_scale(dwh_ddl)
    table_warnings_1 = _recover_table_keys(
        data_1["ktr"], known_tables, dwh_constraints, narracion_modelo=data_1.get("validaciones", []),
        dwh_numeric_scale=dwh_numeric_scale,
    )
    table_warnings_2 = _recover_table_keys(
        data_2["ktr"], known_tables, dwh_constraints, narracion_modelo=data_2.get("validaciones", []),
        dwh_numeric_scale=dwh_numeric_scale,
    )
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
    contract_warnings = [
        f"{CONTRACT_PREFIX}{m}"
        for m in validate_ktr_contracts(
            [data_1["ktr"], data_2["ktr"]], req.stg_definition, dwh_ddl, STEP_TYPE_ALIASES,
        )
    ]
    dim_contract_warnings = _dim_contracts_anomaly_warning(dwh_ddl, req.dim_contracts)
    scd_zero_warnings = _scd_zero_calendar_guard(dwh_ddl, req.dim_contracts)
    scd_consequence_findings = _scd_consequence_findings(req.dim_contracts)
    monetary_scd2_warnings = _monetary_scd2_guard(req.dim_contracts)
    inferred_member_warnings = _inferred_member_notifications(
        _dims_with_inferred_member(dwh_ddl, req.dim_contracts)
    )
    ddl_change_warnings = [f"DDL (Parte 3): {c}" for c in ddl_result.cambios_aplicados]
    step_policy_results = apply_dimension_contracts(
        data_2["ktr"], req.dim_contracts, STEP_TYPE_ALIASES, data_2.get("validaciones", []),
    )
    verify_warnings = _verify_emitted_ktr(
        data_2["ktr"], known_tables, dwh_constraints,
        narracion_modelo=data_2.get("validaciones", []), dwh_numeric_scale=dwh_numeric_scale,
    )
    return _build_response_from_two_ktr_data(
        data_1, data_2, metadata,
        required_columns_by_table=required_columns_by_table,
        extra_warnings=[
            *cfg_warnings_1, *cfg_warnings_2, *table_warnings_1, *table_warnings_2,
            *repair_warnings_1, *repair_warnings_2, *integrity_warnings_1, *integrity_warnings_2,
            *type_warnings, *contract_warnings, *dim_contract_warnings, *scd_zero_warnings,
            *scd_consequence_findings, *monetary_scd2_warnings, *verify_warnings,
            *inferred_member_warnings, *ddl_change_warnings, *seed_warnings,
        ],
        extra_validaciones=[*ddl_result.conflictos, *[Validacion(**r) for r in step_policy_results]],
        dwh_ddl=dwh_ddl,
        stg_ddl=req.stg_definition,
        known_tables=known_tables,
    )


# ─── Flujo async con conexiones en paralelo ───────────────────────────────────
# generate_etl_async corre en background (asyncio.create_task, disparado desde
# el router apenas el usuario confirma) mientras el cliente completa el
# formulario de conexiones destino. _try_build es la barrera: se llama tanto
# al terminar el modelo como al recibir conexiones, sin importar el orden.
#
# D29/D30 (docs/refactor/02-decisiones.md): el pipeline de generación quedó
# organizado por ETAPA (no por operación) para poder checkpointear entre la
# etapa 1 y la etapa 2 — ver _stage_pipeline() y los dos bloques "CHECKPOINT"
# más abajo en generate_etl_async(). Progreso emitido vía ProgressSink
# (app.services.job_progress) en cada hito.

_STAGE_LABEL = {
    "job": "la generación",
    "ddl": "la auditoría del DDL",
    "origen_stg": "Origen → Staging",
    "stg_dwh": "Staging → DWH",
    "build": "el armado de archivos",
}


async def _stage_pipeline(
    stage: Literal["origen_stg", "stg_dwh"],
    prompt: str,
    system: str,
    context_text: str,
    llm: BaseLLM,
    sink: ProgressSink,
    known_tables: frozenset[str] = frozenset(),
    dwh_constraints: dict[str, dict[str, dict]] | None = None,
    dwh_numeric_scale: dict[str, tuple[int, int]] | None = None,
) -> tuple[dict, Optional[LLMResponse], list[str]]:
    """Corre UNA etapa completa (llamada al modelo + normalize + los dos
    repairs) y emite progreso en cada hito. Extraído de lo que antes era una
    única secuencia intercalada por operación (D30) — esto es lo que permite
    que generate_etl_async() checkpointee entre la etapa 1 y la etapa 2:
    antes no existía un instante "etapa 1 terminada" al que engancharse."""
    label = _STAGE_LABEL[stage]
    sink.current_stage = stage
    sink.emit(code="stage.llm.started", message=f"Pidiendo al modelo el KTR {label}")

    resp = await llm.complete(prompt, system, schema=ETL_OUTPUT_SCHEMA)
    data = resp.json_data
    if data is None:
        raise ValueError(f"El modelo no devolvió datos estructurados para {label}.")

    n_steps = len(data.get("ktr", {}).get("steps", []))
    sink.emit(code="stage.llm.done", message=f"El modelo respondió — {label} ({n_steps} steps)")

    data["ktr"], cfg_warnings = normalize_step_configs(data["ktr"])
    # H29 — antes de repair/integrity está bien (esos no tocan 'table'), pero
    # tiene que estar antes de apply_dimension_contracts/split_ktr_by_cut,
    # que corren después de que esta función retorna (ver validators/README.md).
    table_warnings = _recover_table_keys(
        data["ktr"], known_tables, dwh_constraints, narracion_modelo=data.get("validaciones", []),
        dwh_numeric_scale=dwh_numeric_scale,
    )

    sink.emit(code="stage.repair.started", message=f"Revisando steps incompletos — {label}")
    data["ktr"], repair_warnings = await repair_ktr_steps(data["ktr"], llm, context_text)
    data["ktr"], integrity_warnings = await repair_integrity_gaps(data["ktr"], llm, context_text)
    sink.emit(code="stage.repair.done", message=f"Steps revisados — {label}")

    return data, resp, [*cfg_warnings, *table_warnings, *repair_warnings, *integrity_warnings]


def _try_build(job_id, db: Session, sink: Optional[ProgressSink] = None) -> None:
    from app.models.ktr_build_job import KtrBuildJob, ModelStatus, KtrBuildStatus
    from app.services.ktr_builder import missing_layer_warnings, resolve_real_connections

    sink = sink or current_sink()  # None si nadie seteó un sink (p.ej. tests viejos) — todo emit() de abajo lo tolera

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
        if sink:
            sink.emit(stage="build", code="build.waiting_connections", message="Esperando las conexiones de destino")
        return

    # Guarda defensiva: model_status solo llega a "done" al final de las dos
    # etapas (ver generate_etl_async) así que esto no debería dispararse hoy
    # — pero un model_status=done sin raw_data_2 por un bug futuro reventaría
    # más abajo con un KeyError feo en vez de un build_status=failed claro.
    if not job.model_json or "raw_data_2" not in job.model_json:
        job.build_status = KtrBuildStatus.failed
        job.model_error = "Estado inconsistente: model_status=done sin raw_data_2."
        db.commit()
        return

    if sink:
        sink.emit(stage="build", code="build.started", message="Armando los archivos .ktr/.kjb")

    real_connections, conn_warnings = resolve_real_connections(job.connections_map, db, owner=job.owner_id)
    # Capas que ni siquiera llegaron en connections_map (ej. conn_origen cuando
    # el origen no vino de una Connection guardada) — resolve_real_connections
    # solo avisa de lo que llegó y falló resolver, no de lo que nunca llegó.
    conn_warnings = [*conn_warnings, *missing_layer_warnings(real_connections)]
    if sink:
        for w in conn_warnings:
            sink.emit(stage="build", code="build.connection_unresolved", level="warning", message=w)
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
            # (resolve_real_connections arriba) — strict_connections activa el
            # chequeo de conexión sin resolver. Ya no aborta (D15): sale como
            # warning en el resultado y como evento build.connection_unresolved
            # arriba, y el .ktr se entrega con placeholder para completar en Spoon.
            strict_connections=True,
            dwh_ddl=job.model_json.get("dwh_ddl"),
            stg_ddl=job.model_json.get("stg_ddl"),
            known_tables=frozenset(job.model_json.get("known_tables") or ()),
        )
    except KtrBuildError as exc:
        job.build_status = KtrBuildStatus.failed
        job.model_error = str(exc.original_error)
        db.commit()
        if sink:
            sink.emit(stage="build", code="build.failed", level="error",
                       message=f"Falló la construcción del .ktr: {exc.original_error}")
        return
    except Exception as exc:
        # Cualquier falla no anticipada (ej. bug en build_lineage) no debe dejar
        # el job colgado en un estado no terminal: el cliente polea /status
        # indefinidamente si build_status nunca llega a "failed".
        _log.error("_try_build: fallo no anticipado (job_id=%s) — %s", job_id, exc, exc_info=True)
        job.build_status = KtrBuildStatus.failed
        job.model_error = str(exc)
        db.commit()
        if sink:
            sink.emit(stage="build", code="build.failed", level="error", message=f"Falló la construcción del .ktr: {exc}")
        return

    job.result_json = result.model_dump(mode="json")
    job.build_status = KtrBuildStatus.built
    db.commit()
    if sink:
        sink.emit(stage="build", code="build.done", message="Archivos generados")

    # Superset a configuración manual (ver decisión de diseño de no-custodia
    # de credenciales): la conexión ETL_DWH ya no se auto-provisiona acá con
    # una URI real — no hay password del que armarla. El usuario la configura
    # una vez en Superset → Configuración → Conexiones a bases de datos (ver
    # get_or_create_database, que ya crea la entrada con placeholder cuando
    # no hay URI real — ese fallback siempre existió, ahora es el único camino).


async def generate_etl_async(job_id, req: ETLFromInferenceRequest, llm: BaseLLM, session_factory) -> None:
    """Llama al modelo y persiste el resultado en ktr_build_jobs. Abre su propia
    sesión de DB porque corre en un asyncio.create_task separado del request
    original — la sesión del request ya cerró para cuando esto se ejecuta.

    D30: la etapa 1 se checkpointea apenas termina (model_json.raw_data_1),
    con model_status todavía en "pending" — un checkpoint parcial nunca
    dispara _try_build() (exige model_status == done). Si la etapa 2 falla,
    el except hace MERGE sobre model_json en vez de reemplazo, así que
    raw_data_1 sobrevive al fallo de la etapa 2.

    D31: req.reuse_stage_1, si viene, saltea la llamada al modelo de la etapa
    1 (y sus repairs) — pero NO saltea validate_and_correct_ddl(): su dwh_ddl
    alimenta el prompt de la etapa 2, _required_columns_from_ddl() y
    ddl_conflictos."""
    from app.models.ktr_build_job import KtrBuildJob, KtrBuildStatus, ModelStatus

    db = session_factory()
    sink = ProgressSink(job_id, session_factory)
    with active_sink(sink):
        try:
            sink.emit(stage="job", code="job.started", message="Generación iniciada")
            try:
                # Parte 3: el .ktr se arma contra el DDL final que sale de esta
                # auditoría, no contra req.dwh_model crudo — misma llamada que en
                # generate_etl_from_inference. SIEMPRE corre, con o sin reuse_stage_1.
                sink.current_stage = "ddl"
                sink.emit(code="ddl.audit.started", message="Auditando el DDL del DWH")
                ddl_result = await validate_and_correct_ddl(req.dwh_model, req.dim_contracts, llm)
                dwh_ddl    = ddl_result.dwh_ddl
                # P1-4 (docs/refactor/plan-reparacion-etl.md): ver misma nota en
                # generate_etl_from_inference.
                dwh_ddl, seed_warnings = synthesize_missing_seed_rows(dwh_ddl, req.dim_contracts)
                n_cambios  = len(ddl_result.cambios_aplicados)
                n_conflictos = len(ddl_result.conflictos)
                sink.emit(
                    stage="ddl", code="ddl.audit.done",
                    message=(
                        f"DDL auditado — {n_cambios} ajuste(s), {n_conflictos} conflicto(s)"
                        if n_conflictos else f"DDL auditado — {n_cambios} ajuste(s) aplicado(s)"
                    ),
                )

                ctx            = context_builder.build_model_context(req.origenTables, db)
                origen_txt     = context_builder.format_model_context_for_prompt(ctx)
                staging_tables = _staging_table_names_from_ddl(req.stg_definition)
                system         = _load_system("system_etl.txt")
                context_text   = f"{req.stg_definition}\n\n{dwh_ddl}"
                known_tables   = _known_table_names(req.stg_definition, dwh_ddl)
                dwh_constraints = _dwh_column_check_constraints(dwh_ddl)
                dwh_numeric_scale = _dwh_numeric_scale(dwh_ddl)

                # ── Etapa 1 (origen→STG) — reuso o llamada real ────────────────
                if req.reuse_stage_1 is not None:
                    data_1 = req.reuse_stage_1
                    # Red defensiva barata (determinística, sin LLM): el payload
                    # puede venir de un archivo importado por el usuario, misma
                    # superficie de confianza que build-from-raw.
                    data_1["ktr"], stage_warnings_1 = normalize_step_configs(data_1["ktr"])
                    stage_warnings_1 = [
                        *stage_warnings_1,
                        *_recover_table_keys(
                            data_1["ktr"], known_tables, dwh_constraints,
                            narracion_modelo=data_1.get("validaciones", []),
                            dwh_numeric_scale=dwh_numeric_scale,
                        ),
                    ]
                    resp_1 = None
                    sink.current_stage = "origen_stg"
                    sink.emit(
                        code="stage.reused",
                        message=f"{_STAGE_LABEL['origen_stg']} reutilizada de un intento anterior — sin llamar al modelo",
                    )
                else:
                    prompt_1 = _build_prompt_from_inference(
                        req, origen_txt, mode="origen_stg", staging_tables=staging_tables,
                    )
                    data_1, resp_1, stage_warnings_1 = await _stage_pipeline(
                        "origen_stg", prompt_1, system, context_text, llm, sink,
                        known_tables=known_tables, dwh_constraints=dwh_constraints,
                        dwh_numeric_scale=dwh_numeric_scale,
                    )

                # CHECKPOINT 1 (D30): model_status sigue en "pending" — _try_build()
                # no se dispara con un checkpoint parcial.
                job = db.get(KtrBuildJob, job_id)
                if job is None:
                    return  # el usuario abandonó y el TTL ya barrió la fila
                job.model_json = {
                    **(job.model_json or {}),
                    "raw_data_1": data_1,
                    "dwh_ddl": dwh_ddl,
                    "stg_ddl": req.stg_definition,
                    "known_tables": sorted(known_tables),
                    "stage_warnings_1": stage_warnings_1,
                    "ddl_conflictos": [c.model_dump() for c in ddl_result.conflictos],
                    "stages": {
                        "origen_stg": {"status": "reused" if req.reuse_stage_1 is not None else "done"},
                        "stg_dwh": {"status": "pending"},
                    },
                }
                db.commit()
                sink.emit(
                    code="stage.checkpoint",
                    message=f"Respuesta de {_STAGE_LABEL['origen_stg']} guardada",
                )

                # ── Etapa 2 (STG→DWH) — siempre llama al modelo ────────────────
                prompt_2 = _build_prompt_from_inference(
                    req, "", mode="stg_dwh", staging_tables=staging_tables, dwh_ddl=dwh_ddl,
                )
                data_2, resp_2, stage_warnings_2 = await _stage_pipeline(
                    "stg_dwh", prompt_2, system, context_text, llm, sink,
                    known_tables=known_tables, dwh_constraints=dwh_constraints,
                )
            except Exception as exc:
                _log.error("generate_etl_async: etapa %s falló (job_id=%s) — %s",
                           sink.current_stage, job_id, exc, exc_info=True)
                sink.emit(
                    code="stage.failed", level="error",
                    message=f"Falló {_STAGE_LABEL.get(sink.current_stage, sink.current_stage)}: {exc}",
                )
                job = db.get(KtrBuildJob, job_id)
                if job is not None:
                    job.model_status = ModelStatus.failed
                    # build_status default es "awaiting_model" — sin esto el frontend
                    # nunca ve un build_status terminal y polea /status hasta el techo
                    # de 30 min (POLL_MAX_ATTEMPTS) en vez de cortar apenas el modelo falla.
                    job.build_status = KtrBuildStatus.failed
                    job.model_error = str(exc)
                    # MERGE, no reemplazo — D30: si la etapa 1 ya se checkpointeó
                    # (bloque de arriba), raw_data_1 sobrevive al fallo de la etapa 2.
                    prev_stages = (job.model_json or {}).get("stages", {})
                    job.model_json = {
                        **(job.model_json or {}),
                        "stages": {**prev_stages, sink.current_stage: {"status": "failed", "error": str(exc)}},
                    }
                    db.commit()
                return

            metadata = MetadataResponse(
                modelo_usado=resp_2.model,
                tokens_input=(resp_1.input_tokens if resp_1 else 0) + (resp_2.input_tokens or 0),
                tokens_output=(resp_1.output_tokens if resp_1 else 0) + (resp_2.output_tokens or 0),
                region_inferencia=resp_2.provider,
            )

            type_warnings = _type_mismatch_warnings(req.stg_definition, dwh_ddl, data_2["ktr"])
            contract_warnings = [
                f"{CONTRACT_PREFIX}{m}"
                for m in validate_ktr_contracts(
                    [data_1["ktr"], data_2["ktr"]], req.stg_definition, dwh_ddl, STEP_TYPE_ALIASES,
                )
            ]
            dim_contract_warnings = _dim_contracts_anomaly_warning(dwh_ddl, req.dim_contracts)
            scd_zero_warnings = _scd_zero_calendar_guard(dwh_ddl, req.dim_contracts)
            scd_consequence_findings = _scd_consequence_findings(req.dim_contracts)
            monetary_scd2_warnings = _monetary_scd2_guard(req.dim_contracts)
            inferred_member_warnings = _inferred_member_notifications(
                _dims_with_inferred_member(dwh_ddl, req.dim_contracts)
            )
            ddl_change_warnings = [f"DDL (Parte 3): {c}" for c in ddl_result.cambios_aplicados]
            # Muta data_2["ktr"] in-place — tiene que correr ANTES de persistir
            # raw_data_2, si no _try_build() reconstruye el .ktr contra el step
            # sin sintetizar. Nota: esto corre DESPUÉS del checkpoint 2 de abajo
            # — raw_data_2 en el commit final puede diferir del que se ve en un
            # /status intermedio, a propósito (ver D30).
            step_policy_results = apply_dimension_contracts(
                data_2["ktr"], req.dim_contracts, STEP_TYPE_ALIASES, data_2.get("validaciones", []),
            )
            verify_warnings = _verify_emitted_ktr(
                data_2["ktr"], known_tables, dwh_constraints,
                narracion_modelo=data_2.get("validaciones", []), dwh_numeric_scale=dwh_numeric_scale,
            )

            reuse_tokens_note = (
                ["Origen → Staging reutilizada — sus tokens no se contabilizan arriba."]
                if req.reuse_stage_1 is not None else []
            )

            job = db.get(KtrBuildJob, job_id)
            if job is None:
                return  # el usuario abandonó y el TTL ya barrió la fila
            job.model_status = ModelStatus.done
            prev_stages = (job.model_json or {}).get("stages", {})
            job.model_json = {
                **(job.model_json or {}),
                "raw_data_2": data_2,
                "metadata": metadata.model_dump(),
                "required_columns_by_table": _required_columns_from_ddl(req.stg_definition, dwh_ddl),
                "repair_warnings": [
                    *stage_warnings_1, *stage_warnings_2,
                    *type_warnings, *contract_warnings, *dim_contract_warnings, *scd_zero_warnings,
                    *scd_consequence_findings, *monetary_scd2_warnings, *verify_warnings,
                    *inferred_member_warnings, *ddl_change_warnings, *seed_warnings, *reuse_tokens_note,
                ],
                # Persistido para que _try_build() (que corre después, cuando el
                # usuario confirma las conexiones) pueda incluirlos en la
                # respuesta final sin volver a llamar a validate_and_correct_ddl /
                # apply_dimension_contracts.
                "ddl_conflictos": [c.model_dump() for c in ddl_result.conflictos],
                "step_policy_conflictos": step_policy_results,
                "stages": {**prev_stages, "stg_dwh": {"status": "done"}},
            }
            db.commit()
            sink.emit(code="stage.checkpoint", message=f"Respuesta de {_STAGE_LABEL['stg_dwh']} guardada")

            _try_build(job_id, db, sink=sink)
        except Exception as exc:
            # Red de seguridad: cualquier falla no anticipada por fuera del try/except
            # puntual de arriba (ej. build_model_context, _try_build) tampoco debe
            # dejar el job colgado en "awaiting_model" para siempre.
            _log.error("generate_etl_async: fallo no anticipado (job_id=%s) — %s", job_id, exc, exc_info=True)
            job = db.get(KtrBuildJob, job_id)
            if job is not None:
                job.model_status = ModelStatus.failed
                job.build_status = KtrBuildStatus.failed
                job.model_error = str(exc)
                db.commit()
        finally:
            db.close()
