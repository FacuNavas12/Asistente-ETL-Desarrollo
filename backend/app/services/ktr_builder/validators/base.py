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
    # {tabla_lower: {columna: {"minimum": str|None, "maximum": str|None, "type": str}}}
    # -- solo columnas con CHECK de rango (D43), solo tablas DWH (Fase 2-ter,
    # docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md). Plain
    # dict, no CanonicalField/FieldConstraints (pydantic, no domain) -- ver
    # check_constraint_filter.py para el builder real (etl_generator.py).
    dwh_constraints: dict[str, dict[str, dict]] = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "warning" | "info"
    message: str
    step_name: str | None = None
    repaired: bool = False


class KtrPass(Protocol):
    name: str

    def __call__(self, ctx: ValidationContext) -> list[Finding]: ...


# Fase 0 (docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md, D50):
# antes de esto, todo caller de run_passes() aplanaba a `f.message`, tirando
# la severidad — un Finding severity="error" de recover_table_key llegaba a
# EtlDetail indistinguible de una advertencia de buenas prácticas. Reusa el
# mismo mecanismo de promoción por prefijo que FIELD_INTEGRITY_PREFIX/
# CONTRACT_PREFIX/ERROR_CATALOG_PREFIX (etl_generator._split_integrity_warnings)
# en vez de cambiar el tipo de retorno de cada caller de list[str] a
# list[Finding] — el plumbing de warnings en etl_generator.py es list[str] en
# ~7 sitios y ese refactor más grande no lo pide esta fase.
PRE_EMIT_ERROR_PREFIX = "[Validación pre-emisión] "


def split_findings_by_severity(findings: list[Finding]) -> list[str]:
    """Findings severity=='error' llevan PRE_EMIT_ERROR_PREFIX (el caller los
    promueve a Validacion tipo=error vía _split_integrity_warnings); el resto
    queda como mensaje plano (cosmético, buenas prácticas)."""
    return [
        f"{PRE_EMIT_ERROR_PREFIX}{f.message}" if f.severity == "error" else f.message
        for f in findings
    ]
