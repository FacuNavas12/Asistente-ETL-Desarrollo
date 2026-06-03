"""
Adapter: frictionless.Schema → CanonicalSchema (source_type="csv" or "excel").

Frictionless type names are a superset of CanonicalType; all map 1:1 except
exotic types which fall to UNKNOWN. Format hints are preserved where possible.
"""
from __future__ import annotations

from typing import Literal

from app.schemas.canonical import (
    CanonicalField,
    CanonicalSchema,
    CanonicalType,
    FieldConstraints,
    FieldFormat,
)
from app.services.type_mappings import FieldFormat as _FieldFormatType

# Frictionless type name → CanonicalType
_FR_TYPE_MAP: dict[str, CanonicalType] = {
    "string":   CanonicalType.STRING,
    "integer":  CanonicalType.INTEGER,
    "number":   CanonicalType.NUMBER,
    "boolean":  CanonicalType.BOOLEAN,
    "date":     CanonicalType.DATE,
    "time":     CanonicalType.TIME,
    "datetime": CanonicalType.DATETIME,
    "year":     CanonicalType.INTEGER,   # frictionless-specific
    "yearmonth":CanonicalType.STRING,    # no CanonicalType equivalent
    "duration": CanonicalType.STRING,
    "object":   CanonicalType.OBJECT,
    "array":    CanonicalType.ARRAY,
    "geojson":  CanonicalType.OBJECT,
    "any":      CanonicalType.UNKNOWN,
}

# Frictionless date/datetime/time format strings → our FieldFormat literals.
# Frictionless uses strptime-style patterns; we map known ones to our enum.
_FR_DATE_FORMAT_MAP: dict[str, FieldFormat] = {
    "default":       "YYYY-MM-DD",
    "%Y-%m-%d":      "YYYY-MM-DD",
    "%d/%m/%Y":      "DD/MM/YYYY",
    "%m/%d/%Y":      "MM/DD/YYYY",
    "%Y/%m/%d":      "YYYY/MM/DD",
    "%d-%m-%Y":      "DD-MM-YYYY",
    "%Y-%m-%dT%H:%M:%S": "YYYY-MM-DDTHH:MM:SS",
    "%Y-%m-%d %H:%M:%S": "YYYY-MM-DD HH:MM:SS",
}


def frictionless_schema_to_canonical(
    fr_schema,
    source_name: str,
    source_type: Literal["csv", "excel"],
) -> CanonicalSchema:
    """
    Convert a frictionless.Schema object to a CanonicalSchema.

    Args:
        fr_schema:   A frictionless.Schema obtained from resource.schema.
        source_name: The table/sheet name (filename without extension or sheet name).
        source_type: "csv" or "excel".

    Returns:
        CanonicalSchema with inferred_by="frictionless" on all fields.
        No profile is set here — the caller (file_schema.py) attaches it.
    """
    fields: list[CanonicalField] = []

    for fr_field in fr_schema.fields:
        canonical_type = _FR_TYPE_MAP.get(fr_field.type, CanonicalType.UNKNOWN)
        fmt            = _map_format(fr_field.type, fr_field.format)

        fields.append(
            CanonicalField(
                name=fr_field.name,
                type=canonical_type,
                format=fmt,
                inferred_by="frictionless",
                constraints=FieldConstraints(),
                # precision/scale/length unavailable from file sources — left None
            )
        )

    return CanonicalSchema(
        source_name=source_name,
        source_type=source_type,
        fields=fields,
    )


def _map_format(fr_type: str, fr_format: str) -> FieldFormat:
    """
    Map frictionless (type, format) pair to our FieldFormat literal.
    Falls back to "default" for unrecognized combinations.
    """
    if fr_type in ("date", "datetime", "time"):
        return _FR_DATE_FORMAT_MAP.get(fr_format, "default")
    return "default"
