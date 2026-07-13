"""Validación de resolución de campos: recorre el grafo de steps/hops en orden
topológico y calcula qué campos produce/propaga cada step, para verificar que
todo campo referenciado por un step consumidor (TableOutput, DimensionLookup,
DBLookup, etc.) exista en el stream que le llega. Mismo síntoma que Spoon
reporta en runtime como "Could not find field X in stream" — acá se detecta
en build-time, antes de serializar el XML.

La semántica de qué produce/consume cada tipo de step vive en STEP_CONTRACTS
(contracts.py) — este módulo solo recorre el grafo y aplica esa semántica,
no la reimplementa.

Cuando la producción de un step no se puede resolver con certeza (SQL de
TableInput no parseable, SELECT *, step sin contrato relevado acá) se marca
como desconocida y no se valida aguas abajo de ese punto — preferimos no
detectar un hueco real antes que bloquear un .ktr válido por falso positivo.
"""
from __future__ import annotations

from app.services.ktr_builder.contracts import STEP_CONTRACTS, missing_required_keys
from app.services.ktr_builder.contracts import parse_cfg as _parse_cfg


def _step_output_fields(canonical_type: str, cfg: dict, upstream: set[str] | None) -> set[str] | None:
    """Campos que el step produce hacia adelante. None = desconocido (no
    validar consumidores aguas abajo de este punto)."""
    contract = STEP_CONTRACTS.get(canonical_type)
    if contract is not None and contract.produces is not None:
        return contract.produces(cfg, upstream)
    # Passthrough conservador: cualquier step sin contrato relevado acá no
    # elimina campos del stream (evita falsos positivos en tipos no auditados).
    return upstream


def _required_fields(canonical_type: str, cfg: dict) -> set[str]:
    """Campos que ese step consumidor necesita encontrar en el stream de entrada."""
    contract = STEP_CONTRACTS.get(canonical_type)
    if contract is not None and contract.consumes is not None:
        return contract.consumes(cfg)
    return set()


def _incomplete_producer_reason(canonical_type: str, cfg: dict) -> str | None:
    """Si el step es de un tipo que normalmente aporta campos nuevos al stream
    pero su config no trae lo mínimo para hacerlo (required_keys del
    contrato), devuelve una razón legible. None si el tipo no aplica o está
    configurado lo suficiente (no valida que el campo específico faltante
    venga de acá — solo que el step está "vacío" y es sospechoso de ser el
    hueco real)."""
    missing = missing_required_keys(canonical_type, cfg)
    return missing[0][1] if missing else None


def _nearest_incomplete_ancestor(
    start: str,
    preds: dict[str, list[str]],
    step_by_name: dict[str, dict],
    step_type_aliases: dict[str, str],
    order_index: dict[str, int],
) -> tuple[str, str, str] | None:
    """Recorre hacia atrás todo el árbol de predecesores de `start` buscando
    el step con config incompleto más cercano (mayor order_index = más cerca
    del consumidor). None si ningún ancestro califica."""
    seen: set[str] = set()
    stack = list(preds.get(start, []))
    best: tuple[str, str, str] | None = None
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        step = step_by_name.get(p)
        if step is not None:
            canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
            reason = _incomplete_producer_reason(canonical, _parse_cfg(step.get("config", {})))
            if reason and (best is None or order_index.get(p, -1) > order_index.get(best[0], -1)):
                best = (p, canonical, reason)
        stack.extend(preds.get(p, []))
    return best


