"""
Reglas puras sobre DDL de staging/DWH ya parseado con
adapters.ddl_adapter.parse_ddl. Extraído de etl_generator.py — piggyback en
O3 (ver docs/refactor/02-decisiones.md), no una migración de capa: sigue
siendo services/, no domain/, porque depende de parse_ddl (sqlglot vía
adapters/ddl_adapter.py, infraestructura) — ver "Criterio de capas" en
CLAUDE.md. Mismo cluster que docs/auditoria/00b-fallos-silenciosos.md §3.3
señaló: cada función es best-effort, un DDL no parseable degrada a []/{},
solo loggeado, nunca corta el flujo (R11 sin resolver todavía, señalado ahí).
"""
from __future__ import annotations

import logging

from app.domain.canonical_types import CanonicalType
from app.domain.scd import is_calendar_dimension
from app.services.adapters.ddl_adapter import parse_ddl
from app.services.ktr_builder import PRE_EMIT_ERROR_PREFIX
from app.services.ktr_builder.contracts import normalize_config, parse_cfg
from app.services.ktr_builder.dimension_step_policy import (
    DIMENSION_STEP_TYPES,
    has_registered_override,
)

_log = logging.getLogger(__name__)


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


def _dwh_column_check_constraints(dwh_ddl: str) -> dict[str, dict[str, dict]]:
    """{tabla_lower: {columna: {"minimum":.., "maximum":.., "type":..}}} —
    solo columnas con CHECK de rango (minimum/maximum no ambos None, D43).
    Cada tabla queda indexada dos veces (nombre completo del DDL y nombre
    'bare' sin schema, mismo criterio informal que table_key_recovery._bare())
    porque cfg["table"] de un step normalmente llega sin calificar — insumo
    de ValidationContext.dwh_constraints (Fase 2-ter, S-4/H45,
    docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md).
    Best-effort: DDL no parseable -> {}, solo loggeado."""
    result: dict[str, dict[str, dict]] = {}
    if not dwh_ddl or not dwh_ddl.strip():
        return result
    try:
        schemas = parse_ddl(dwh_ddl, dialect=None)
    except Exception as exc:
        _log.warning("No se pudo parsear DDL DWH para CHECK de rango: %s", exc)
        return result
    for schema in schemas:
        cols: dict[str, dict] = {}
        for f in schema.fields:
            if f.constraints.minimum is None and f.constraints.maximum is None:
                continue
            cols[f.name] = {
                "minimum": f.constraints.minimum,
                "maximum": f.constraints.maximum,
                "type": f.type.value,
            }
        if not cols:
            continue
        full = schema.source_name.strip().lower()
        bare = full.rsplit(".", 1)[-1]
        result[full] = cols
        result[bare] = cols
    return result


def _dwh_numeric_scale(dwh_ddl: str) -> dict[str, tuple[int, int]]:
    """{columna_lower: (precision, scale)} -- TODA columna numérica del DWH
    con precisión/escala declarada (`NUMERIC(p,s)`/`DECIMAL(p,s)`), sin el
    filtro de "solo columnas con CHECK" que aplica _dwh_column_check_
    constraints (P3-4, docs/refactor/plan-reparacion-etl.md, item 8).
    Indexado por nombre de columna, no de tabla -- mismo criterio que
    v11_monetario_sin_bignumber/MONEY_FIELD_HINTS, sin cruzar por tabla.
    Best-effort: DDL no parseable -> {}, solo loggeado."""
    result: dict[str, tuple[int, int]] = {}
    if not dwh_ddl or not dwh_ddl.strip():
        return result
    try:
        schemas = parse_ddl(dwh_ddl, dialect=None)
    except Exception as exc:
        _log.warning("No se pudo parsear DDL DWH para escala numérica: %s", exc)
        return result
    for schema in schemas:
        for f in schema.fields:
            if f.precision is None or f.scale is None:
                continue
            result[f.name.strip().lower()] = (f.precision, f.scale)
    return result


