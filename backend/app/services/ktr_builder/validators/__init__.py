"""Registry de passes pre-emisión sobre `ktr_data` (ver base.py para el
contrato). Agregar un pass nuevo es agregarlo a PRE_EMIT_PASSES — nada más
en este paquete cambia."""
from __future__ import annotations

from app.services.ktr_builder.validators.base import (
    Finding,
    KtrPass,
    PRE_EMIT_ERROR_PREFIX,
    ValidationContext,
    split_findings_by_severity,
)
from app.services.ktr_builder.validators.dead_computed_fields import DEAD_FIELD_PREFIX, flag_dead_computed_fields
from app.services.ktr_builder.validators.dimension_lookup_fields import (
    DIMENSION_LOOKUP_FIELDS_PREFIX,
    check_dimension_lookup_fields,
)
from app.services.ktr_builder.validators.insert_update_bypass import (
    INSERT_UPDATE_BYPASS_PREFIX,
    check_insert_update_bypass,
)
from app.services.ktr_builder.validators.check_constraint_filter import (
    CHECK_FILTER_PREFIX,
    check_constraint_filter_rows,
)
from app.services.ktr_builder.validators.guard_staging_layer import (
    STAGING_GUARD_PREFIX,
    guard_staging_layer,
)
from app.services.ktr_builder.validators.narration_crosscheck import (
    NARRATION_CROSSCHECK_PREFIX,
    check_narration_crosscheck,
)
from app.services.ktr_builder.validators.monetary_scale import (
    MONETARY_SCALE_PREFIX,
    check_monetary_scale,
)
from app.services.ktr_builder.validators.table_key_recovery import TABLE_KEY_PREFIX, recover_table_key

# O3 (docs/refactor/30-decision-python-llm.md): la tupla se parte en dos.
# TABLE_RECOVERY_PASSES tiene que correr ANTES de apply_dimension_contracts
# (necesita 'table' ya recuperado — ver table_key_recovery.py). VERIFY_PASSES
# tiene que correr DESPUÉS: inspeccionan el config final de un step de
# dimensión (date_from/date_to/fields[].type en check_dimension_lookup_fields,
# la narración del modelo contra el step real en check_narration_crosscheck),
# y antes de O3 esos passes corrían sobre el config que el MODELO había
# escrito, no sobre el que Python termina sintetizando — un finding sobre un
# valor que estaba por ser pisado es una señal falsa, no ruido inocuo.
# PRE_EMIT_PASSES se preserva como la concatenación de ambas: build.py sigue
# corriendo la tupla completa como red de seguridad para callers que no pasan
# por apply_dimension_contracts (tests, build_etl_from_raw con dim_contracts
# vacío) — nada cambia ahí.
TABLE_RECOVERY_PASSES: tuple[KtrPass, ...] = (
    recover_table_key,
)
VERIFY_PASSES: tuple[KtrPass, ...] = (
    flag_dead_computed_fields, check_dimension_lookup_fields, check_insert_update_bypass,
    check_constraint_filter_rows, guard_staging_layer, check_narration_crosscheck, check_monetary_scale,
)
PRE_EMIT_PASSES: tuple[KtrPass, ...] = TABLE_RECOVERY_PASSES + VERIFY_PASSES


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
    "TABLE_RECOVERY_PASSES",
    "VERIFY_PASSES",
    "PRE_EMIT_ERROR_PREFIX",
    "run_passes",
    "split_findings_by_severity",
    "TABLE_KEY_PREFIX",
    "recover_table_key",
    "DEAD_FIELD_PREFIX",
    "flag_dead_computed_fields",
    "DIMENSION_LOOKUP_FIELDS_PREFIX",
    "check_dimension_lookup_fields",
    "INSERT_UPDATE_BYPASS_PREFIX",
    "check_insert_update_bypass",
    "CHECK_FILTER_PREFIX",
    "check_constraint_filter_rows",
    "STAGING_GUARD_PREFIX",
    "guard_staging_layer",
    "NARRATION_CROSSCHECK_PREFIX",
    "check_narration_crosscheck",
    "MONETARY_SCALE_PREFIX",
    "check_monetary_scale",
]
