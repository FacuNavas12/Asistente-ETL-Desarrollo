"""
Builds ModelContext from origin tables.

Bifurcation:
  DB source   (table.connection_id is set) → fetch stats via SQL + random sample from DB
  File source (no connection_id)           → use .data from request columns

format_model_context_for_prompt() is the ONLY exit point that serializes
table context into a prompt string. All services must go through it.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.schemas.context_schemas import ColumnProfile, ColumnStats, ModelContext, ModelTableContext
from app.services import profiler as profiler_svc

logger = logging.getLogger(__name__)


# ─── DB path ──────────────────────────────────────────────────────────────────

def _profile_from_db(table, db: Session) -> list[ColumnProfile]:
    """Fetch population stats via SQL + random sample, then profile."""
    from app.models.connection import Connection
    from app.services.db_connector import get_sample_rows

    try:
        conn_uuid = uuid.UUID(table.connection_id)
    except (ValueError, AttributeError):
        logger.warning("Invalid connection_id '%s'; falling back to memory", table.connection_id)
        return _profile_from_memory(table)

    conn = db.get(Connection, conn_uuid)
    if conn is None:
        logger.warning("Connection %s not found; falling back to memory", table.connection_id)
        return _profile_from_memory(table)

    # Resolve schema and table name.
    schema = table.schema_name or ""
    tname  = table.tableName
    if "." in tname and not schema:
        schema, _, tname = tname.partition(".")

    col_names = [c.name for c in table.columns]

    try:
        stats         = profiler_svc.fetch_column_stats(conn, schema, tname, col_names)
        sample_result = get_sample_rows(conn, schema, tname, limit=20)
        logger.debug("sample bias for %s.%s: %s", schema, tname, sample_result.bias)
        return profiler_svc.profile_columns(col_names, stats, sample_result.rows)
    except Exception as exc:
        logger.warning("DB profiling failed for %s: %s; using memory fallback", table.tableName, exc)
        return _profile_from_memory(table)


# ─── Memory path (CSV / Excel / manual entry) ────────────────────────────────

def _map_datatype(dt: str) -> str:
    t = (dt or "").lower()
    if any(t.startswith(k) for k in ("int", "bigint", "smallint", "serial")):
        return "int"
    if any(t.startswith(k) for k in ("float", "double", "decimal", "numeric", "real", "money")):
        return "float"
    if t in ("bool", "boolean"):
        return "bool"
    if any(t.startswith(k) for k in ("date", "datetime", "timestamp", "time")):
        return "date"
    return "string"


def _profile_from_memory(table) -> list[ColumnProfile]:
    """Use .data from request columns as both population source and sample."""
    col_names = [c.name for c in table.columns]
    col_data  = [list(c.data or []) for c in table.columns]
    max_rows  = max((len(d) for d in col_data), default=0)

    if max_rows == 0:
        return [
            ColumnProfile(
                name=c.name,
                inferred_type=_map_datatype(c.dataType),
                null_pct=0.0,
                distinct_count=0,
                leading_trailing_spaces_pct=0.0,
                casing_distribution={},
            )
            for c in table.columns
        ]

    all_rows = [
        [col_data[ci][ri] if ri < len(col_data[ci]) else None
         for ci in range(len(col_names))]
        for ri in range(max_rows)
    ]

    stats       = profiler_svc.compute_stats_from_memory(col_names, all_rows)
    sample_rows = all_rows[:20]
    return profiler_svc.profile_columns(col_names, stats, sample_rows)


# ─── ModelContext builder (bifurcation) ───────────────────────────────────────

def build_model_context(tables: list, db: Optional[Session] = None) -> ModelContext:
    """
    Routes each table to DB or memory profiling.
    InternalTableRef is derived internally and never included in ModelContext.
    """
    model_tables: list[ModelTableContext] = []
    for table in tables:
        if getattr(table, "connection_id", None) and db is not None:
            profiles = _profile_from_db(table, db)
        else:
            profiles = _profile_from_memory(table)

        model_tables.append(ModelTableContext(
            table_name=table.tableName,
            columns=profiles,
        ))
    return ModelContext(source_tables=model_tables)


# ─── Whitelist serializer — ONLY exit point to prompt strings ─────────────────

def format_model_context_for_prompt(ctx: ModelContext) -> str:
    """
    Serializes ModelContext to the text that appears inside a prompt.

    WHITELIST — only these fields from ColumnProfile are written:
      name, inferred_type, null_pct, distinct_count,
      leading_trailing_spaces_pct, casing_distribution,
      min_length, max_length, format_hint, masked_examples.

    Absent: connection_id, raw .data values, InternalTableRef, InternalContext.
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