def _known_table_names(*ddls: str) -> frozenset[str]:
    """Nombres de tabla física reales (lowercase, todas las tablas del/los
    DDL, sin filtrar por si tienen columnas NOT NULL) — insumo de
    validators.recover_table_key (H29). Best-effort, igual que
    _staging_table_names_from_ddl/_required_columns_from_ddl: un DDL no
    parseable solo se loggea."""
    names: set[str] = set()
    for ddl in ddls:
        if not ddl or not ddl.strip():
            continue
        try:
            schemas = parse_ddl(ddl, dialect=None)
        except Exception as exc:
            _log.warning("No se pudo parsear DDL para nombres de tabla conocidos: %s", exc)
            continue
        names.update(schema.source_name.strip().lower() for schema in schemas)
    return frozenset(names)


# ─── R-K7 (03c-investigacion-vocabulario-dimension-kettle.md, D51): guard de
# scd_type==0 fuera del caso calendario ──────────────────────────────────────
#
# El colapso 0->1 (derive_dimension_loader_step) solo es seguro cuando la
# dimensión es de calendario — el ETL nunca la carga (K18, system_etl.txt), la
# rama del loader es inalcanzable. Si la inferencia declara scd_type=0 en una
# dimensión que SÍ se carga, el colapso convierte una garantía de inmutabilidad
# en sobrescritura silenciosa: pérdida de dato irreversible.
#
# El pre-check de calendario (structure_inferrer._build_scd_precheck_block)
# corre sobre TABLAS DE ORIGEN y solo se serializa como texto del prompt — no
# se persiste, no está indexado por nombre de dimensión DWH. No hay resultado
# que reusar acá. Pero el mismo predicado (is_calendar_dimension) es
# re-derivable sin agregar ningún campo al output del LLM: nombre de tabla
# (DimContract.table), una sola clave natural (DimContract.natural_keys), y el
# tipo de esa clave sale del DDL del DWH — que ya está en mano en este punto
# del pipeline (mismo parse_ddl que _dim_contracts_anomaly_warning/
# _column_types_from_ddl ya usan más arriba).
def _scd_zero_calendar_guard(dwh_ddl: str, dim_contracts: list) -> list[str]:
    """Findings PRE_EMIT_ERROR_PREFIX (severidad error, ver
    validators/base.py) para toda dimensión scd_type==0 que NO es de
    calendario — D15: no aborta, pero _split_integrity_warnings la promueve a
    Validacion tipo=error en vez de perderse entre buenas prácticas. Best-
    effort: DDL no parseable -> sin guard (mismo criterio que el resto de
    funciones _*_from_ddl de este módulo), nunca corta el flujo."""
    zero_type = [c for c in dim_contracts if c.scd_type == 0]
    if not zero_type:
        return []
    if not dwh_ddl or not dwh_ddl.strip():
        return []
    try:
        schemas = parse_ddl(dwh_ddl, dialect=None)
    except Exception as exc:
        _log.warning("No se pudo parsear dwh_model para el guard de scd_type=0: %s", exc)
        return []
    fields_by_table = {s.source_name.strip().lower(): s.fields for s in schemas}

    findings: list[str] = []
    for c in zero_type:
        table_key = c.table.strip().split(".")[-1].lower()
        fields = fields_by_table.get(table_key)
        if fields is None:
            # Sin DDL para esa tabla no se puede confirmar ni descartar — no
            # es este guard el que reporta ese hueco (ver
            # _dim_contracts_anomaly_warning / repair_integrity_gaps).
            continue
        date_cols = [f.name for f in fields if f.type in (CanonicalType.DATE, CanonicalType.DATETIME)]
        if is_calendar_dimension(c.table, list(c.natural_keys), date_cols):
            continue  # colapso 0->1 seguro — el ETL nunca carga el calendario (K18)
        findings.append(
            f"{PRE_EMIT_ERROR_PREFIX}dim_contracts declara '{c.table}' con scd_type=0, pero no "
            "matchea la regla de dimensión de calendario (nombre de tabla + una sola clave "
            "natural de tipo fecha) — R-K7: Kettle no tiene un modo 'no tocar si ya existe' en "
            "Dimension lookup/update, así que scd_type=0 colapsa a scd_type=1 (sobrescritura) "
            "para toda dimensión que el ETL SÍ carga. Si la intención es que este atributo nunca "
            "se sobrescriba, no hay mecanismo — re-declará scd_type=1 explícito. Si es un error "
            "de inferencia, corregí el contrato."
        )
    return findings


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


