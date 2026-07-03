from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel


class ColumnStats(BaseModel):
    """Population-level stats from SQL aggregates or in-memory scan.
    Never sent to the model — used only inside the profiler.
    """
    total_count: int
    null_count: int
    distinct_count: int
    min_length: Optional[int] = None
    max_length: Optional[int] = None


class ColumnProfile(BaseModel):
    """Per-column sanitized profile. This is the only column representation
    that may appear in a model prompt.
    """
    name: str
    inferred_type: Literal["string", "int", "float", "date", "bool", "unknown"]
    null_pct: float
    distinct_count: int
    leading_trailing_spaces_pct: float
    casing_distribution: dict[str, float]
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    # Descriptor only: "YYYY-MM-DD", regex pattern, "enum-like (N distinct values)".
    # NEVER the actual category list or real sample values.
    format_hint: Optional[str] = None
    # Only when format is ambiguous AND cardinality is high enough to avoid
    # revealing the value set. Values are masked (e.g. j***@***.com).
    masked_examples: Optional[list[str]] = None
    # Estructura de la columna (NOT NULL / PK) — nunca dato. required=True sin
    # default_kind indica que el ETL debe proveer el valor obligatoriamente.
    required: bool = False
    # "literal" (emitible como constante) o "function" (NOW(), nextval(...):
    # la debe aplicar la BD destino, el ETL nunca la emite como valor). None
    # cuando la columna no declara DEFAULT.
    default_kind: Optional[Literal["literal", "function"]] = None


class InternalTableRef(BaseModel):
    """Backend-only reference. Contains everything needed to re-query the source.
    NEVER serialized to a prompt or included in a router response body.
    """
    connection_id: str
    schema_name: Optional[str] = None
    table_name: str


class InternalContext(BaseModel):
    """Backend-only container of all source refs for a request.
    NEVER sent to the model.
    """
    source_refs: list[InternalTableRef]


class ModelTableContext(BaseModel):
    """Sanitized, profiled view of one source table.
    Contains no connection identifiers and no raw data.
    """
    table_name: str
    columns: list[ColumnProfile]


class ModelContext(BaseModel):
    """Everything the model is allowed to see about source tables.
    Built exclusively via the whitelist in context_builder.format_model_context_for_prompt().
    """
    source_tables: list[ModelTableContext]
