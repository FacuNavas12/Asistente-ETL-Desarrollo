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

import re

from app.services.ktr_builder.contracts import ROW_GENERATOR_TYPES, STEP_CONTRACTS, missing_required_keys
from app.services.ktr_builder.contracts import parse_cfg as _parse_cfg

# Prefijo que marca un mensaje de esta validación como advertencia de integridad
# de datos (severidad "error" en el frontend) en vez de un warning cosmético de
# buenas prácticas. build.py lo agrega a `warnings` sin abortar el build —
# etl_generator.py lo detecta por este prefijo para promoverlo a `Validacion`
# tipo="error" en la respuesta.
FIELD_INTEGRITY_PREFIX = "[Integridad de datos] "


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


def _topo_order(steps: list, hops: list) -> tuple[list[str], dict[str, list[str]]]:
    """Orden topológico por hops habilitados + mapa de predecesores por step.
    Steps en ciclo/desconectados se agregan al final del orden (no bloquea
    esta función — cada validador decide si eso es un problema para él)."""
    step_names = [s.get("name") for s in steps]
    preds: dict[str, list[str]] = {name: [] for name in step_names}
    succs: dict[str, list[str]] = {name: [] for name in step_names}
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
    for name in step_names:
        if name not in order:
            order.append(name)  # ciclo/desconectado — no lo bloquea esta función

    return order, preds


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

    order, preds = _topo_order(steps, hops)

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


def find_missing_field_producers(ktr_data: dict, step_type_aliases: dict[str, str]) -> list[dict]:
    """Igual recorrido que validate_field_resolution, pero devuelve registros
    estructurados en vez de mensajes formateados — para que un caller (ver
    repair.py repair_integrity_gaps) pueda actuar programáticamente sobre el
    step culpable en vez de parsear texto de error.

    Cada registro: {field, consumer, consumer_type, producers, culprit_step,
    culprit_type, reason}. culprit_step es None si no se pudo atribuir el
    hueco a un ancestro con config incompleto (ver _nearest_incomplete_ancestor)
    — típicamente porque el step que debería producir el campo ni siquiera
    está conectado por hops, no porque su config esté vacía."""
    steps = ktr_data.get("steps", [])
    hops = ktr_data.get("hops", [])
    step_by_name = {s.get("name"): s for s in steps}

    order, preds = _topo_order(steps, hops)
    order_index = {name: i for i, name in enumerate(order)}
    produced: dict[str, set[str] | None] = {}
    records: list[dict] = []

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
                incomplete = _nearest_incomplete_ancestor(
                    name, preds, step_by_name, step_type_aliases, order_index
                )
                for field in sorted(missing):
                    records.append({
                        "field": field,
                        "consumer": name,
                        "consumer_type": canonical,
                        "producers": list(pred_names),
                        "culprit_step": incomplete[0] if incomplete else None,
                        "culprit_type": incomplete[1] if incomplete else None,
                        "reason": incomplete[2] if incomplete else None,
                    })

        produced[name] = _step_output_fields(canonical, cfg, upstream)

    return records


def validate_field_resolution(ktr_data: dict, step_type_aliases: dict[str, str]) -> list[str]:
    """Recorre el grafo por hops en orden topológico. Devuelve mensajes (sin
    el prefijo FIELD_INTEGRITY_PREFIX) para cada campo que un step consumidor
    referencia pero que ningún step aguas arriba produce — mismo síntoma que
    Spoon reporta en runtime como 'Could not find field X in stream'.

    build.py NO aborta el build por estos mensajes: el .ktr se genera igual y
    el mensaje se promueve a Validacion tipo="error" en la respuesta (severidad
    máxima) — Spoon fallaría en runtime con 'Could not find field X in stream',
    pero el usuario decide si corregirlo o regenerar, no se le niega el archivo.

    Formatea find_missing_field_producers() — ver ese para la versión
    estructurada que consume repair.py."""
    errors: list[str] = []
    for rec in find_missing_field_producers(ktr_data, step_type_aliases):
        if rec["culprit_step"]:
            errors.append(
                f"Campo '{rec['field']}' no se produce: '{rec['culprit_step']}' ({rec['culprit_type']}) "
                f"{rec['reason']} (consumidor aguas abajo: '{rec['consumer']}')."
            )
        else:
            producers = rec["producers"] or ["(sin step de entrada)"]
            errors.append(
                f"Campo '{rec['field']}' requerido por '{rec['consumer']}' no está en el stream "
                f"(productores aguas arriba: {producers})."
            )
    return errors


def find_nearest_source_table_name(
    ktr_data: dict, step_type_aliases: dict[str, str], start_step_name: str
) -> str | None:
    """Camina hacia atrás desde start_step_name buscando el TableInput/CsvInput/
    ExcelInput/JsonInput/TextFileInput más cercano y devuelve un nombre de
    tabla/archivo legible. Usado por repair.py (repair_integrity_gaps) para
    sintetizar el `value` de campos de auditoría tipo `stg_origen` cuando no
    hay otra forma de saber de qué tabla vino la fila. None si no encuentra
    ninguno en todo el árbol de ancestros."""
    steps = ktr_data.get("steps", [])
    hops = ktr_data.get("hops", [])
    step_by_name = {s.get("name"): s for s in steps}
    _, preds = _topo_order(steps, hops)

    seen: set[str] = set()
    stack = list(preds.get(start_step_name, []))
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        step = step_by_name.get(name)
        if step is not None:
            canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
            cfg = _parse_cfg(step.get("config", {}))
            if canonical == "TableInput":
                match = re.search(r"FROM\s+([A-Za-z0-9_.\"\[\]]+)", cfg.get("sql", "") or "", re.IGNORECASE)
                if match:
                    return match.group(1).split(".")[-1].strip('"[]')
            elif canonical in ("CsvInput", "ExcelInput", "JsonInput", "TextFileInput"):
                fname = cfg.get("filename") or cfg.get("file") or cfg.get("path")
                if fname:
                    return str(fname)
        stack.extend(preds.get(name, []))
    return None