def _dims_with_inferred_member(dwh_ddl: str, dim_contracts: list) -> list[dict]:
    """D21 (02-decisiones.md): dimensiones referenciadas por una FK NOT NULL de
    una tabla de hechos necesitan el patrón anti-join+Union hacia el loader
    único (miembro inferido) — el lookup de esa FK nunca puede devolver NULL.
    Reusa parse_ddl (mismo parser que _dim_contracts_anomaly_warning arriba):
    is_foreign_key/references/constraints.required por columna ya traen todo
    lo necesario, sin parseo nuevo."""
    if not dim_contracts or not dwh_ddl or not dwh_ddl.strip():
        return []
    try:
        schemas = parse_ddl(dwh_ddl, dialect=None)
    except Exception as exc:
        _log.warning("No se pudo parsear dwh_model para detectar miembro inferido (D21): %s", exc)
        return []

    dims_by_table = {c.table.strip().split(".")[-1].lower(): c for c in dim_contracts}
    result: list[dict] = []
    for schema in schemas:
        for field in schema.fields:
            if not (field.is_foreign_key and field.constraints.required and field.references):
                continue
            ref_table = field.references.reference_resource.strip().split(".")[-1].lower()
            dim = dims_by_table.get(ref_table)
            if dim is None:
                continue
            result.append({
                "dimension": dim.table,
                "fact_table": schema.source_name,
                "fk_column": field.name,
                "natural_keys": list(dim.natural_keys),
            })
    return result


# ─── Invariante: toda dimensión de dim_contracts tiene un step que la carga
# (docs/refactor/02-decisiones.md, D-pendiente "toda dimensión con FK tiene
# loader") ─────────────────────────────────────────────────────────────────
#
# _dims_with_inferred_member (arriba) ve DDL + dim_contracts pero nunca
# ktr_data — su salida solo alimenta el prompt (D21), nunca se re-verifica
# contra el .ktr ya emitido. apply_dimension_contracts (dimension_step_policy.py)
# ve ktr_data + dim_contracts pero nunca DDL, y sobre todo itera los STEPS que
# el modelo escribió — una dimensión sin ningún step (loader omitido del
# todo) nunca entra a ese loop, queda en silencio. Ningún camino existente
# cruza las tres fuentes (dim_contracts × ktr_data × DDL). find_unloaded_dimensions
# corre DESPUÉS de apply_dimension_contracts (que ya normalizó in-place todo
# loader real a type="DimensionLookup"/config["update"]="Y", D44/O3) — lee ese
# estado post-mutación en vez de reimplementar el BFS de rol (D16/D58).
#
# Divergencia deliberada del resto de este módulo: el docstring de arriba dice
# "un DDL no parseable degrada a []/{}, solo loggeado, nunca corta el flujo" —
# acá, además de loggear, se emite una Validacion de warning explícita. Un
# hueco de cobertura (no se pudo confirmar si falta un loader) no puede
# quedar indistinguible de "no falta ningún loader": la máxima del proyecto
# es nunca crear sin notificar, y un [] silencioso acá sería exactamente eso.
UNVERIFIED_DIMENSION_COVERAGE_FIELD = "verificacion_dimensiones"


def _dwh_ddl_parseable(dwh_ddl: str | None) -> bool:
    """True si `dwh_ddl` trae texto y parsea sin excepción. No distingue
    "vacío" de "inválido" para el caller — ambos son el mismo caso de
    degradación (no se puede clasificar severidad por FK)."""
    if not dwh_ddl or not dwh_ddl.strip():
        return False
    try:
        parse_ddl(dwh_ddl, dialect=None)
    except Exception:
        return False
    return True


def _tables_with_loader_step(
    ktr_data: dict, step_type_aliases: dict[str, str], validaciones_modelo: list,
) -> set[str]:
    """{tabla_lower} con evidencia de estar cargada: un step DimensionLookup/
    CombinationLookup con update="Y" (loader, tal como lo dejó
    apply_dimension_contracts — D44 fuerza siempre a DimensionLookup), o una
    tabla con override registrado (OVERRIDE_STEP_PREFIX) — ese caso
    apply_dimension_contracts la deja intacta a propósito (decisión explícita
    del modelo, no un hueco), así que contarla como "sin loader" sería un
    falso positivo sobre algo que ya se decidió a mano."""
    loaded: set[str] = set()
    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        if canonical not in DIMENSION_STEP_TYPES:
            continue
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        table = (cfg.get("table") or "").strip().lower()
        if not table:
            continue
        if cfg.get("update") == "Y":
            loaded.add(table)
        elif has_registered_override(validaciones_modelo, table):
            loaded.add(table)
    return loaded


