"""Registry de passes pre-emisión sobre `ktr_data` (ver base.py para el
contrato). Agregar un pass nuevo es agregarlo a PRE_EMIT_PASSES — nada más
en este paquete cambia."""
from __future__ import annotations

from app.services.ktr_builder.validators.base import Finding, KtrPass, ValidationContext
from app.services.ktr_builder.validators.dead_computed_fields import DEAD_FIELD_PREFIX, flag_dead_computed_fields
from app.services.ktr_builder.validators.table_key_recovery import TABLE_KEY_PREFIX, recover_table_key

PRE_EMIT_PASSES: tuple[KtrPass, ...] = (recover_table_key, flag_dead_computed_fields)


def run_passes(ctx: ValidationContext, passes: tuple[KtrPass, ...] = PRE_EMIT_PASSES) -> list[Finding]:
    findings: list[Finding] = []
    for run in passes:
        findings.extend(run(ctx))
    return findings


__all__ = [
    "Finding",
    "KtrPass",
    "ValidationContext",
    "PRE_EMIT_PASSES",
    "run_passes",
    "TABLE_KEY_PREFIX",
    "recover_table_key",
    "DEAD_FIELD_PREFIX",
    "flag_dead_computed_fields",
]
