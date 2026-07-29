"""
Adapter: sqlglot AST → list[CanonicalSchema] (source_type="ddl").

Converts each CREATE TABLE statement found in a parsed DDL into a CanonicalSchema.
Unknown or proprietary types map to CanonicalType.UNKNOWN — never raise.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

import sqlglot
from sqlglot import exp
from sqlglot.expressions import DataType as DT

from app.schemas.canonical import (
    CanonicalField,
    CanonicalSchema,
    CanonicalType,
    FieldConstraints,
    FieldFormat,
    ForeignKeyRef,
)
from app.services.sql_defaults import looks_like_sql_function

logger = logging.getLogger(__name__)

# ── Type mapping: sqlglot DataType.Type → CanonicalType ──────────────────────

_SQLGLOT_TYPE_MAP: dict[DT.Type, CanonicalType] = {
    # Integer
    DT.Type.INT:         CanonicalType.INTEGER,
    DT.Type.BIGINT:      CanonicalType.INTEGER,
    DT.Type.SMALLINT:    CanonicalType.INTEGER,
    DT.Type.TINYINT:     CanonicalType.INTEGER,
    DT.Type.MEDIUMINT:   CanonicalType.INTEGER,
    DT.Type.SERIAL:      CanonicalType.INTEGER,
    DT.Type.BIGSERIAL:   CanonicalType.INTEGER,
    DT.Type.SMALLSERIAL: CanonicalType.INTEGER,
    DT.Type.INT128:      CanonicalType.INTEGER,
    DT.Type.INT256:      CanonicalType.INTEGER,
    DT.Type.UBIGINT:     CanonicalType.INTEGER,
    DT.Type.UINT:        CanonicalType.INTEGER,
    DT.Type.USMALLINT:   CanonicalType.INTEGER,
    DT.Type.UTINYINT:    CanonicalType.INTEGER,
    # Number
    DT.Type.DECIMAL:     CanonicalType.NUMBER,
    DT.Type.FLOAT:       CanonicalType.NUMBER,
    DT.Type.DOUBLE:      CanonicalType.NUMBER,
    DT.Type.MONEY:       CanonicalType.NUMBER,
    DT.Type.SMALLMONEY:  CanonicalType.NUMBER,
    DT.Type.BIGDECIMAL:  CanonicalType.NUMBER,
    DT.Type.UDECIMAL:    CanonicalType.NUMBER,
    DT.Type.UDOUBLE:     CanonicalType.NUMBER,
    # String
    DT.Type.VARCHAR:     CanonicalType.STRING,
    DT.Type.CHAR:        CanonicalType.STRING,
    DT.Type.NVARCHAR:    CanonicalType.STRING,
    DT.Type.NCHAR:       CanonicalType.STRING,
    DT.Type.TEXT:        CanonicalType.STRING,
    DT.Type.TINYTEXT:    CanonicalType.STRING,
    DT.Type.MEDIUMTEXT:  CanonicalType.STRING,
    DT.Type.LONGTEXT:    CanonicalType.STRING,
    DT.Type.NAME:        CanonicalType.STRING,
    DT.Type.BPCHAR:      CanonicalType.STRING,
    DT.Type.UUID:        CanonicalType.STRING,
    # Boolean
    DT.Type.BOOLEAN:     CanonicalType.BOOLEAN,
    DT.Type.BIT:         CanonicalType.BOOLEAN,
    # Date / Time / Datetime
    DT.Type.DATE:        CanonicalType.DATE,
    DT.Type.TIME:        CanonicalType.TIME,
    DT.Type.TIMETZ:      CanonicalType.TIME,
    DT.Type.TIMESTAMP:   CanonicalType.DATETIME,
    DT.Type.TIMESTAMPTZ: CanonicalType.DATETIME,
    DT.Type.DATETIME:    CanonicalType.DATETIME,
    DT.Type.DATETIME2:   CanonicalType.DATETIME,
    DT.Type.SMALLDATETIME: CanonicalType.DATETIME,
    # Object / Binary / Array
    DT.Type.JSON:        CanonicalType.OBJECT,
    DT.Type.JSONB:       CanonicalType.OBJECT,
    DT.Type.XML:         CanonicalType.OBJECT,
    DT.Type.HSTORE:      CanonicalType.OBJECT,
    DT.Type.BINARY:      CanonicalType.BINARY,
    DT.Type.VARBINARY:   CanonicalType.BINARY,
    DT.Type.BLOB:        CanonicalType.BINARY,
    DT.Type.LONGBLOB:    CanonicalType.BINARY,
    DT.Type.MEDIUMBLOB:  CanonicalType.BINARY,
    DT.Type.TINYBLOB:    CanonicalType.BINARY,
    DT.Type.IMAGE:       CanonicalType.BINARY,
    DT.Type.ROWVERSION:  CanonicalType.BINARY,
    DT.Type.ARRAY:       CanonicalType.ARRAY,
}

# UUID types get format="uuid"
_UUID_SQLGLOT_TYPES: frozenset[DT.Type] = frozenset({DT.Type.UUID})

# Numeric types where the first DataTypeParam is precision (not length)
_PRECISION_SQLGLOT_TYPES: frozenset[DT.Type] = frozenset({
    DT.Type.DECIMAL, DT.Type.FLOAT, DT.Type.DOUBLE,
    DT.Type.BIGDECIMAL,
})

# String/binary types where the first DataTypeParam is length
_LENGTH_SQLGLOT_TYPES: frozenset[DT.Type] = frozenset({
    DT.Type.VARCHAR, DT.Type.CHAR, DT.Type.NVARCHAR, DT.Type.NCHAR,
    DT.Type.BINARY, DT.Type.VARBINARY, DT.Type.BPCHAR,
})


# ── Public API ────────────────────────────────────────────────────────────────

def parse_ddl(ddl: str, dialect: str | None) -> list[CanonicalSchema]:
    """
    Parse a DDL string (one or more CREATE TABLE statements) and return
    one CanonicalSchema per table found.

    Args:
        ddl:     Raw DDL text. May contain multiple CREATE TABLE statements.
        dialect: sqlglot dialect string ("postgres", "tsql", "mysql") or None for ANSI.

    Returns:
        list[CanonicalSchema] — empty if no CREATE TABLE found.
        Unknown types produce CanonicalType.UNKNOWN and a log warning (no exception).
    """
    try:
        statements = sqlglot.parse(ddl, dialect=dialect or None)
    except Exception as exc:
        raise ValueError(f"Error de sintaxis SQL: {exc}") from exc

    schemas: list[CanonicalSchema] = []
    for stmt in statements:
        if not isinstance(stmt, exp.Create) or stmt.kind != "TABLE":
            continue
        try:
            schema = _create_table_to_schema(stmt, dialect)
            schemas.append(schema)
        except Exception as exc:
            logger.warning("Error procesando CREATE TABLE: %s", exc)

    return schemas


# ── Internal helpers ──────────────────────────────────────────────────────────

# Comparaciones simples que un CHECK puede expresar sobre una sola columna
# (`col OP literal`, en cualquier orden de operandos). Acumuladas como
# (tipo_de_nodo_sqlglot, literal_crudo) por nombre de columna en minúsculas.
_ComparisonList = list[tuple[type, str]]

# `col OP lit` cuando la columna quedó del lado derecho (`lit OP col`) es
# equivalente a invertir el operador: `0 <= precio` === `precio >= 0`.
_MIRROR_OP: dict[type, type] = {
    exp.GTE: exp.LTE,
    exp.LTE: exp.GTE,
    exp.GT: exp.LT,
    exp.LT: exp.GT,
}


def _unwrap_table_level_constraint(expr: exp.Expression) -> exp.Expression:
    """`CONSTRAINT nombre PRIMARY KEY(...)/FOREIGN KEY(...)/CHECK(...)` llega
    de sqlglot como `exp.Constraint` envolviendo el nodo real en
    `.expressions[0]` — sin desenvolver, un PK/FK/CHECK nombrado es
    indistinguible de cualquier otro constraint no reconocido y se pierde en
    silencio (bug real, confirmado contra DDL con constraints 100% nombrados).
    Sin nombre, sqlglot ya entrega el nodo directo y esta función es un
    pass-through."""
    if isinstance(expr, exp.Constraint) and expr.expressions:
        return expr.expressions[0]
    return expr


def _normalize_comparison(condition: exp.Expression) -> tuple[str, str, type] | None:
    """Para un nodo GTE/LTE/GT/LT, devuelve (columna, literal, tipo_operador)
    reescribiendo el operador si la columna quedó del lado derecho. None si
    alguno de los 2 lados no es una columna o un literal simple (ej.
    columna-vs-columna, columna-vs-función) — esos casos no tienen forma de
    reducirse a un solo valor de `minimum`/`maximum`."""
    left, right = condition.this, condition.expression
    op_type = type(condition)
    if isinstance(left, exp.Column) and isinstance(right, exp.Literal):
        return left.this.name, right.this, op_type
    if isinstance(right, exp.Column) and isinstance(left, exp.Literal):
        return right.this.name, left.this, _MIRROR_OP[op_type]
    return None


def _collect_condition_constraints(
    condition: exp.Expression,
    bounds: dict[str, _ComparisonList],
    enums: dict[str, list[str]],
) -> None:
    """Camina la condición de un CHECK (recursivo en AND) y acumula
    comparaciones columna-vs-literal en `bounds` y valores de `IN` en
    `enums`, por nombre de columna en minúsculas. Todo lo que no matchea un
    patrón soportado (OR, funciones, columna-vs-columna, subqueries) se
    loggea y se descarta — best-effort, nunca levanta excepción ni corta el
    parseo del resto del DDL."""
    if isinstance(condition, exp.And):
        _collect_condition_constraints(condition.this, bounds, enums)
        _collect_condition_constraints(condition.expression, bounds, enums)
        return

    if isinstance(condition, exp.Between):
        col, low, high = condition.this, condition.args.get("low"), condition.args.get("high")
        if isinstance(col, exp.Column) and isinstance(low, exp.Literal) and isinstance(high, exp.Literal):
            name = col.this.name.lower()
            bounds[name].append((exp.GTE, low.this))
            bounds[name].append((exp.LTE, high.this))
        else:
            logger.info("CHECK con BETWEEN no soportado, se descarta: %s", condition.sql())
        return

    if isinstance(condition, exp.In):
        col, values = condition.this, condition.expressions
        if isinstance(col, exp.Column) and values and all(isinstance(v, exp.Literal) for v in values):
            enums[col.this.name.lower()].extend(v.this for v in values)
        else:
            logger.info("CHECK con IN no soportado (no son todos literales), se descarta: %s", condition.sql())
        return

    if isinstance(condition, (exp.GTE, exp.LTE, exp.GT, exp.LT)):
        normalized = _normalize_comparison(condition)
        if normalized is not None:
            col_name, literal, op_type = normalized
            bounds[col_name.lower()].append((op_type, literal))
        else:
            logger.info("CHECK con comparación no soportada (no es columna-vs-literal), se descarta: %s", condition.sql())
        return

    logger.info("CHECK con forma no soportada (%s), se descarta: %s", type(condition).__name__, condition.sql())


def _resolve_field_bounds(
    col_name: str,
    canonical_type: CanonicalType,
    comparisons: _ComparisonList,
    enum_values: list[str],
) -> tuple[Optional[str], Optional[str], Optional[list[str]]]:
    """Traduce las comparaciones crudas acumuladas para una columna a
    `minimum`/`maximum`. Operadores estrictos (`>`/`<`) solo se ajustan para
    `INTEGER` (siguiente/anterior entero, `+1`/`-1`) — para `NUMBER` no hay
    "próximo valor" sin conocer la escala del tipo, se descarta y se loggea
    (diferido, ver docs/refactor/01-hallazgos.md H38)."""
    minimum: Optional[str] = None
    maximum: Optional[str] = None
    for op_type, literal in comparisons:
        value = literal
        if op_type in (exp.GT, exp.LT):
            if canonical_type != CanonicalType.INTEGER:
                logger.info(
                    "CHECK estricto (%s) sobre '%s' de tipo %s — ajuste solo soportado para INTEGER, se descarta",
                    "> " if op_type is exp.GT else "<", col_name, canonical_type,
                )
                continue
            try:
                value = str(int(literal) + (1 if op_type is exp.GT else -1))
            except ValueError:
                logger.info("CHECK estricto sobre '%s' con literal no entero, se descarta: %s", col_name, literal)
                continue
        if op_type in (exp.GTE, exp.GT):
            minimum = value
        else:
            maximum = value

    enum = sorted(set(enum_values)) if enum_values else None
    return minimum, maximum, enum


def _create_table_to_schema(stmt: exp.Create, dialect: str | None) -> CanonicalSchema:
    tbl_expr = stmt.this   # Schema (with cols) or Table (no cols)
    tbl      = tbl_expr.this if isinstance(tbl_expr, exp.Schema) else tbl_expr

    source_name = f"{tbl.db}.{tbl.name}" if tbl.db else tbl.name
    col_exprs   = tbl_expr.expressions if isinstance(tbl_expr, exp.Schema) else []

    # ── Collect table-level PKs/FKs/CHECKs ────────────────────────────────────
    # Un constraint NOMBRADO (`CONSTRAINT x PRIMARY KEY/FOREIGN KEY/CHECK(...)`)
    # llega envuelto en exp.Constraint — hay que desenvolverlo antes de mirar
    # el tipo real, si no, PK/FK/CHECK nombrados se pierden en silencio.
    table_pk_cols: set[str] = set()
    table_fk_refs: list[ForeignKeyRef] = []
    table_level_bounds: dict[str, _ComparisonList] = defaultdict(list)
    table_level_enums: dict[str, list[str]] = defaultdict(list)

    for raw_expr in col_exprs:
        expr = _unwrap_table_level_constraint(raw_expr)
        if isinstance(expr, exp.PrimaryKey):
            table_pk_cols.update(c.name for c in expr.expressions)
        elif isinstance(expr, exp.ForeignKey):
            fk_ref = _extract_fk_ref(expr)
            if fk_ref:
                table_fk_refs.append(fk_ref)
        elif isinstance(expr, exp.CheckColumnConstraint):
            _collect_condition_constraints(expr.this, table_level_bounds, table_level_enums)

    # ── Build FK lookup: column → ForeignKeyRef ───────────────────────────────
    fk_by_col: dict[str, ForeignKeyRef] = {}
    for fk in table_fk_refs:
        for col_name in fk.fields:
            fk_by_col[col_name] = fk

    # ── Build fields ──────────────────────────────────────────────────────────
    fields: list[CanonicalField] = []
    for expr in col_exprs:
        if not isinstance(expr, exp.ColumnDef):
            continue
        field = _col_def_to_field(
            expr, table_pk_cols, fk_by_col, table_level_bounds, table_level_enums, dialect,
        )
        fields.append(field)

    pk_cols = [f.name for f in fields if f.is_primary_key]

    return CanonicalSchema(
        source_name=source_name,
        source_type="ddl",
        fields=fields,
        primary_key=pk_cols,
        foreign_keys=table_fk_refs,
    )


def _col_def_to_field(
    col_def: exp.ColumnDef,
    table_pk_cols: set[str],
    fk_by_col: dict[str, ForeignKeyRef],
    table_level_bounds: dict[str, _ComparisonList],
    table_level_enums: dict[str, list[str]],
    dialect: str | None = None,
) -> CanonicalField:
    col_name = col_def.this.name
    dtype    = col_def.kind

    canonical_type = CanonicalType.UNKNOWN
    fmt: FieldFormat = "default"
    precision: Optional[int] = None
    scale:     Optional[int] = None
    length:    Optional[int] = None
    is_not_null = False
    is_pk       = col_name in table_pk_cols
    default_expr: Optional[str] = None
    default_kind: Optional[str] = None

    if dtype is not None:
        dtype_type = dtype.this
        canonical_type = _SQLGLOT_TYPE_MAP.get(dtype_type, CanonicalType.UNKNOWN)

        if canonical_type == CanonicalType.UNKNOWN and dtype_type not in (
            DT.Type.NULL, DT.Type.UNKNOWN, DT.Type.USERDEFINED,
        ):
            logger.warning("Tipo SQL no reconocido: %s → UNKNOWN", dtype_type)

        if dtype_type in _UUID_SQLGLOT_TYPES:
            fmt = "uuid"

        params = dtype.expressions
        if params:
            if dtype_type in _PRECISION_SQLGLOT_TYPES:
                precision = _int_param(params, 0)
                scale     = _int_param(params, 1)
            elif dtype_type in _LENGTH_SQLGLOT_TYPES:
                length = _int_param(params, 0)

    # Inline column constraints
    col_bounds: dict[str, _ComparisonList] = defaultdict(list)
    col_enums: dict[str, list[str]] = defaultdict(list)
    for constraint in col_def.constraints:
        if isinstance(constraint.kind, exp.NotNullColumnConstraint):
            is_not_null = True
        if isinstance(constraint.kind, exp.PrimaryKeyColumnConstraint):
            is_pk = True
        if isinstance(constraint.kind, exp.DefaultColumnConstraint):
            default_node = constraint.kind.this
            if default_node is not None:
                try:
                    default_expr = default_node.sql(dialect=dialect or None)
                except Exception:
                    default_expr = str(default_node)
                is_function  = isinstance(default_node, exp.Func) or looks_like_sql_function(default_expr)
                default_kind = "function" if is_function else "literal"
        if isinstance(constraint.kind, exp.CheckColumnConstraint):
            _collect_condition_constraints(constraint.kind.this, col_bounds, col_enums)

    name_lower = col_name.lower()
    comparisons = table_level_bounds.get(name_lower, []) + col_bounds.get(name_lower, [])
    enum_values = table_level_enums.get(name_lower, []) + col_enums.get(name_lower, [])
    minimum, maximum, enum = _resolve_field_bounds(col_name, canonical_type, comparisons, enum_values)

    return CanonicalField(
        name=col_name,
        type=canonical_type,
        format=fmt,
        precision=precision,
        scale=scale,
        length=length,
        constraints=FieldConstraints(
            required=is_not_null or is_pk, minimum=minimum, maximum=maximum, enum=enum,
        ),
        is_primary_key=is_pk,
        is_foreign_key=col_name in fk_by_col,
        references=fk_by_col.get(col_name),
        inferred_by="ddl",
        default_expr=default_expr,
        default_kind=default_kind,  # type: ignore[arg-type]
    )


def _int_param(params: list, idx: int) -> Optional[int]:
    try:
        return int(params[idx].this.this)
    except (IndexError, TypeError, ValueError):
        return None


def _extract_fk_ref(expr: exp.ForeignKey) -> Optional[ForeignKeyRef]:
    """Extract a ForeignKeyRef from a table-level FOREIGN KEY constraint."""
    try:
        fk_cols = [c.name for c in expr.expressions]
        ref     = expr.args.get("reference")
        if ref is None or not fk_cols:
            return None

        # ref is a Reference expression; its .this is a Schema or Table
        ref_tbl = ref.this
        if isinstance(ref_tbl, exp.Schema):
            tbl = ref_tbl.this
            ref_cols = [c.name for c in ref_tbl.expressions]
        else:
            tbl = ref_tbl
            ref_cols = []

        ref_resource = f"{tbl.db}.{tbl.name}" if tbl.db else tbl.name
        return ForeignKeyRef(
            fields=fk_cols,
            reference_resource=ref_resource,
            reference_fields=ref_cols,
        )
    except Exception as exc:
        logger.warning("No se pudo parsear FK: %s", exc)
        return None
