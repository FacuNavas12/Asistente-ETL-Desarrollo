"""
Canonical type mapping from raw SQL type strings to CanonicalType.

Input: the formatted type string produced by db_connector._format_type(), e.g.:
  "integer", "varchar(255)", "character varying(100)", "numeric(10,2)", "boolean"

Covers PostgreSQL (information_schema data_type names) and SQL Server.
Unknown types map to CanonicalType.UNKNOWN — never raise.
"""
from __future__ import annotations

import re
from typing import Optional

from app.schemas.canonical import CanonicalType, FieldFormat

# ── Regex patterns ────────────────────────────────────────────────────────────

# "numeric(10,2)" or "decimal(10, 2)"
_PREC_SCALE_RE = re.compile(r'^(.+?)\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)$')
# "varchar(255)" or "character varying(100)" or "numeric(10)"
_LENGTH_RE = re.compile(r'^(.+?)\s*\(\s*(\d+)\s*\)$')

# Base types where a single-arg "(n)" means precision, not character length
_PRECISION_ONLY_TYPES: frozenset[str] = frozenset({
    "numeric", "decimal", "float", "real", "double precision",
})

# Types that carry format="uuid"
_UUID_TYPES: frozenset[str] = frozenset({"uuid", "uniqueidentifier"})

# ── Lookup table ──────────────────────────────────────────────────────────────

_TYPE_MAP: dict[str, CanonicalType] = {
    # ── Integer ──
    "integer":      CanonicalType.INTEGER,
    "int":          CanonicalType.INTEGER,
    "int4":         CanonicalType.INTEGER,
    "bigint":       CanonicalType.INTEGER,
    "int8":         CanonicalType.INTEGER,
    "smallint":     CanonicalType.INTEGER,
    "int2":         CanonicalType.INTEGER,
    "tinyint":      CanonicalType.INTEGER,
    "serial":       CanonicalType.INTEGER,
    "bigserial":    CanonicalType.INTEGER,
    "smallserial":  CanonicalType.INTEGER,

    # ── Number ──
    "numeric":          CanonicalType.NUMBER,
    "decimal":          CanonicalType.NUMBER,
    "float":            CanonicalType.NUMBER,
    "float4":           CanonicalType.NUMBER,
    "float8":           CanonicalType.NUMBER,
    "real":             CanonicalType.NUMBER,
    "double precision": CanonicalType.NUMBER,
    "money":            CanonicalType.NUMBER,
    "smallmoney":       CanonicalType.NUMBER,

    # ── String ──
    "character varying": CanonicalType.STRING,
    "varchar":           CanonicalType.STRING,
    "character":         CanonicalType.STRING,
    "char":              CanonicalType.STRING,
    "nchar":             CanonicalType.STRING,
    "nvarchar":          CanonicalType.STRING,
    "text":              CanonicalType.STRING,
    "ntext":             CanonicalType.STRING,
    "name":              CanonicalType.STRING,
    "citext":            CanonicalType.STRING,
    "uuid":              CanonicalType.STRING,
    "uniqueidentifier":  CanonicalType.STRING,

    # ── Boolean ──
    "boolean": CanonicalType.BOOLEAN,
    "bool":    CanonicalType.BOOLEAN,
    "bit":     CanonicalType.BOOLEAN,   # SQL Server BIT is boolean-like

    # ── Date ──
    "date": CanonicalType.DATE,

    # ── Time ──
    "time":                     CanonicalType.TIME,
    "time without time zone":   CanonicalType.TIME,
    "time with time zone":      CanonicalType.TIME,
    "timetz":                   CanonicalType.TIME,

    # ── Datetime ──
    "timestamp":                    CanonicalType.DATETIME,
    "timestamp without time zone":  CanonicalType.DATETIME,
    "timestamp with time zone":     CanonicalType.DATETIME,
    "timestamptz":                  CanonicalType.DATETIME,
    "datetime":                     CanonicalType.DATETIME,
    "datetime2":                    CanonicalType.DATETIME,
    "smalldatetime":                CanonicalType.DATETIME,
    "datetimeoffset":               CanonicalType.DATETIME,

    # ── Object ──
    "json":  CanonicalType.OBJECT,
    "jsonb": CanonicalType.OBJECT,
    "xml":   CanonicalType.OBJECT,

    # ── Binary ──
    "bytea":     CanonicalType.BINARY,
    "binary":    CanonicalType.BINARY,
    "varbinary": CanonicalType.BINARY,
    "image":     CanonicalType.BINARY,

    # ── Array ──
    "array": CanonicalType.ARRAY,

    # ── Geo / network / other PG types → STRING (structure preserved as text) ──
    "interval":  CanonicalType.STRING,
    "inet":      CanonicalType.STRING,
    "cidr":      CanonicalType.STRING,
    "macaddr":   CanonicalType.STRING,
    "macaddr8":  CanonicalType.STRING,
    "point":     CanonicalType.STRING,
    "line":      CanonicalType.STRING,
    "lseg":      CanonicalType.STRING,
    "box":       CanonicalType.STRING,
    "path":      CanonicalType.STRING,
    "polygon":   CanonicalType.STRING,
    "circle":    CanonicalType.STRING,
    "tsvector":  CanonicalType.STRING,
    "tsquery":   CanonicalType.STRING,
}


# ── Public API ────────────────────────────────────────────────────────────────

def map_sql_type(
    type_str: str,
) -> tuple[CanonicalType, Optional[int], Optional[int], Optional[int], FieldFormat]:
    """
    Parse a SQL type string into canonical components.

    Returns:
        (canonical_type, precision, scale, length, format)
        precision/scale/length are None when not applicable.

    Examples:
        "integer"              → (INTEGER, None, None, None, "default")
        "varchar(255)"         → (STRING,  None, None, 255,  "default")
        "character varying(100)" → (STRING, None, None, 100,  "default")
        "numeric(10,2)"        → (NUMBER,  10,   2,    None, "default")
        "uuid"                 → (STRING,  None, None, None, "uuid")
        "some_exotic_type"     → (UNKNOWN, None, None, None, "default")
    """
    s = type_str.strip()
    precision: Optional[int] = None
    scale: Optional[int]     = None
    length: Optional[int]    = None

    m = _PREC_SCALE_RE.match(s)
    if m:
        base      = m.group(1).strip().lower()
        precision = int(m.group(2))
        scale     = int(m.group(3))
    else:
        m = _LENGTH_RE.match(s)
        if m:
            base = m.group(1).strip().lower()
            n    = int(m.group(2))
            if base in _PRECISION_ONLY_TYPES:
                precision = n
            else:
                length = n
        else:
            base = s.lower()

    canonical: CanonicalType = _TYPE_MAP.get(base, CanonicalType.UNKNOWN)
    fmt: FieldFormat = "uuid" if base in _UUID_TYPES else "default"

    return canonical, precision, scale, length, fmt
