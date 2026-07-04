"""
Adapter: list[ColumnInfo] + list[ForeignKeyRef] → CanonicalSchema (source_type="database").

This is the single entry point for converting BD schema metadata into the canonical
representation. It does not touch the database — all queries happen upstream in
db_connector.get_columns() and db_connector.get_foreign_keys().
"""
from __future__ import annotations

from app.schemas.canonical import (
    CanonicalField,
    CanonicalSchema,
    FieldConstraints,
    ForeignKeyRef,
    TableProfile,
)
from app.schemas.connection import ColumnInfo
from app.services.sql_defaults import classify_default_expr
from app.services.type_mappings import map_sql_type


def build(
    col_infos: list[ColumnInfo],
    source_name: str,
    fk_refs: list[ForeignKeyRef] | None = None,
    profile: TableProfile | None = None,
) -> CanonicalSchema:
    """
    Build a CanonicalSchema from db_connector output.

    Args:
        col_infos:   Ordered list of ColumnInfo from get_columns().
        source_name: Table name in "schema.table" or "table" format.
        fk_refs:     FK relationships from get_foreign_keys(). None = no FKs.
        profile:     Optional statistical profile from the profiler.

    Returns:
        CanonicalSchema with source_type="database", inferred_by="database" on all fields.
    """
    fk_refs = fk_refs or []

    # Build per-column FK lookup (column name → its ForeignKeyRef)
    # A column can participate in at most one FK constraint.
    fk_by_col: dict[str, ForeignKeyRef] = {}
    for fk in fk_refs:
        for col_name in fk.fields:
            fk_by_col[col_name] = fk

    fields: list[CanonicalField] = []
    for ci in col_infos:
        canonical_type, precision, scale, length, fmt = map_sql_type(ci.type)
        fields.append(
            CanonicalField(
                name=ci.name,
                type=canonical_type,
                format=fmt,
                precision=precision,
                scale=scale,
                length=length,
                constraints=FieldConstraints(required=not ci.nullable),
                is_primary_key=ci.primary_key,
                is_foreign_key=ci.name in fk_by_col,
                references=fk_by_col.get(ci.name),
                inferred_by="database",
                default_expr=ci.default,
                default_kind=classify_default_expr(ci.default),
            )
        )

    pk_cols = [f.name for f in fields if f.is_primary_key]

    return CanonicalSchema(
        source_name=source_name,
        source_type="database",
        fields=fields,
        primary_key=pk_cols,
        foreign_keys=fk_refs,
        profile=profile,
    )