def find_unloaded_dimensions(
    ktr_data: dict,
    dim_contracts: list,
    dwh_ddl: str | None,
    step_type_aliases: dict[str, str],
    validaciones_modelo: list | None = None,
) -> list[dict]:
    """Toda tabla de `dim_contracts` sin ningún step loader (ni override
    registrado) en `ktr_data`. Devuelve dicts {"tipo","campo","mensaje"}
    listos para Validacion(**v) — mismo contrato de salida que
    apply_dimension_contracts (dimension_step_policy.py), pensado para
    extender la misma lista de resultados en el caller.

    Severidad: "error" si la dimensión faltante es además referenciada por
    una FK NOT NULL desde una fact table (_dims_with_inferred_member) — ese
    caso garantiza violación del constraint o un lookup que nunca matchea en
    runtime, no es una sugerencia. El resto sale "warning" (podría ser una
    dimensión legítimamente precargada por fuera del ETL, ej. calendario).

    Nunca aborta. Si dim_contracts viene vacío, no reporta nada acá — ese
    caso ("dim_contracts se perdió del todo") ya lo cubre
    _dim_contracts_anomaly_warning, no duplicar. Si `dwh_ddl` no llega o no
    parsea, no se puede clasificar por FK — se emite un warning adicional
    diciéndolo explícitamente (ver nota de divergencia arriba) y toda
    dimensión faltante sale "warning" (nunca se asume "error" sin poder
    confirmar la FK)."""
    if not dim_contracts:
        return []

    validaciones_modelo = validaciones_modelo or []
    loaded = _tables_with_loader_step(ktr_data, step_type_aliases, validaciones_modelo)
    faltantes = [
        c for c in dim_contracts
        if c.table.strip().lower() not in loaded
    ]
    if not faltantes:
        return []

    ddl_ok = _dwh_ddl_parseable(dwh_ddl)
    findings: list[dict] = []
    if not ddl_ok:
        findings.append({
            "tipo": "warning",
            "campo": UNVERIFIED_DIMENSION_COVERAGE_FIELD,
            "mensaje": (
                "No se pudo verificar si las dimensiones de dim_contracts tienen step de carga "
                "— el DDL del DWH no llegó o no es parseable. Las "
                f"{len(faltantes)} dimensión(es) sin loader detectadas se reportan como "
                "advertencia porque no se pudo confirmar si un hecho las referencia por FK NOT NULL."
            ),
        })
        fk_by_table: dict[str, dict] = {}
    else:
        fk_by_table = {
            entry["dimension"].strip().lower(): entry
            for entry in _dims_with_inferred_member(dwh_ddl, dim_contracts)
        }

    for c in faltantes:
        table_lower = c.table.strip().lower()
        fk = fk_by_table.get(table_lower)
        if fk is not None:
            findings.append({
                "tipo": "error",
                "campo": c.table,
                "mensaje": (
                    f"dim_contracts declara '{c.table}', referenciada por FK NOT NULL "
                    f"'{fk['fact_table']}.{fk['fk_column']}', pero ningún step del .ktr la carga "
                    "(no hay DimensionLookup con update=Y sobre esa tabla). En runtime la "
                    "dimensión queda vacía salvo su fila DESCONOCIDO: el lookup de la FK no "
                    "matchea y la carga del hecho cae a la clave por defecto o viola el NOT "
                    "NULL. Agregar el step de carga en Spoon antes de ejecutar."
                ),
            })
        else:
            findings.append({
                "tipo": "warning",
                "campo": c.table,
                "mensaje": (
                    f"dim_contracts declara '{c.table}', pero ningún step del .ktr la carga "
                    "(no hay DimensionLookup con update=Y sobre esa tabla) — no se detectó una "
                    "FK NOT NULL que la referencie, así que no es necesariamente un error, pero "
                    "revisar: si esa dimensión se precarga por fuera del ETL (ej. calendario, "
                    "K18), ignorar este aviso."
                ),
            })
    return findings
