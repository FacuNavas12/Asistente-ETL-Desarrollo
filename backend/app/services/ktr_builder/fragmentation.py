"""
F3 (Fase 3 del handoff) — motor de corte. Diseño validado en `03-plan.md`
(reporte F2, 2026-07-22) contra `err1.ktr`/`err2.ktr` (H21). Wireado a
`etl_generator.py` (`split_ktr_by_cut`, `_build_ktr_stage`, `_build_job_plan`
N-ario) y a `lineage_builder.stitch_lineage_many` a nivel de servicio
(2026-07-24) — ver nota de estado al pie de este módulo y en `03-plan.md`
para el hueco que queda (ETLGenerateResponse todavía fija a 1 KTR por etapa).

Algoritmo (resumen, detalle completo en 03-plan.md):
1. build_rw_matrix: {tabla: {step: "R"|"W"|"RW"}} — reusa H19 (rol por tipo
   de step) + el update=N de D16 para DimensionLookup en rol fact_lookup.
2. Dos disparadores de corte: C1 (W+R por steps distintos) y C1-bis (doble
   escritor). ExecSQL y steps sin tabla no participan (D15: notifica, no
   bloquea).
3. Componentes conexos por hops (grafo no dirigido, ignorando tablas). Si
   escritor y lector de una tabla-disparadora ya caen en componentes
   distintos -> no hace falta partir más, alcanza con ordenarlos. Si caen
   en el mismo componente: excepción self-lookup/insert-new-only (lectura
   con camino dirigido hacia la escritura) no dispara corte; cualquier otra
   relación en el mismo componente es el caso genuinamente difícil (sin
   evidencia en el corpus actual) -> se notifica, no se parte (D15).
4. Orden entre componentes: grafo dirigido componente-a-componente (una
   arista por cada relación tabla-disparadora escritor->lector/otro-escritor),
   orden topológico. Ciclo real -> notifica (D15), no bloquea.
"""
from __future__ import annotations

from app.services.ktr_builder.contracts import normalize_config, parse_cfg

# H19 (01-hallazgos.md): rol por tipo de step. DimensionLookup es el único
# condicional — su rol depende de cfg["update"] (D16: "N" = fact_lookup,
# forzado solo-lectura por dimension_step_policy antes de llegar acá).
_WRITE_ONLY = {"TableOutput", "InsertUpdate", "Update", "Delete"}
_ALWAYS_RW = {"CombinationLookup"}
_READ_ONLY = {"DBLookup", "TableInput"}
_NOT_CLASSIFIABLE = {"ExecSQL"}


def _step_rw(canonical: str, cfg: dict) -> str | None:
    """"R" | "W" | "RW" | None (sin tabla propia, o no clasificable —
    ExecSQL: SQL arbitrario, Q2 de F1 ya lo marcó fuera de la matriz)."""
    if canonical in _NOT_CLASSIFIABLE:
        return None
    if canonical in _WRITE_ONLY:
        return "W"
    if canonical == "DimensionLookup":
        return "R" if str(cfg.get("update", "Y")).strip().upper() == "N" else "RW"
    if canonical in _ALWAYS_RW:
        return "RW"
    if canonical in _READ_ONLY:
        return "R"
    return None


def build_rw_matrix(ktr_data: dict, step_type_aliases: dict[str, str]) -> dict[str, dict[str, str]]:
    """{tabla_lower: {step_name: "R"|"W"|"RW"}}. Steps sin tabla o ExecSQL no aportan."""
    matrix: dict[str, dict[str, str]] = {}
    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        table = (cfg.get("table") or "").strip()
        if not table:
            continue
        rw = _step_rw(canonical, cfg)
        if rw is None:
            continue
        matrix.setdefault(table.lower(), {})[step.get("name", "")] = rw
    return matrix


def _connected_components(steps: list[dict], hops: list[dict]) -> dict[str, int]:
    """Componente conexo (grafo NO dirigido de hops, ignorando tablas) por step_name."""
    names = [s.get("name", "") for s in steps]
    adjacency: dict[str, set] = {n: set() for n in names}
    for hop in hops:
        a, b = hop.get("from", ""), hop.get("to", "")
        if a in adjacency and b in adjacency:
            adjacency[a].add(b)
            adjacency[b].add(a)
    comp: dict[str, int] = {}
    comp_id = 0
    for n in names:
        if n in comp:
            continue
        stack = [n]
        comp[n] = comp_id
        while stack:
            cur = stack.pop()
            for nxt in adjacency.get(cur, ()):
                if nxt not in comp:
                    comp[nxt] = comp_id
                    stack.append(nxt)
        comp_id += 1
    return comp


