"""
D23 (docs/refactor/02-decisiones.md): validador de contrato writer→reader
entre KTRs. Compara las dos salidas REALES del LLM entre sí (lo que un KTR
escribe en una tabla vs. lo que otro KTR de la misma corrida espera leer de
esa tabla) — no usa stg_definition/dwh_model como tercera fuente de verdad
para el contenido, solo para saber qué columnas son NOT NULL en cada tabla.

Fuente de aristas escritor→lector: build_rw_matrix() (fragmentation.py),
corrida por archivo — no _resolve_table_endpoints() (lineage_builder.py).
Motivo: _resolve_table_endpoints solo matchea TableOutput/TableInput
terminales (pensado para el diagrama de linaje) y no ve un lector vía
DBLookup/DimensionLookup no-terminal. build_rw_matrix ya clasifica ese
universo más amplio (mismo que usa validate_dimension_lookup_races).

Alcance real de esta primera versión (D23 punto 3 pide "columnas + nombres +
tipos", entregado acá: nombres, con tipos como gap documentado):
  - NOMBRES: sí. Compara columnas NOT NULL sin default del DDL de la tabla
    (stg_definition o dwh_ddl, lo que la declare) contra las columnas que el
    archivo escritor realmente puebla — extraídas del propio config del step
    (column_name/table_field, no del stream), no inferidas.
  - TIPOS: NO implementado en esta versión. Un step escritor (TableOutput,
    InsertUpdate, ...) no declara tipo propio — el único tipo "real" del lado
    escritor requeriría inferencia de expresión cross-file (Calculator/
    Formula/cast en el archivo que lo produce), fuera del alcance de
    contracts.py (intra-archivo por diseño, ver fields_validate.py). Sin esa
    inferencia, comparar "tipo" sería re-empaquetar el mismo chequeo
    DDL-vs-DDL que ya hace etl_generator._type_mismatch_warnings() — que D23
    punto 1 explícitamente dice que NO cuenta como este validador (compara
    declarado contra declarado, no lo que el KTR realmente produjo). Queda
    como gap abierto, no simulado.
  - Solo extrae columnas de tabla para steps escritores con formato de config
    conocido: TableOutput, InsertUpdate, Update (ver _WRITER_TABLE_FIELD_SOURCES).
    DimensionLookup/CombinationLookup escriben tabla (build_rw_matrix ya los
    marca W/RW) pero su shape de "keys"/atributos de dimensión es distinto y
    no está mapeado acá todavía — un archivo cuya única escritura a una tabla
    sea por esos dos steps no se valida por nombre (conservador: no genera
    falso positivo, tampoco cobertura).

Severidad D15/D23-punto4: todo mismatch es texto plano, sin abortar nada —
el caller (etl_generator.py) lo promueve a Validacion tipo="error".
"""
from __future__ import annotations

from app.services.adapters.ddl_adapter import parse_ddl
from app.services.adapters.sql_table_resolver import resolve_sql_tables
from app.services.ktr_builder.contracts import normalize_config, parse_cfg
from app.services.ktr_builder.fragmentation import MatrixKey, build_rw_matrix
from app.schemas.canonical import CanonicalSchema

CONTRACT_PREFIX = "[Contrato entre KTR] "

# canonical_type -> tuplas (config_list_key, campo_columna_tabla, fallback)
# — mismas claves que ya emite output.py hacia el XML real (ver
# _step_TableOutput/_step_InsertUpdate/_step_Update en steps/output.py).
_WRITER_TABLE_FIELD_SOURCES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "TableOutput": (("fields", "column_name", "dest"),),
    "InsertUpdate": (("keys", "table_field", "field"), ("fields", "table_field", "rename")),
    "Update": (("keys", "table_field", "field"), ("fields", "table_field", "rename")),
}


def _per_file_table_roles(ktr_data: dict, step_type_aliases: dict[str, str]) -> dict[MatrixKey, str]:
    """{(conexión, tabla_lower): "R"|"W"|"RW"} — colapsa build_rw_matrix (por
    step) a nivel archivo: ¿este archivo, en conjunto, escribe/lee esta
    (conexión, tabla)? D45 punto 2: clave normalizada, no `table.lower().strip()`
    a secas — ver fragmentation.py.

    D45 punto 1 (docs/refactor/02-decisiones.md): build_rw_matrix ya resuelve
    TableInput por SQL real (resolve_sql_tables inyectado, sqlglot) — este
    módulo no es DOMAIN_MODULES (importa ddl_adapter/sqlglot libremente), así
    que pasa la implementación real directo, sin protocolo. Antes de D45 acá
    vivía un segundo resolver por regex (workaround documentado como
    deliberado en D23) que duplicaba lo que build_rw_matrix ahora hace nativo
    — "un solo resolver para los dos" (D45), se borra sin reemplazo."""
    matrix, _resolution_findings = build_rw_matrix(ktr_data, step_type_aliases, resolve_sql_tables)
    roles: dict[MatrixKey, str] = {}
    for key, step_roles in matrix.items():
        vals = set(step_roles.values())
        writes = "W" in vals or "RW" in vals
        reads = "R" in vals or "RW" in vals
        if writes and reads:
            roles[key] = "RW"
        elif writes:
            roles[key] = "W"
        elif reads:
            roles[key] = "R"
    return roles


