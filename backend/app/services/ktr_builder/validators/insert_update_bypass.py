"""R-K7 (docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md,
D51): InsertUpdateMeta.prepareUpdate() arma un "UPDATE t SET ... WHERE ..."
con SET vacío y falla en la primera fila si update_bypassed queda en "N"
(default de Kettle cuando el tag está ausente) mientras CERO <value> del step
tienen update="Y". steps/output.py:_step_InsertUpdate ya evita este caso por
default (bypass automático a "Y" sin declaración explícita en cfg) — este
pass cubre el caso restante: cfg declara update_bypassed=N/false EXPLÍCITO a
la vez que declara cero values updatable, combinación contradictoria que
nadie puede resolver por su cuenta sin saber la intención real (D15: reporta,
no repara)."""
from __future__ import annotations

from app.services.ktr_builder.common import _yn
from app.services.ktr_builder.contracts import parse_cfg
from app.services.ktr_builder.validators.base import Finding, ValidationContext

INSERT_UPDATE_BYPASS_PREFIX = "[Insert/Update] "

name = "check_insert_update_bypass"


def check_insert_update_bypass(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    for step in ctx.ktr_data.get("steps", []):
        raw_type = step.get("type", "")
        canonical = ctx.step_type_aliases.get(raw_type, raw_type)
        if canonical != "InsertUpdate":
            continue
        cfg = parse_cfg(step.get("config", {}))
        if "update_bypassed" not in cfg:
            continue  # sin declaración explícita, el emisor ya decide un default seguro
        if _yn(cfg.get("update_bypassed"), default=False) != "N":
            continue
        fields = cfg.get("fields", [])
        has_updatable_value = any(f.get("update", True) for f in fields)
        if has_updatable_value:
            continue
        step_name = step.get("name", "")
        findings.append(Finding(
            severity="error", step_name=step_name,
            message=(
                f"{INSERT_UPDATE_BYPASS_PREFIX}Step '{step_name}': update_bypassed=N declarado "
                "explícito con CERO <value> en update=Y — Kettle arma un 'UPDATE ... SET' vacío y "
                "falla en la primera fila (InsertUpdateMeta.prepareUpdate()). Si la intención es que "
                "el UPDATE nunca corra (insert-only), quitar update_bypassed del config o ponerlo en Y."
            ),
        ))
    return findings
