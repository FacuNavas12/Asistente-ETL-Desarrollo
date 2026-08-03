"""P3-4 (docs/refactor/plan-reparacion-etl.md, item 8): la escala de un campo
`BigNumber` sin `length`/`precision` explícita tiene que salir del DDL del
DWH, nunca de un default fabricado (18,2 "precedente estándar" no es una
fuente verificable por columna). Repara cuando el DDL resuelve la escala;
reporta error cuando no hay fuente confiable -- nunca se fabrica un valor.

`Calculator` y `Formula` declaran la misma información bajo claves de config
DISTINTAS (`value_type`/`value_length`/`value_precision` vs.
`type`/`length`/`precision` -- convención deliberada, ver system_etl.txt:369,
no un alias que normalize_config resuelva) -- de ahí la tabla
`_SCALE_KEYS_BY_CANONICAL` en vez de asumir un único juego de claves."""
from __future__ import annotations

from app.services.ktr_builder.contracts import parse_cfg
from app.services.ktr_builder.validators.base import Finding, ValidationContext

MONETARY_SCALE_PREFIX = "[Escala BigNumber] "

name = "check_monetary_scale"

# canonical -> (entries_key, type_key, length_key, precision_key) -- claves de
# INPUT que cada emisor realmente lee, no intercambiables (ver docstring).
_SCALE_KEYS_BY_CANONICAL: dict[str, tuple[str, str, str, str]] = {
    "Calculator": ("calculations", "value_type", "value_length", "value_precision"),
    "Formula":    ("formulas",     "type",       "length",       "precision"),
}


def check_monetary_scale(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    for step in ctx.ktr_data.get("steps", []):
        canonical = ctx.step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        keys = _SCALE_KEYS_BY_CANONICAL.get(canonical)
        if keys is None:
            continue
        entries_key, type_key, length_key, precision_key = keys
        cfg = parse_cfg(step.get("config", {}))
        entries = cfg.get(entries_key, cfg.get("fields", []))
        for e in entries:
            if not isinstance(e, dict) or e.get(type_key) != "BigNumber":
                continue
            field_name = (e.get("field_name") or e.get("name") or "").strip().lower()
            scale = ctx.dwh_numeric_scale.get(field_name)
            has_explicit = e.get(length_key) is not None and e.get(precision_key) is not None
            if has_explicit:
                continue
            if scale is not None:
                e[length_key], e[precision_key] = scale
                # D9/D13 (registro de deltas) + contrato del paquete
                # (base.py:9-12, "toda mutación real va acompañada de un
                # Finding con repaired=True") -- mismo patrón que
                # table_key_recovery.py.
                findings.append(Finding(
                    severity="warning", step_name=step.get("name", ""), repaired=True,
                    message=(
                        f"{MONETARY_SCALE_PREFIX}Step '{step.get('name')}': campo '{field_name}' "
                        f"tipado BigNumber sin longitud/precisión -- completado desde el DDL del DWH "
                        f"({scale[0]},{scale[1]})."
                    ),
                ))
            else:
                findings.append(Finding(
                    severity="error", step_name=step.get("name", ""),
                    message=(
                        f"{MONETARY_SCALE_PREFIX}Step '{step.get('name')}': campo '{field_name}' "
                        "tipado BigNumber sin longitud/precisión explícita, y no se pudo resolver "
                        "desde el DDL del DWH (columna no encontrada) -- no se fabrica un valor "
                        f"default; declarar {length_key}/{precision_key} en el config o corregir "
                        "el nombre del campo."
                    ),
                ))
    return findings