def validate_row_sources(ktr_data: dict, step_type_aliases: dict[str, str]) -> list[str]:
    """Detecta ramas del grafo que van a producir 0 filas de forma
    determinística — el mismo síntoma que un `Constant`/`Add constants`
    colgado de un `WriteToLog` sin entrada (WriteToLog no genera filas, solo
    loggea/pasa las que ya recibió) o un `JoinRows` (cartesiano) cruzando
    contra una rama de parámetros vacía, que vacía TODO el resultado del
    join sin importar cuántas filas traiga el otro lado.

    Propaga "garantizado 0 filas" en orden topológico:
      - un step de ROW_GENERATOR_TYPES nunca es 0 filas (genera las suyas).
      - un step SIN predecesores que no es generador nunca corre -> 0 filas.
      - JoinRows (producto cartesiano): 0 filas si CUALQUIERA de sus ramas
        de entrada es 0 filas (no alcanza con que el lado principal tenga
        datos).
      - cualquier otro step: 0 filas solo si TODOS sus predecesores lo son
        (passthrough conservador — evita falsos positivos en steps con
        múltiples entradas que no son cartesianos)."""
    steps = ktr_data.get("steps", [])
    step_by_name = {s.get("name"): s for s in steps}
    order, preds = _topo_order(steps, ktr_data.get("hops", []))

    zero: dict[str, bool] = {}
    for name in order:
        step = step_by_name.get(name)
        if step is None:
            continue
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        pred_names = preds.get(name, [])
        if canonical in ROW_GENERATOR_TYPES:
            zero[name] = False
        elif not pred_names:
            zero[name] = True
        elif canonical == "JoinRows":
            zero[name] = any(zero.get(p, False) for p in pred_names)
        else:
            zero[name] = all(zero.get(p, False) for p in pred_names)

    errors: list[str] = []
    for name in order:
        if not zero.get(name):
            continue
        step = step_by_name.get(name)
        if step is None:
            continue
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        pred_names = preds.get(name, [])

        if not pred_names:
            errors.append(
                f"Step '{name}' ({canonical}) no tiene fuente de filas: no tiene ningún step "
                f"predecesor y '{canonical}' no es un step generador (TableInput/CsvInput/"
                "RowGenerator/GetSystemInfo/...) — nunca va a ejecutarse ni a producir filas. "
                "Si necesita sembrar literales o parámetros sin depender de otra tabla, anteponer "
                "un 'RowGenerator' (Generate Rows, 1 fila)."
            )
        elif canonical == "JoinRows":
            zeroed = [p for p in pred_names if zero.get(p)]
            errors.append(
                f"Step '{name}' (JoinRows): la rama '{zeroed[0] if zeroed else '?'}' llega con 0 "
                "filas garantizadas — JoinRows es un cruce cartesiano: si un solo lado está vacío, "
                "el resultado completo queda vacío sin importar cuántas filas traiga el otro lado. "
                "Revisar la fuente de filas de esa rama."
            )
        else:
            errors.append(
                f"Step '{name}' ({canonical}) hereda 0 filas garantizadas de sus predecesores "
                f"({', '.join(pred_names)}) — nunca va a procesar ninguna fila."
            )

    return errors


def validate_dimension_lookup_races(ktr_data: dict, step_type_aliases: dict[str, str]) -> list[str]:
    """PDI ejecuta todos los steps de una transformación en paralelo (no en el
    orden visual del canvas). Si una misma transformación carga una dimensión
    vía `DimensionLookup`/`CombinationLookup` (insert-if-missing) Y ADEMÁS
    busca el SK de esa misma tabla vía un `DBLookup` separado, el DBLookup
    puede ejecutar antes de que el DimensionLookup haya insertado/commiteado
    la fila nueva — condición de carrera, FK nula en runtime (INSERT en la
    tabla de hechos falla o queda con FK inconsistente).

    `DimensionLookup`/`CombinationLookup` ya devuelven el SK en su propio
    campo de retorno — el DBLookup separado casi siempre es redundante."""
    errors: list[str] = []
    load_tables: dict[str, str] = {}
    lookup_tables: dict[str, str] = {}

    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        if canonical not in ("DimensionLookup", "CombinationLookup", "DBLookup"):
            continue
        cfg = _parse_cfg(step.get("config", {}))
        table = (cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or "").strip().lower()
        if not table:
            continue
        if canonical in ("DimensionLookup", "CombinationLookup"):
            load_tables.setdefault(table, step.get("name"))
        else:
            lookup_tables.setdefault(table, step.get("name"))

    for table, dbl_name in lookup_tables.items():
        loader_name = load_tables.get(table)
        if loader_name is None:
            continue
        errors.append(
            f"Step '{dbl_name}' (DBLookup) busca el SK de '{table}' con un lookup separado, pero "
            f"'{loader_name}' ya carga esa misma dimensión en esta transformación — PDI ejecuta "
            "todos los steps en paralelo (no en el orden visual), así que el DBLookup puede correr "
            "antes de que el DimensionLookup/CombinationLookup commitee la fila nueva (condición de "
            f"carrera, FK nula en runtime). '{loader_name}' ya devuelve el SK en su propio campo de "
            "retorno — conectar el step de hechos directamente a esa salida y eliminar el DBLookup "
            "redundante, o separar la carga de dimensiones y la carga de hechos en dos "
            "transformaciones distintas si de verdad necesitan mecanismos distintos."
        )

    return errors
