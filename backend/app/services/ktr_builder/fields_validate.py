"""Validación de resolución de campos: recorre el grafo de steps/hops en orden
topológico y calcula qué campos produce/propaga cada step, para verificar que
todo campo referenciado por un step consumidor (TableOutput, DimensionLookup,
DBLookup, etc.) exista en el stream que le llega. Mismo síntoma que Spoon
reporta en runtime como "Could not find field X in stream" — acá se detecta
en build-time, antes de serializar el XML.

Cuando la producción de un step no se puede resolver con certeza (SQL de
TableInput no parseable, SELECT *, step sin semántica relevada acá) se marca
como desconocida y no se valida aguas abajo de ese punto — preferimos no
detectar un hueco real antes que bloquear un .ktr válido por falso positivo.
"""
from __future__ import annotations

import json
import re

from app.services.ktr_builder.common import _yn


def _parse_cfg(raw) -> dict:
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    return raw or {}


def _select_columns(sql: str) -> set[str] | None:
    """Extrae nombres de columna de un SELECT simple (sin subqueries). None si
    no se puede resolver con certeza (SELECT *, expresión no reconocida) —
    en ese caso el step se trata como fuente desconocida."""
    if not sql or not sql.strip():
        return None
    m = re.search(r"select\s+(.*?)\s+from\s", sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    cols_str = m.group(1)
    if "*" in cols_str:
        return None

    parts, current, depth = [], "", 0
    for ch in cols_str:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)

    cols: set[str] = set()
    for p in parts:
        p = p.strip()
        if not p:
            continue
        alias_match = re.search(r"\bas\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", p, re.IGNORECASE)
        if alias_match:
            cols.add(alias_match.group(1))
            continue
        token = p.split()[-1] if " " in p else p
        token = token.split(".")[-1].strip('`"[]')
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", token):
            cols.add(token)
        else:
            return None  # expresión no resoluble -> se pierde certeza para todo el SELECT
    return cols


def _step_output_fields(canonical_type: str, cfg: dict, upstream: set[str] | None) -> set[str] | None:
    """Campos que el step produce hacia adelante. None = desconocido (no
    validar consumidores aguas abajo de este punto)."""
    if canonical_type == "TableInput":
        return _select_columns(cfg.get("sql", ""))

    if canonical_type in ("CsvInput", "ExcelInput", "JsonInput", "TextFileInput"):
        names = {f.get("name") for f in cfg.get("fields", []) if isinstance(f, dict) and f.get("name")}
        return names or None

    if upstream is None:
        return None

    if canonical_type in ("Constant", "GetSystemInfo"):
        added = {f.get("name") for f in cfg.get("fields", []) if isinstance(f, dict) and f.get("name")}
        return upstream | added

    if canonical_type == "Calculator":
        added = {
            c.get("field_name") for c in cfg.get("calculations", [])
            if c.get("field_name") and _yn(c.get("removed_from_result", c.get("remove"))) != "Y"
        }
        return upstream | added

    if canonical_type == "NumberRange":
        return upstream | {cfg.get("output_field", "range")}

    if canonical_type in ("GroupBy", "MemoryGroupBy"):
        # GroupBy descarta el resto del stream: solo sobreviven los campos de
        # agrupación y los resultados de agregación (mismo comportamiento que
        # GroupByMeta/MemoryGroupByMeta en Kettle).
        group = {
            gf if isinstance(gf, str) else gf.get("name", "")
            for gf in cfg.get("group_fields", [])
        }
        aggregates = {
            agg.get("name") or agg.get("result_field") or agg.get("aggregate") or agg.get("output_field")
            for agg in cfg.get("aggregates", [])
        }
        return (group | aggregates) - {None, ""}

    if canonical_type == "Formula":
        added = {
            f.get("field_name") or f.get("name")
            for f in cfg.get("formulas", cfg.get("fields", []))
            if (f.get("field_name") or f.get("name"))
        }
        return upstream | added

    if canonical_type == "SelectValues":
        select_fields = cfg.get("select") or cfg.get("fields") or cfg.get("columns") or []
        remove_fields = {
            r if isinstance(r, str) else r.get("name", "")
            for r in cfg.get("remove", [])
        }
        if select_fields:
            out = set()
            for f in select_fields:
                if isinstance(f, str):
                    out.add(f)
                else:
                    out.add(f.get("rename") or f.get("name", ""))
            return out - {""}
        return upstream - remove_fields

    if canonical_type in ("DimensionLookup", "CombinationLookup"):
        return_field = (cfg.get("return_field") or cfg.get("returnfield") or
                        cfg.get("sk_field") or cfg.get("surrogate_key") or "id_sk")
        return upstream | {return_field}

    if canonical_type == "DBLookup":
        added = {
            r.get("rename") or r.get("name")
            for r in cfg.get("return_fields", cfg.get("returns", []))
            if (r.get("rename") or r.get("name"))
        }
        return upstream | added

    if canonical_type == "StreamLookup":
        added = {
            v.get("rename") or v.get("name")
            for v in cfg.get("values", cfg.get("fields", []))
            if (v.get("rename") or v.get("name"))
        }
        return upstream | added

    # Passthrough conservador: cualquier step sin semántica relevada acá no
    # elimina campos del stream (evita falsos positivos en tipos no auditados).
    return upstream


