"""
Builds ModelContext from origin tables.

Four paths, all routed through CanonicalSchema:
  DB source        (connection_id set)    → _profile_from_db()
  File source      (canonical_schema set) → canonical_schema used directly
  DDL source       (canonical_schema set, source_type="ddl") → same as file
  Formulario/manual (none of the above)  → _schema_from_columnas_origen()

format_model_context_for_prompt() is the ONLY exit point that serializes
table context into a prompt string. All services must go through it.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.schemas.canonical import CanonicalField, CanonicalSchema, CanonicalType, TableProfile
from app.schemas.context_schemas import ModelContext, ModelTableContext
from app.services import profiler as profiler_svc
from app.services.adapters import db_adapter
from app.services.adapters.schema_to_context import canonical_to_model_context

logger = logging.getLogger(__name__)

# ─── DEBUG: filtrado de contexto ──────────────────────────────────────────────
# Para activar el log de lo que entra y sale de format_model_context_for_prompt,
# descomenta la línea siguiente. Para quitar el feature, borra este bloque y los
# dos bloques "if _DEBUG_CONTEXT_FILTER" dentro de la función de abajo.
# 
# ─────────────────────────────────────────────────────────────────────────────

# Frontend dataType strings → CanonicalType.
# Used in the formulario path and the DB fallback.
_FRONTEND_TO_CANONICAL: dict[str, CanonicalType] = {
    "int":      CanonicalType.INTEGER,
    "integer":  CanonicalType.INTEGER,
    "float":    CanonicalType.NUMBER,
    "number":   CanonicalType.NUMBER,
    "decimal":  CanonicalType.NUMBER,
    "numeric":  CanonicalType.NUMBER,
    "bool":     CanonicalType.BOOLEAN,
    "boolean":  CanonicalType.BOOLEAN,
    "date":     CanonicalType.DATE,
    "datetime": CanonicalType.DATETIME,
    "time":     CanonicalType.TIME,
    "string":   CanonicalType.STRING,
    "text":     CanonicalType.STRING,
}


def _map_frontend_type(dt: str) -> CanonicalType:
    return _FRONTEND_TO_CANONICAL.get((dt or "").lower(), CanonicalType.UNKNOWN)


# ─── DB path ──────────────────────────────────────────────────────────────────

def _profile_from_db(table, db: Session) -> CanonicalSchema:
    """
    Fetch structural schema from INFORMATION_SCHEMA and stats from the profiler.
    Returns a CanonicalSchema with the statistical profile embedded in schema.profile.
    Falls back to _schema_from_columnas_origen() on any connectivity or query error.
    """
    from app.models.connection import Connection
    from app.services.db_connector import get_columns, get_foreign_keys, get_sample_rows

    try:
        conn_uuid = uuid.UUID(table.connection_id)
    except (ValueError, AttributeError):
        logger.warning("Invalid connection_id '%s'; using formulario fallback", table.connection_id)
        return _schema_from_columnas_origen(table, source_type="database")

    conn = db.get(Connection, conn_uuid)
    if conn is None:
        logger.warning("Connection %s not found; using formulario fallback", table.connection_id)
        return _schema_from_columnas_origen(table, source_type="database")

    schema = table.schema_name or ""
    tname  = table.tableName
    if "." in tname and not schema:
        schema, _, tname = tname.partition(".")

    qualified = f"{schema}.{tname}" if schema else tname

    try:
        col_infos = get_columns(conn, qualified)
        fk_map    = get_foreign_keys(conn, [qualified])
        fk_refs   = fk_map.get(qualified, [])

        col_names     = [ci.name for ci in col_infos]
        stats         = profiler_svc.fetch_db_column_stats(conn, schema, tname, col_names)
        sample_result = get_sample_rows(conn, schema, tname, limit=20)
        logger.debug("sample bias for %s: %s", qualified, sample_result.bias)
        profiles = profiler_svc.profile_columns(col_names, stats, sample_result.rows)

        return db_adapter.build(
            col_infos,
            qualified,
            fk_refs=fk_refs,
            profile=TableProfile(column_profiles=profiles),
        )
    except Exception as exc:
        logger.warning(
            "DB profiling failed for %s: %s; using formulario fallback", qualified, exc
        )
        return _schema_from_columnas_origen(table, source_type="database")


# ─── Formulario / fallback path ───────────────────────────────────────────────

def _schema_from_columnas_origen(
    table,
    source_type: str = "database",
) -> CanonicalSchema:
    """
    Build a CanonicalSchema from ColumnaOrigen objects.

    Used for:
      - Manual form entry (InputFormulario): columns defined by the user.
      - DB fallback: when INFORMATION_SCHEMA is unreachable.

    Fields carry inferred_by="user". No statistical profile — stats are
    unknown for this source, so the prompt will show names and types only.
    """
    fields = [
        CanonicalField(
            name=c.name,
            type=_map_frontend_type(c.dataType),
            inferred_by="user",
        )
        for c in table.columns
    ]
    return CanonicalSchema(
        source_name=table.tableName,
        source_type=source_type,  # type: ignore[arg-type]
        fields=fields,
    )


# ─── ModelContext builder ─────────────────────────────────────────────────────

def build_model_context(tables: list, db: Optional[Session] = None) -> ModelContext:
    """
    Routes each table to the appropriate CanonicalSchema builder, then converts
    to ModelContext via canonical_to_model_context().

    DB path          (connection_id set)    → _profile_from_db()
    File/DDL path    (canonical_schema set) → canonical_schema used directly
    Formulario path  (neither)              → _schema_from_columnas_origen()
    """
    model_tables: list[ModelTableContext] = []
    for table in tables:
        if getattr(table, "connection_id", None) and db is not None:
            canonical = _profile_from_db(table, db)
        elif getattr(table, "canonical_schema", None) is not None:
            canonical = table.canonical_schema
        else:
            canonical = _schema_from_columnas_origen(table)

        ctx = canonical_to_model_context([canonical])
        model_tables.extend(ctx.source_tables)

    return ModelContext(source_tables=model_tables)


# ─── Whitelist serializer — ONLY exit point to prompt strings ─────────────────

def format_model_context_for_prompt(ctx: ModelContext) -> str:
    """
    Serializes ModelContext to the text that appears inside a prompt.

    WHITELIST — only these ColumnProfile fields are written:
      name, inferred_type, null_pct, distinct_count,
      leading_trailing_spaces_pct, casing_distribution,
      min_length, max_length, format_hint, masked_examples.

    Absent: connection_id, raw data values, InternalTableRef, InternalContext.
    """

    lines: list[str] = []
    for t in ctx.source_tables:
        lines.append(f"\n  Tabla: {t.table_name}")
        for col in t.columns:
            parts = [f"    - {col.name}"]
            parts.append(f"tipo: {col.inferred_type}")
            parts.append(f"nulos: {col.null_pct:.1%}")
            parts.append(f"distintos: {col.distinct_count}")
            if col.leading_trailing_spaces_pct > 0:
                parts.append(f"espacios_borde: {col.leading_trailing_spaces_pct:.1%}")
            if col.casing_distribution:
                casing_str = ", ".join(
                    f"{k}: {v:.0%}" for k, v in col.casing_distribution.items()
                )
                parts.append(f"casing: {casing_str}")
            if col.min_length is not None and col.max_length is not None:
                parts.append(f"largo: {col.min_length}–{col.max_length} chars")
            if col.format_hint:
                parts.append(f"formato: {col.format_hint}")
            if col.masked_examples:
                parts.append(f"ejemplos: {', '.join(col.masked_examples)}")
            lines.append(" | ".join(parts))

    return "\n".join(lines)
