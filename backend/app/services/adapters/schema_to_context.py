"""
Adapter: list[CanonicalSchema] → ModelContext.

This is the canonical exit point toward the prompt builder.
It replaces the ad-hoc ModelTableContext construction scattered in context_builder.
Not wired to any router yet (Fase 1).

Two paths:
  - Schema has a profile → use profile.column_profiles directly (already sanitized).
  - No profile          → synthesize minimal ColumnProfile from CanonicalField structure.
    Used when a CanonicalSchema is built from DDL or user-provided metadata without
    a live profiling run.
"""
from __future__ import annotations

from app.schemas.canonical import CanonicalField, CanonicalSchema, CanonicalType
from app.schemas.context_schemas import ColumnProfile, ModelContext, ModelTableContext

# Maps CanonicalType → the inferred_type literal expected by ColumnProfile.
# ColumnProfile.inferred_type uses legacy names from the profiler ("int", "float").
_CANONICAL_TO_PROFILE_TYPE: dict[CanonicalType, str] = {
    CanonicalType.STRING:   "string",
    CanonicalType.INTEGER:  "int",
    CanonicalType.NUMBER:   "float",
    CanonicalType.BOOLEAN:  "bool",
    CanonicalType.DATE:     "date",
    CanonicalType.TIME:     "string",
    CanonicalType.DATETIME: "date",
    CanonicalType.OBJECT:   "string",
    CanonicalType.ARRAY:    "string",
    CanonicalType.BINARY:   "string",
    CanonicalType.UNKNOWN:  "unknown",
}


def canonical_to_model_context(schemas: list[CanonicalSchema]) -> ModelContext:
    """
    Convert a list of CanonicalSchema objects into a ModelContext for prompt serialization.

    If a schema carries a profile, its column_profiles are used as-is (they were
    produced by the profiler and are already sanitized). Otherwise, a minimal
    ColumnProfile is synthesized from the structural fields — null_pct and
    distinct_count are unknown (0) and must be disclosed as such in the prompt.
    """
    model_tables: list[ModelTableContext] = []
    for schema in schemas:
        if schema.profile and schema.profile.column_profiles:
            profiles = schema.profile.column_profiles
        else:
            profiles = [_field_to_minimal_profile(f) for f in schema.fields]

        model_tables.append(
            ModelTableContext(
                table_name=schema.source_name,
                columns=profiles,
            )
        )
    return ModelContext(source_tables=model_tables)


def _field_to_minimal_profile(field: CanonicalField) -> ColumnProfile:
    """
    Synthesize a minimal ColumnProfile from structural metadata only.
    Statistical fields (null_pct, distinct_count) are set to 0 / unknown
    because no profiling run was available.
    """
    inferred = _CANONICAL_TO_PROFILE_TYPE.get(field.type, "unknown")
    fmt_hint: str | None = None
    if field.format != "default":
        fmt_hint = field.format
    elif field.length is not None:
        fmt_hint = f"max length: {field.length}"
    elif field.precision is not None and field.scale is not None:
        fmt_hint = f"numeric({field.precision},{field.scale})"

    return ColumnProfile(
        name=field.name,
        inferred_type=inferred,
        null_pct=0.0,
        distinct_count=0,
        leading_trailing_spaces_pct=0.0,
        casing_distribution={},
        format_hint=fmt_hint,
        required=field.constraints.required,
        default_kind=field.default_kind,
    )
