from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel, model_validator

# Excepción nombrada a "schemas/ no importa nada del proyecto" (por símbolo,
# no por paquete — docs/arquitectura-objetivo.md, sección "Mapa capa-objetivo"):
# CanonicalType/FieldFormat/ColumnRole son value objects puros de stdlib
# (Enum/Literal), vocabulario de dominio, no contrato de transporte. Viven en
# domain/ y se reexportan acá para no romper a los consumidores existentes de
# `from app.schemas.canonical import CanonicalType`. Cualquier ampliación de
# esta excepción tiene que argumentar contra ese motivo (value object puro de
# stdlib), no asumirlo por analogía.
from app.domain.canonical_types import CanonicalType, ColumnRole, FieldFormat

__all__ = [
    "CanonicalType",
    "ColumnRole",
    "FieldFormat",
    "FieldConstraints",
    "ForeignKeyRef",
    "ColumnSemantics",
    "CanonicalField",
    "DwhIntent",
    "TableSemantics",
    "TableProfile",
    "CanonicalSchema",
]

if TYPE_CHECKING:
    from app.schemas.context_schemas import ColumnProfile


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

    @model_validator(mode="before")
    @classmethod
    def _normalize_llm_names(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        # fields: accept "columns"
        if "fields" not in data and "columns" in data:
            data["fields"] = data.pop("columns")
        # reference_resource: accept "table"
        if "reference_resource" not in data and "table" in data:
            data["reference_resource"] = data.pop("table")
        # reference_fields: accept "column" (str) or "reference_columns"
        if "reference_fields" not in data:
            if "reference_columns" in data:
                data["reference_fields"] = data.pop("reference_columns")
            elif "column" in data:
                val = data.pop("column")
                data["reference_fields"] = [val] if isinstance(val, str) else val
        return data


# ── Semántica de columna (la llena el usuario) ────────────────────────────────
# ColumnRole vive en domain/canonical_types.py — reexportado arriba.

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

    # Default de columna — estructura, nunca dato. default_kind clasifica
    # default_expr como "literal" (emitible como constante) o "function"
    # (NOW(), gen_random_uuid(), nextval(...): la debe aplicar la BD, nunca
    # el ETL). None cuando la columna no tiene DEFAULT declarado.
    default_expr: Optional[str] = None
    default_kind: Optional[Literal["literal", "function"]] = None

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
