"""Vocabulario canónico de tipos/columnas — value objects puros (stdlib),
independientes de cómo se transportan (Pydantic vive en schemas/canonical.py,
que reexporta estos tres símbolos para no romper a sus 16 consumidores).

Movidos acá desde schemas/canonical.py (sesión de arquitectura, split de
registry.py): son vocabulario estable del dominio ("qué tipos de dato/columna
existen"), no contrato de transporte HTTP — ver docs/arquitectura-objetivo.md,
sección "Mapa capa-objetivo".
"""
from __future__ import annotations

from enum import Enum
from typing import Literal


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


# Alineados con Frictionless + extensiones propias.
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


class ColumnRole(str, Enum):
    MEASURE             = "measure"
    DIMENSION_ATTRIBUTE = "dimension_attribute"
    KEY                 = "key"
    DATE                = "date"
    DEGENERATE          = "degenerate"
    DESCRIPTIVE         = "descriptive"