def _reaches(a: str, b: str, hops: list[dict]) -> bool:
    """True si hay camino DIRIGIDO de a hacia b por hops habilitados (usado
    para la excepción self-lookup: ¿la lectura corre aguas arriba de la
    escritura?)."""
    adjacency: dict[str, list[str]] = {}
    for hop in hops:
        if not hop.get("enabled", True):
            continue
        adjacency.setdefault(hop.get("from", ""), []).append(hop.get("to", ""))
    if a == b:
        return True
    visited = {a}
    stack = list(adjacency.get(a, []))
    while stack:
        cur = stack.pop()
        if cur == b:
            return True
        if cur in visited:
            continue
        visited.add(cur)
        stack.extend(adjacency.get(cur, []))
    return False


def compute_cut(ktr_data: dict, step_type_aliases: dict[str, str]) -> dict:
    """{"groups": [[step_name, ...], ...] ya en orden de ejecución,
    "notifications": [str]} — ver algoritmo completo en el docstring del
    módulo / reporte F2 en 03-plan.md. NO reordena steps dentro de un grupo
    (eso lo hace _auto_layout aguas abajo); solo decide partición + orden
    entre particiones."""
    steps = ktr_data.get("steps", [])
    hops = ktr_data.get("hops", [])
    matrix = build_rw_matrix(ktr_data, step_type_aliases)
    comp = _connected_components(steps, hops)

    notifications: list[str] = []
    trigger_edges: set[tuple[int, int]] = set()

    # V2 (03-plan.md, F2): lookup sin productor — no es señal de corte, se
    # detecta en la misma pasada que arma la matriz R/W. Tabla leída por
    # algún step de esta etapa pero que ningún step de la misma etapa
    # escribe -> notificación accionable (D15), no afecta la partición.
    for table, roles in matrix.items():
        writers_v2 = [n for n, rw in roles.items() if rw in ("W", "RW")]
        if writers_v2:
            continue
        for reader in (n for n, rw in roles.items() if rw in ("R", "RW")):
            notifications.append(
                f"Tabla '{table}': leída por '{reader}' pero ningún step de esta etapa la "
                "escribe (V2) — verificar que se cargue en otra etapa/archivo antes de ejecutar en Spoon."
            )

    for table, roles in matrix.items():
        writers = [n for n, rw in roles.items() if rw in ("W", "RW")]
        readers = [n for n, rw in roles.items() if rw in ("R", "RW")]
        is_c1 = any(r not in writers for r in readers) and writers
        is_c1_bis = len(writers) > 1
        if not (is_c1 or is_c1_bis):
            continue

        pair_comps = {comp.get(n) for n in set(writers) | set(readers)}
        if len(pair_comps) <= 1:
            # Mismo componente de hop — excepción self-lookup/insert-new-only:
            # segura si TODA lectura tiene camino dirigido hacia TODA escritura
            # (lectura estrictamente aguas arriba, idioma "existe? -> filtra -> inserta").
            safe = all(
                _reaches(r, w, hops)
                for r in readers for w in writers if r != w
            )
            if safe:
                continue
            notifications.append(
                f"Tabla '{table}': steps {sorted(set(writers) | set(readers))} comparten "
                "componente de hops sin relación segura de lectura-antes-que-escritura — "
                "corte automático no soportado para este caso todavía (sin evidencia en el "
                "corpus actual), revisar a mano."
            )
            continue

        for w in writers:
            for r in readers:
                if r == w:
                    continue
                cw, cr = comp.get(w), comp.get(r)
                if cw != cr:
                    trigger_edges.add((cw, cr))
        if len(writers) > 1:
            for i, w1 in enumerate(writers):
                for w2 in writers[i + 1:]:
                    c1, c2 = comp.get(w1), comp.get(w2)
                    if c1 != c2:
                        trigger_edges.add((c1, c2))

    groups_by_comp: dict[int, list[str]] = {}
    for name, c in comp.items():
        groups_by_comp.setdefault(c, []).append(name)

    graph: dict[int, set[int]] = {c: set() for c in groups_by_comp}
    for cw, cr in trigger_edges:
        graph.setdefault(cw, set()).add(cr)
        graph.setdefault(cr, set())

    order: list[int] = []
    visited: set[int] = set()
    temp: set[int] = set()
    cyclic = False

    def _visit(n: int) -> None:
        nonlocal cyclic
        if n in temp:
            cyclic = True
            return
        if n in visited:
            return
        temp.add(n)
        for m in graph.get(n, ()):
            _visit(m)
        temp.discard(n)
        visited.add(n)
        order.append(n)

    for c in list(graph):
        _visit(c)

    if cyclic:
        notifications.append(
            "Ciclo detectado entre grupos al ordenar por dependencia de tabla — caso "
            "patológico (D15): no se pudo determinar un orden seguro, revisar a mano."
        )
        final_order = list(groups_by_comp.keys())
    else:
        order.reverse()
        final_order = order

    return {
        "groups": [groups_by_comp[c] for c in final_order],
        "notifications": notifications,
    }


