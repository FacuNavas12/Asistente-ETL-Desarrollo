"""Implementación real (sqlglot) del contrato `SqlTableResolver`
(app/domain/sql_resolution.py) — D45 punto 1 (docs/refactor/02-decisiones.md).
Resuelve el/los `TableInput.sql` y `ExecSQL` de un KTR a tabla(s) real(es)
para que `fragmentation.build_rw_matrix` deje de tratarlos como invisibles.

Mismo motor (`sqlglot`) que `adapters/ddl_adapter.py`, pero acá se parsea DML
(SELECT/TRUNCATE/INSERT/UPDATE/DELETE/CREATE) en vez de DDL de columnas."""
from __future__ import annotations

import logging

import sqlglot
from sqlglot import exp

from app.domain.sql_resolution import SqlResolution

logger = logging.getLogger(__name__)

# Statement de escritura sqlglot -> operación (mismo vocabulario que
# `ExecSQL` necesita clasificar: TRUNCATE/INSERT/UPDATE/DELETE/CREATE).
_WRITE_OPS: tuple[tuple[type, str], ...] = (
    (exp.TruncateTable, "TRUNCATE"),
    (exp.Insert, "INSERT"),
    (exp.Update, "UPDATE"),
    (exp.Delete, "DELETE"),
    (exp.Create, "CREATE"),
)


def _table_name(t: exp.Table) -> str:
    return f"{t.db}.{t.name}".lower() if t.db else t.name.lower()


def _select_columns(select: exp.Select) -> frozenset[str] | None:
    """Mismo criterio que ktr_builder/contracts.py:_select_columns — SELECT *
    o cualquier expresión sin alias resoluble pierde certeza para TODO el
    SELECT (None), no solo para esa columna."""
    cols: set[str] = set()
    for e in select.expressions:
        if isinstance(e, exp.Star):
            return None
        alias = e.alias_or_name
        if not alias or alias == "*":
            return None
        cols.add(alias)
    return frozenset(cols) if cols else None


def resolve_sql_tables(sql: str, dialect: str | None = None) -> SqlResolution:
    """Best-effort (D15): SQL no parseable -> SqlResolution con `error`, nunca
    levanta excepción — el caller (fragmentation, vía el callable inyectado)
    decide qué Finding emitir."""
    if not sql or not sql.strip():
        return SqlResolution(tables=frozenset(), error="SQL vacío")

    try:
        statements = [s for s in sqlglot.parse(sql, dialect=dialect or None) if s is not None]
    except Exception as exc:
        return SqlResolution(tables=frozenset(), error=f"Error de sintaxis SQL: {exc}")

    if not statements:
        return SqlResolution(tables=frozenset(), error="SQL sin statements reconocibles")

    tables: set[str] = set()
    operation: str | None = None
    columns: frozenset[str] | None = None
    for stmt in statements:
        for op_type, op_label in _WRITE_OPS:
            if isinstance(stmt, op_type):
                operation = op_label
                break
        for t in stmt.find_all(exp.Table):
            tables.add(_table_name(t))
        if isinstance(stmt, exp.Select):
            columns = _select_columns(stmt)

    if not tables:
        return SqlResolution(
            tables=frozenset(), operation=operation,
            error="Sin tabla reconocible en el SQL (statement válido, pero sin FROM/tabla afectada)",
        )
    return SqlResolution(tables=frozenset(tables), operation=operation, columns=columns)
