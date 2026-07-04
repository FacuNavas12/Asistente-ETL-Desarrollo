"""
Clasificación general de defaults SQL: literal vs función/expresión.

Usado en dos puntos del pipeline:
  1. Adapters (ddl_adapter, db_adapter) — clasifican el DEFAULT de cada columna
     al construir el CanonicalField, para que el prompt le diga al modelo qué
     columnas no debe poblar.
  2. Validador post-generación (ktr_builder) — red de seguridad que revisa el
     valor que el modelo efectivamente puso en un step Constant, sin importar
     si el modelo leyó o ignoró la indicación del prompt.

No depende de un dialecto SQL específico ni de sqlglot — trabaja sobre texto,
así sirve tanto para expresiones ya renderizadas (DDL) como para el string
crudo de information_schema.columns.column_default.
"""
from __future__ import annotations

import re
from typing import Literal

DefaultKind = Literal["literal", "function"]

# Palabras clave SQL que son funciones/expresiones sin paréntesis.
_KEYWORD_FUNCTIONS: frozenset[str] = frozenset({
    "current_timestamp", "current_date", "current_time",
    "localtimestamp", "localtime", "current_user", "session_user", "sysdate",
})

# Identificador seguido de paréntesis: NOW(), gen_random_uuid(), nextval('x'), getdate()...
_FUNCTION_CALL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*\(.*\)")


def looks_like_sql_function(expr: str | None) -> bool:
    """True si expr es una función/expresión SQL (NOW(), CURRENT_TIMESTAMP, nextval(...))
    en vez de un valor literal ('ACTIVO', 0, TRUE). Nunca levanta excepción."""
    if not expr:
        return False
    s = expr.strip()
    if not s:
        return False
    bare = s.strip("()").strip()
    if bare.lower() in _KEYWORD_FUNCTIONS:
        return True
    return bool(_FUNCTION_CALL_RE.search(s))


def classify_default_expr(expr: str | None) -> DefaultKind | None:
    """Clasifica un default de columna. None si expr está vacío."""
    if not expr:
        return None
    return "function" if looks_like_sql_function(expr) else "literal"
