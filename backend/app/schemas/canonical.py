from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.context_schemas import ColumnProfile


# ── Tipos canónicos ───────────────────────────────────────────────────────────

class CanonicalType(str, Enum):
    STRING   = "string"
    INTEGER  = "integer"
    NUMBER   = "number"
    BOOLEAN  = "boolean"
    DATE     = "date"
    TIME     = "time"
    DATETIME = "datetime"
    OBJECT   = "object"
    ARRAY    = "array"
    BINARY   = "binary"
    UNKNOWN  = "unknown"


# ── Formatos (alineados con Frictionless + extensiones propias) ───────────────

FieldFormat = Literal[
    "default",
    # date / datetime / time
    "YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "YYYY/MM/DD", "DD-MM-YYYY",
    "YYYY-MM-DDTHH:MM:SS", "YYYY-MM-DD HH:MM:SS",
    # string
    "email", "uri", "phone", "uuid",
    # number
    "decimal-comma",
]


# ── Constraints estructurales ─────────────────────────────────────────────────

class FieldConstraints(BaseModel):
    required: bool = False
    unique: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    minimum: Optional[str] = None
    maximum: Optional[str] = None
    pattern: Optional[str] = None
    enum: Optional[list[str]] = None


# ── FK ────────────────────────────────────────────────────────────────────────

class ForeignKeyRef(BaseModel):
    """Alineado con Frictionless Table Schema foreignKeys."""
    fields: list[str]
    reference_resource: str      # "schema.table"
    reference_fields: list[str]


# ── Semántica de columna (la llena el usuario) ────────────────────────────────

class ColumnRole(str, Enum):
    MEASURE             = "measure"
    DIMENSION_ATTRIBUTE = "dimension_attribute"
    KEY                 = "key"
    DATE                = "date"
    DEGENERATE          = "degenerate"
    DESCRIPTIVE         = "descriptive"


class ColumnSemantics(BaseModel):
    """Opcional. None por defecto. Nunca inferida por la máquina."""
    role: Optional[ColumnRole] = None
    semantic_type: Optional[str] = None
    scd_type: Optional[Literal["1", "2", "3", "6"]] = None


# ── Campo canónico ────────────────────────────────────────────────────────────

class CanonicalField(BaseModel):
    # Estructura — llena la máquina
    name: str
    type: CanonicalType = CanonicalType.UNKNOWN
    format: FieldFormat = "default"
    precision: Optional[int] = None   # null cuando el origen no puede conocerlo (CSV)
    scale: Optional[int] = None
    length: Optional[int] = None
    constraints: FieldConstraints = FieldConstraints()
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: Optional[ForeignKeyRef] = None
    inferred_by: Literal["database", "frictionless", "ddl", "user"] = "user"

    # Semántica — llena el usuario
    semantics: ColumnSemantics = ColumnSemantics()


# ── Semántica de tabla (la llena el usuario) ──────────────────────────────────

class DwhIntent(BaseModel):
    """Shape reservado; sin lógica todavía."""
    table_type: Optional[Literal["dimension", "fact", "staging", "bridge"]] = None
    scd_type: Optional[Literal["1", "2", "3", "6"]] = None


class TableSemantics(BaseModel):
    """Opcional. None por defecto. Llena el usuario."""
    grain: Optional[str] = None
    business_description: Optional[str] = None
    dwh_intent: Optional[DwhIntent] = None


# ── Perfil estadístico (sin filas; solo metadata resumen) ────────────────────

class TableProfile(BaseModel):
    row_count_estimate: Optional[int] = None
    column_profiles: list[ColumnProfile]  # type: ignore[type-arg]


# ── Esquema canónico ──────────────────────────────────────────────────────────

class CanonicalSchema(BaseModel):
    schema_version: str = "1.0"
    source_name: str
    source_type: Literal["csv", "excel", "database", "ddl"]
    fields: list[CanonicalField]

    # Estructura — llena la máquina
    primary_key: list[str] = []
    foreign_keys: list[ForeignKeyRef] = []

    # Semántica — llena el usuario
    semantics: TableSemantics = TableSemantics()

    # Perfil estadístico opcional
    profile: Optional[TableProfile] = None


# Resuelve la forward reference de TableProfile → ColumnProfile al final del módulo
# para evitar importación circular en tiempo de ejecución.
from app.schemas.context_schemas import ColumnProfile  # noqa: E402
TableProfile.model_rebuild()
