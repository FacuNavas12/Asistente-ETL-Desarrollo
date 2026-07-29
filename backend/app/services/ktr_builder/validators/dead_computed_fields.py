"""H40 (docs/refactor/01-hallazgos.md) — un `Calculator` puede declarar un
campo nuevo (`calculations[].field_name`) que ningún step aguas abajo
consume ni mapea a una tabla destino. No rompe el build (Spoon lo corre
igual, el campo queda flotando en el stream) — es cómputo del LLM que no
aporta nada al resultado, invisible hoy para cualquier validador. Ver D41
(docs/refactor/02-decisiones.md) para el porqué del alcance.

Alcance deliberado, solo `Calculator`: generalizar a Formula/NumberRange/
GroupBy exigiría reconstruir el stream real por step (qué campos ya venían
del upstream vs. cuáles agrega este step puntual — ver
`fields_validate._topo_order`/`_step_output_fields`) para distinguir "campo
nuevo" de "campo que ya estaba". `Calculator` es el único caso donde el
nombre del campo agregado se lee directo del config
(`calculations[].field_name`), sin esa reconstrucción — encaja con el
alcance "menor" del hallazgo. D15 (mejor esfuerzo, no bloquea): esto es
warning, nunca error — un cómputo sin consumidor no rompe nada en Spoon.

Falsos negativos aceptados a propósito, mismo criterio que
`fields_validate.py` ("preferimos no detectar un hueco real antes que
bloquear/marcar mal un .ktr válido por falso positivo"): el pass camina
TODO el subgrafo alcanzable aguas abajo y cuenta el campo como usado si
CUALQUIER step ahí lo consume por nombre — no distingue si un narrowing
intermedio (SelectValues sin incluirlo, GroupBy) lo habría descartado del
stream antes de llegar a ese consumidor. `_consumed_names()` también cubre
dos consumos que `contracts.STEP_CONTRACTS` todavía no modela (gap propio,
no de este pass): `SelectValues` (consume por `select[].name` antes de un
posible rename) y `GroupBy`/`MemoryGroupBy` (consume por
`aggregates[].subject_field`)."""
from __future__ import annotations

from app.services.ktr_builder.common import _yn
from app.services.ktr_builder.contracts import STEP_CONTRACTS, parse_cfg
from app.services.ktr_builder.validators.base import Finding, ValidationContext

DEAD_FIELD_PREFIX = "[Cómputo sin consumidor] "

name = "flag_dead_computed_fields"


def _calculator_added_fields(cfg: dict) -> list[str]:
    seen: dict[str, None] = {}
    for c in cfg.get("calculations", []):
        field_name = c.get("field_name")
        if field_name and _yn(c.get("removed_from_result", c.get("remove"))) != "Y":
            seen.setdefault(field_name, None)
    return list(seen)


def _build_successors(steps: list, hops: list) -> dict[str, list[str]]:
    step_names = {s.get("name") for s in steps}
    succs: dict[str, list[str]] = {n: [] for n in step_names}
    for hop in hops:
        if not hop.get("enabled", True):
            continue
        src, dst = hop.get("from"), hop.get("to")
        if src in succs and dst in step_names:
            succs[src].append(dst)
    return succs


def _consumed_names(canonical: str, cfg: dict) -> set[str]:
    """Nombres que un step consume por nombre — usa STEP_CONTRACTS.consumes
    cuando existe, más los dos casos sin modelar que describe el docstring
    del módulo (SelectValues, GroupBy/MemoryGroupBy)."""
    contract = STEP_CONTRACTS.get(canonical)
    consumed = set(contract.consumes(cfg)) if contract and contract.consumes else set()

    if canonical == "SelectValues":
        select_fields = cfg.get("select") or cfg.get("fields") or cfg.get("columns") or []
        consumed |= {
            f.get("name") for f in select_fields
            if isinstance(f, dict) and f.get("name")
        }
    elif canonical in ("GroupBy", "MemoryGroupBy"):
        consumed |= {
            agg.get("subject") or agg.get("subject_field") or agg.get("field")
            for agg in cfg.get("aggregates", [])
        } - {None, ""}

    return consumed


def _reachable_consumed_names(
    start: str, succs: dict[str, list[str]], step_by_name: dict[str, dict], step_type_aliases: dict[str, str]
) -> set[str]:
    seen: set[str] = set()
    stack = list(succs.get(start, []))
    consumed: set[str] = set()
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        step = step_by_name.get(n)
        if step is not None:
            canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
            cfg = parse_cfg(step.get("config", {}))
            consumed |= _consumed_names(canonical, cfg)
        stack.extend(succs.get(n, []))
    return consumed


def flag_dead_computed_fields(ctx: ValidationContext) -> list[Finding]:
    steps = ctx.ktr_data.get("steps", [])
    hops = ctx.ktr_data.get("hops", [])
    step_by_name = {s.get("name"): s for s in steps}
    succs = _build_successors(steps, hops)

    findings: list[Finding] = []
    for step in steps:
        raw_type = step.get("type", "")
        canonical = ctx.step_type_aliases.get(raw_type, raw_type)
        if canonical != "Calculator":
            continue

        step_name = step.get("name", "")
        cfg = parse_cfg(step.get("config", {}))
        added = _calculator_added_fields(cfg)
        if not added:
            continue

        reachable_consumed = _reachable_consumed_names(step_name, succs, step_by_name, ctx.step_type_aliases)

        for field_name in added:
            if field_name in reachable_consumed:
                continue
            findings.append(Finding(
                severity="warning",
                step_name=step_name,
                message=(
                    f"{DEAD_FIELD_PREFIX}Step '{step_name}' (Calculator): el campo calculado "
                    f"'{field_name}' no lo consume ningún step aguas abajo ni se mapea a ninguna "
                    "columna de tabla destino — cómputo sin efecto en el resultado. Revisar si falta "
                    "el mapeo en el TableOutput/InsertUpdate correspondiente, o si el cálculo sobra."
                ),
            ))

    return findings