def split_ktr_by_cut(ktr_data: dict, step_type_aliases: dict[str, str]) -> tuple[list[dict], list[str]]:
    """F3 punto 1 (03-plan.md): parte ktr_data en 1..N sub-dicts según
    compute_cut(), en el orden de ejecución que el corte determina.

    0 o 1 grupo (D6-bis: sin señal estructural, o ktr_data vacío) -> devuelve
    [ktr_data] tal cual, mismo objeto — cero costo, cero cambio de
    comportamiento para el caso universal de hoy.

    N>1 grupos -> un sub-dict por grupo, cada uno con "steps"/"hops" filtrados
    a ese grupo (orden relativo original preservado, no el de compute_cut) y
    el resto de las claves (name/description/connections) compartidas —
    normalize_step_configs/build_ktr ya toleran una lista de connections con
    entradas no usadas por ningún step del sub-dict."""
    cut = compute_cut(ktr_data, step_type_aliases)
    groups = cut["groups"]
    if len(groups) <= 1:
        return [ktr_data], cut["notifications"]

    all_steps = ktr_data.get("steps", [])
    all_hops = ktr_data.get("hops", [])
    sub_dicts: list[dict] = []
    for group in groups:
        names = set(group)
        sub_steps = [s for s in all_steps if s.get("name", "") in names]
        sub_hops = [
            h for h in all_hops
            if h.get("from", "") in names and h.get("to", "") in names
        ]
        sub_dicts.append({**ktr_data, "steps": sub_steps, "hops": sub_hops})
    return sub_dicts, cut["notifications"]


# ─── Nota de estado (2026-07-24, wiring de servicio) ───────────────────────
# Hecho esta sesión (ver test_fragmentation_wiring.py):
# 1. split_ktr_by_cut() (este módulo) — parte ktr_data en N sub-dicts según
#    compute_cut(). _build_ktr_stage() (etl_generator.py) la usa + llama
#    build_ktr() una vez por grupo, en el punto H20 (entre
#    repair_integrity_gaps y build_ktr, ver etl_generator.py).
# 2. _build_job_plan() (etl_generator.py) generalizado de 2 JobEntry fijos a
#    N por etapa: 1 archivo -> entry_type="trans" directo; N>1 -> .kjb
#    intermedio + entry_type="job" (F2.5/H7), jerarquía de 3 niveles.
# 3. stitch_lineage_many() (lineage_builder.py) generalizado de 2 KTR fijos
#    (prefijo "K2::") a M archivos (prefijo "F{idx}::"). stitch_lineage(a, b)
#    es ahora un wrapper de stitch_lineage_many([a, b]) — firma preservada
#    (la usa el endpoint público /api/ai/lineage-from-ktr).
#
# Hueco nuevo, no listado originalmente en "Archivos a tocar" de F3 (ver
# 03-plan.md): ETLGenerateResponse (etl_schemas.py) y el ZIP del frontend
# (commit 338bff2) siguen fijos a exactamente 1 KTR por etapa + 1 KJB —
# no hay dónde poner los archivos extra de un corte real en la respuesta
# HTTP. Por eso el flujo en vivo (_build_response_from_two_ktr_data /
# _build_response_from_data en etl_generator.py) llama compute_cut() (así que
# SÍ corre en todo pipeline real, notificaciones V2/patológico incluidas) pero
# NO invoca _build_ktr_stage() para partir de verdad — si detecta groups>1,
# entrega el archivo sin partir + un Validacion(error) explícito con la tabla
# y los steps en conflicto, en vez de fallar en silencio o dropear archivos.
# La capacidad de servicio (split + N builds + jerarquía de jobs + linaje
# cosido) está completa y probada — lista para conectarse en cuanto el schema
# de respuesta deje de estar fijo a 2 archivos.
#
# Sigue pendiente:
# 4. Notificación V2 (lookup sin productor) dentro de compute_cut() — hoy es
#    una pasada aparte sobre build_rw_matrix (tabla leída que nunca aparece
#    escrita por ningún step de la etapa). Ya se emite como notificación, no
#    cambia con este wiring.
# 5. Extender ETLGenerateResponse/frontend para entregar N archivos por HTTP
#    (hueco de arriba) — recién ahí _build_ktr_stage() reemplaza a las
#    llamadas directas a build_ktr() en el flujo en vivo.
# 6. Test de integración end-to-end contra el pipeline HTTP completo (hoy los
#    tests de servicio llaman las funciones internas directamente, no pasan
#    por generate_etl_from_inference con un caso que dispare un corte real).