def _writer_table_columns(canonical: str, cfg: dict) -> set[str] | None:
    """Columnas de TABLA (no de stream) que este step puebla. None si el tipo
    de step no tiene shape de config relevado acá (ver módulo docstring)."""
    sources = _WRITER_TABLE_FIELD_SOURCES.get(canonical)
    if sources is None:
        return None
    cols: set[str] = set()
    for list_key, primary_key, fallback_key in sources:
        for item in cfg.get(list_key, []) or []:
            if not isinstance(item, dict):
                continue
            val = item.get(primary_key) or item.get(fallback_key)
            if val:
                cols.add(str(val).strip().lower())
    return cols


def _table_columns_written(ktr_data: dict, step_type_aliases: dict[str, str], table: str) -> set[str] | None:
    """Unión de columnas de tabla escritas por TODOS los steps de `ktr_data`
    que escriben `table` y tienen shape soportado. None si ningún step que
    toca `table` en rol de escritura tiene shape soportado (no valida por
    nombre en ese caso — conservador, ver módulo docstring)."""
    found_supported = False
    cols: set[str] = set()
    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        step_table = (cfg.get("table") or "").strip().lower()
        if step_table != table:
            continue
        extracted = _writer_table_columns(canonical, cfg)
        if extracted is None:
            continue
        found_supported = True
        cols |= extracted
    return cols if found_supported else None


def _find_table_schema(ddl: str, table: str) -> CanonicalSchema | None:
    """Busca `table` (nombre, sin schema) entre los CREATE TABLE de `ddl`.
    Best-effort: DDL no parseable o tabla no encontrada -> None, sin excepción."""
    if not ddl or not ddl.strip():
        return None
    try:
        schemas = parse_ddl(ddl, dialect=None)
    except Exception:
        return None
    target = table.strip().lower().split(".")[-1]
    for schema in schemas:
        if schema.source_name.strip().lower().split(".")[-1] == target:
            return schema
    return None


def _required_columns(schema: CanonicalSchema) -> dict[str, str]:
    """{columna_lower: CanonicalType.value} de columnas NOT NULL sin default
    — mismo filtro que etl_generator._required_columns_from_ddl()."""
    return {
        f.name.strip().lower(): f.type.value
        for f in schema.fields
        if f.constraints.required and f.default_kind is None
    }


def validate_ktr_contracts(
    ktr_data_list: list[dict],
    stg_ddl: str,
    dwh_ddl: str,
    step_type_aliases: dict[str, str],
) -> list[str]:
    """Por cada tabla tocada por más de un archivo (uno la escribe, otro la
    lee — D23 punto 1: cualquier par, no solo adyacentes), compara columnas
    NOT NULL de la tabla (DDL) contra columnas realmente escritas por el
    archivo escritor. Mensajes SIN CONTRACT_PREFIX — el caller decide cómo
    promoverlos (mismo patrón que FIELD_INTEGRITY_PREFIX en fields_validate.py)."""
    if len(ktr_data_list) < 2:
        return []

    roles_by_file = [_per_file_table_roles(k, step_type_aliases) for k in ktr_data_list]
    keys = {k for roles in roles_by_file for k in roles}

    messages: list[str] = []
    for key in sorted(keys):
        _connection, table = key
        writer_files = [i for i, r in enumerate(roles_by_file) if r.get(key) in ("W", "RW")]
        reader_files = [j for j, r in enumerate(roles_by_file) if r.get(key) in ("R", "RW")]
        if not writer_files or not reader_files:
            continue

        schema = _find_table_schema(stg_ddl, table) or _find_table_schema(dwh_ddl, table)
        if schema is None:
            continue
        required = _required_columns(schema)
        if not required:
            continue

        for i in writer_files:
            for j in reader_files:
                if i == j:
                    continue
                writer_cols = _table_columns_written(ktr_data_list[i], step_type_aliases, table)
                if writer_cols is None:
                    continue
                missing = set(required) - writer_cols
                for col in sorted(missing):
                    messages.append(
                        f"Tabla '{table}': columna '{col}' ({required[col]}, NOT NULL sin default) "
                        f"requerida por archivo {j} no está entre lo que archivo {i} realmente escribe."
                    )
    return messages
