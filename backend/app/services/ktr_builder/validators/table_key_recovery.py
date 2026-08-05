"""H29 (docs/refactor/01-hallazgos.md) — el LLM a veces declara la tabla física
de un step bajo una clave que `contracts.STEP_CONTRACTS.key_aliases` no cubre
(`schema_table`, `dest_table`, ...). `cfg.get("table")` da vacío y el step se
vuelve invisible para el resto del pipeline (matriz R/W del motor de corte,
enforcement SCD1/SCD2, chequeo de carrera de lookup) sin que nadie avise —
ver docs/refactor/02-decisiones.md D40 para el porqué de este diseño.

Recuperación por CONTENIDO, no por posición: si ninguna clave conocida
resolvió `table`, se busca entre los valores string del config cuál coincide
(case-insensitive, sin prefijo de schema) con una tabla física real conocida
del ETL (`ctx.known_tables`). Exactamente un match -> se renombra esa clave a
`table`. Cero o varios matches -> no se adivina, se reporta severidad error
(D15: notifica, no bloquea — el .ktr sale igual).

`TABLE_KEY_PREFIX` va DENTRO de `Finding.message` (no lo agrega el caller):
con más de un pass en `PRE_EMIT_PASSES` (D41), un caller que prefijara TODO
`run_passes()` con esta constante etiquetaría mal los findings de cualquier
otro pass — cada pass es dueño de su propio prefijo, si tiene uno."""
from __future__ import annotations

from app.services.ktr_builder.contracts import TABLE_BEARING_STEPS, normalize_config, parse_cfg
from app.services.ktr_builder.validators.base import Finding, ValidationContext

TABLE_KEY_PREFIX = "[Clave de tabla] "

name = "recover_table_key"


def _bare(value: str) -> str:
    """'public.stg_clientes' -> 'stg_clientes'. Sin schema, minúsculas, sin espacios."""
    return value.strip().lower().rsplit(".", 1)[-1]


def recover_table_key(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    for step in ctx.ktr_data.get("steps", []):
        raw_type = step.get("type", "")
        canonical = ctx.step_type_aliases.get(raw_type, raw_type)
        if canonical not in TABLE_BEARING_STEPS:
            continue

        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        if not isinstance(cfg, dict):
            continue
        step_name = step.get("name", "")

        if (cfg.get("table") or "").strip():
            step["config"] = cfg  # persiste normalización de alias ya conocida
            continue

        candidates = [
            key for key, value in cfg.items()
            if key != "table" and isinstance(value, str) and _bare(value) in ctx.known_tables
        ]

        if len(candidates) == 1:
            key = candidates[0]
            resolved = _bare(cfg.pop(key))
            cfg["table"] = resolved
            step["config"] = cfg
            findings.append(Finding(
                severity="warning",
                repaired=True,
                step_name=step_name,
                message=(
                    f"{TABLE_KEY_PREFIX}Step '{step_name}' ({canonical}): la clave '{key}' no es un "
                    f"alias conocido de tabla, pero su valor coincide con la tabla real '{resolved}' "
                    "— renombrada a 'table'. Revisar si el LLM debería haber usado 'table' directamente."
                ),
            ))
        elif len(candidates) == 0:
            findings.append(Finding(
                severity="error",
                step_name=step_name,
                message=(
                    f"{TABLE_KEY_PREFIX}Step '{step_name}' ({canonical}) no declara 'table' y ningún "
                    "campo de su config coincide con una tabla real conocida de este ETL. El step no "
                    "participa en la matriz de lectura/escritura ni en las validaciones de dimensión "
                    "— completar la tabla a mano en Spoon antes de ejecutar."
                ),
            ))
        else:
            findings.append(Finding(
                severity="error",
                step_name=step_name,
                message=(
                    f"{TABLE_KEY_PREFIX}Step '{step_name}' ({canonical}) no declara 'table' y hay "
                    f"{len(candidates)} campos ambiguos que podrían serlo ({', '.join(candidates)}) — "
                    "no se adivina. Completar la tabla a mano en Spoon antes de ejecutar."
                ),
            ))
    return findings
