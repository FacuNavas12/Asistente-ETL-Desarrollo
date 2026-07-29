"""Contrato uniforme para validadores/reparadores pre-emisión de `ktr_data`
(H29, docs/refactor/01-hallazgos.md). Los validadores existentes del paquete
(`fragmentation.py`, `dimension_step_policy.py`, `fields_validate.py`, ...)
devuelven cada uno una forma distinta (`list[str]`, `list[dict]`, mutación
in-place sin retorno) — este módulo no los reemplaza, es el contrato que
adopta el código nuevo desde acá en adelante (docs/refactor/02-decisiones.md,
D40).

Invariante (D5/D15 — nunca en silencio): un pass PUEDE mutar `ktr_data`, pero
toda mutación real debe venir acompañada de un `Finding` con `repaired=True`.
Un pass nunca aborta el build por su cuenta — reporta severidad `"error"` y
deja que el caller decida (D15: notifica, no bloquea)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ValidationContext:
    ktr_data: dict
    step_type_aliases: dict[str, str]
    known_tables: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "warning" | "info"
    message: str
    step_name: str | None = None
    repaired: bool = False


class KtrPass(Protocol):
    name: str

    def __call__(self, ctx: ValidationContext) -> list[Finding]: ...