def _required_fields(canonical_type: str, cfg: dict) -> set[str]:
    """Campos que ese step consumidor necesita encontrar en el stream de entrada."""
    if canonical_type == "TableOutput":
        return {
            f.get("stream_name") or f.get("source")
            for f in cfg.get("fields", [])
            if (f.get("stream_name") or f.get("source"))
        }
    if canonical_type in ("InsertUpdate", "Update"):
        req = {
            k.get("stream_field") or k.get("name")
            for k in cfg.get("keys", [])
            if (k.get("stream_field") or k.get("name"))
        }
        req |= {
            f.get("stream_field") or f.get("name")
            for f in cfg.get("fields", [])
            if (f.get("stream_field") or f.get("name"))
        }
        return req
    if canonical_type == "Delete":
        return {
            k.get("stream_field") or k.get("name")
            for k in cfg.get("keys", [])
            if (k.get("stream_field") or k.get("name"))
        }
    if canonical_type == "DimensionLookup":
        req = {
            k.get("stream") or k.get("stream_field") or k.get("name")
            for k in cfg.get("keys", [])
            if (k.get("stream") or k.get("stream_field") or k.get("name"))
        }
        if cfg.get("date_field"):
            req.add(cfg["date_field"])
        return req
    if canonical_type == "CombinationLookup":
        return {
            k.get("stream") or k.get("name")
            for k in cfg.get("keys", [])
            if (k.get("stream") or k.get("name"))
        }
    if canonical_type == "DBLookup":
        return {
            k.get("stream_field") or k.get("name")
            for k in cfg.get("keys", [])
            if (k.get("stream_field") or k.get("name"))
        }
    if canonical_type == "StreamLookup":
        return {
            k.get("stream") or k.get("name")
            for k in cfg.get("keys", [])
            if (k.get("stream") or k.get("name"))
        }
    if canonical_type == "SortRows":
        out = set()
        for f in cfg.get("fields", cfg.get("sort_fields", [])):
            name = (f.get("name") or f.get("field") or f.get("column")) if isinstance(f, dict) else f
            if name:
                out.add(name)
        return out
    if canonical_type == "Unique":
        return {
            (f if isinstance(f, str) else f.get("name", ""))
            for f in cfg.get("fields", [])
        } - {""}
    return set()


def _incomplete_producer_reason(canonical_type: str, cfg: dict) -> str | None:
    """Si el step es de un tipo que normalmente aporta campos nuevos al stream
    pero su config no trae lo mínimo para hacerlo, devuelve una razón legible.
    None si el tipo no aplica o está configurado lo suficiente para producir
    algo (no valida que el campo específico faltante venga de acá — solo que
    el step está "vacío" y es sospechoso de ser el hueco real)."""
    if canonical_type == "DBLookup":
        if not cfg.get("return_fields", cfg.get("returns", [])):
            return "no declara campos de retorno (return_fields) en su config"
    elif canonical_type in ("DimensionLookup", "CombinationLookup"):
        if not cfg.get("keys"):
            return "no declara keys de búsqueda en su config"
    elif canonical_type == "StreamLookup":
        if not cfg.get("values", cfg.get("fields", [])):
            return "no declara values a traer del stream de lookup en su config"
    elif canonical_type == "Calculator":
        if not cfg.get("calculations"):
            return "no declara calculations en su config"
    elif canonical_type == "Formula":
        if not cfg.get("formulas", cfg.get("fields", [])):
            return "no declara formulas en su config"
    elif canonical_type in ("GroupBy", "MemoryGroupBy"):
        if not cfg.get("aggregates"):
            return "no declara aggregates en su config"
    elif canonical_type == "NumberRange":
        if not cfg.get("input_field"):
            return "no declara input_field en su config"
    return None


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