def repair_select_values_narrowing(ktr_data: dict, step_type_aliases: dict[str, str]) -> list[str]:
    """
    Pre-pass mecánico (sin LLM): si un SelectValues con lista explícita de
    select/fields deja afuera un campo que (a) existía en el stream justo
    antes de ese SelectValues, y (b) lo necesita algún consumidor aguas
    abajo, lo reinyecta en la lista de select de ese SelectValues.

    Seguro porque solo AGREGA un campo que ya estaba disponible — nunca
    quita ni reinterpreta nada que el modelo puso a propósito. No toca
    GroupBy/MemoryGroupBy (ahí no hay reinyección segura sin decisión
    semántica de group vs. aggregate).

    Muta ktr_data in-place. Devuelve warnings, uno por campo reinyectado.
    """
    steps = ktr_data.get("steps", [])
    hops = ktr_data.get("hops", [])
    step_by_name = {s.get("name"): s for s in steps}

    preds: dict[str, list[str]] = {s.get("name"): [] for s in steps}
    succs: dict[str, list[str]] = {s.get("name"): [] for s in steps}
    for hop in hops:
        if not hop.get("enabled", True):
            continue
        src, dst = hop.get("from"), hop.get("to")
        if src in succs and dst in preds:
            succs[src].append(dst)
            preds[dst].append(src)

    in_degree = {name: len(p) for name, p in preds.items()}
    queue = [n for n, d in in_degree.items() if d == 0]
    order: list[str] = []
    seen = set(queue)
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in succs.get(n, []):
            in_degree[m] -= 1
            if in_degree[m] == 0 and m not in seen:
                seen.add(m)
                queue.append(m)
    for name in step_by_name:
        if name not in order:
            order.append(name)

    upstream_by_step: dict[str, set[str] | None] = {}
    produced: dict[str, set[str] | None] = {}
    warnings: list[str] = []

    def _recompute(name: str) -> None:
        step = step_by_name[name]
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        cfg = _parse_cfg(step.get("config", {}))
        pred_names = preds.get(name, [])
        if not pred_names:
            upstream = None
        else:
            pred_outputs = [produced.get(p) for p in pred_names]
            upstream = None if any(p is None for p in pred_outputs) else set().union(*pred_outputs)
        upstream_by_step[name] = upstream
        produced[name] = _step_output_fields(canonical, cfg, upstream)

    for name in order:
        _recompute(name)

    changed = True
    while changed:
        changed = False
        for name in order:
            step = step_by_name[name]
            canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
            cfg = _parse_cfg(step.get("config", {}))
            upstream = upstream_by_step.get(name)
            if upstream is None:
                continue
            missing = _required_fields(canonical, cfg) - upstream
            if not missing:
                continue
            for pred_name in preds.get(name, []):
                pred_step = step_by_name.get(pred_name)
                if pred_step is None:
                    continue
                pred_canonical = step_type_aliases.get(pred_step.get("type", ""), pred_step.get("type", ""))
                if pred_canonical != "SelectValues":
                    continue
                pred_cfg = _parse_cfg(pred_step.get("config", {}))
                select_fields = pred_cfg.get("select") or pred_cfg.get("fields") or pred_cfg.get("columns")
                if not isinstance(select_fields, list) or not select_fields:
                    continue
                pre_select = upstream_by_step.get(pred_name)
                if pre_select is None:
                    continue
                recoverable = missing & pre_select
                if not recoverable:
                    continue
                for field in sorted(recoverable):
                    select_fields.append({"name": field, "rename": field})
                    warnings.append(
                        f"SelectValues '{pred_name}' no incluía '{field}' (requerido por '{name}') — "
                        "reinyectado automáticamente (ya existía en el stream de entrada)."
                    )
                pred_step["config"] = pred_cfg
                for n2 in order:
                    _recompute(n2)
                changed = True
                break
            if changed:
                break

    return warnings


def validate_field_resolution(ktr_data: dict, step_type_aliases: dict[str, str]) -> list[str]:
    """Recorre el grafo por hops en orden topológico. Devuelve errores (no
    warnings) — a diferencia del resto del módulo esto SIEMPRE bloquea el
    build, porque el .ktr resultante fallaría en Spoon con
    'Could not find field X in stream'."""
    steps = ktr_data.get("steps", [])
    hops = ktr_data.get("hops", [])
    step_by_name = {s.get("name"): s for s in steps}

    preds: dict[str, list[str]] = {s.get("name"): [] for s in steps}
    succs: dict[str, list[str]] = {s.get("name"): [] for s in steps}
    for hop in hops:
        if not hop.get("enabled", True):
            continue
        src, dst = hop.get("from"), hop.get("to")
        if src in succs and dst in preds:
            succs[src].append(dst)
            preds[dst].append(src)

    in_degree = {name: len(p) for name, p in preds.items()}
    queue = [n for n, d in in_degree.items() if d == 0]
    order: list[str] = []
    seen = set(queue)
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in succs.get(n, []):
            in_degree[m] -= 1
            if in_degree[m] == 0 and m not in seen:
                seen.add(m)
                queue.append(m)
    for name in step_by_name:
        if name not in order:
            order.append(name)  # ciclo/desconectado — no lo bloquea esta validación

    order_index = {name: i for i, name in enumerate(order)}
    produced: dict[str, set[str] | None] = {}
    errors: list[str] = []

    for name in order:
        step = step_by_name[name]
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        cfg = _parse_cfg(step.get("config", {}))

        pred_names = preds.get(name, [])
        if not pred_names:
            upstream: set[str] | None = None
        else:
            pred_outputs = [produced.get(p) for p in pred_names]
            upstream = None if any(p is None for p in pred_outputs) else set().union(*pred_outputs)

        if upstream is not None:
            missing = _required_fields(canonical, cfg) - upstream
            if missing:
                producers = pred_names or ["(sin step de entrada)"]
                incomplete = _nearest_incomplete_ancestor(
                    name, preds, step_by_name, step_type_aliases, order_index
                )
                for field in sorted(missing):
                    if incomplete:
                        bad_name, bad_type, reason = incomplete
                        errors.append(
                            f"Campo '{field}' no se produce: '{bad_name}' ({bad_type}) {reason} "
                            f"(consumidor aguas abajo: '{name}')."
                        )
                    else:
                        errors.append(
                            f"Campo '{field}' requerido por '{name}' no está en el stream "
                            f"(productores aguas arriba: {producers})."
                        )

        produced[name] = _step_output_fields(canonical, cfg, upstream)

    return errors
