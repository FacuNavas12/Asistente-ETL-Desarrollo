"""
F3 (Fase 3 del handoff) — motor de corte. Diseño validado en `03-plan.md`
(reporte F2, 2026-07-22) contra `err1.ktr`/`err2.ktr` (H21). Wireado a
`etl_generator.py` (`split_ktr_by_cut`, `_build_ktr_stage`, `_build_job_plan`
N-ario) y a `lineage_builder.stitch_lineage_many` a nivel de servicio
(2026-07-24) — ver nota de estado al pie de este módulo y en `03-plan.md`
para el hueco que queda (ETLGenerateResponse todavía fija a 1 KTR por etapa).

D45 (docs/refactor/02-decisiones.md, sesión A — puntos 3/4/5/7, 2026-07-30):
la excepción self-lookup/insert-new-only por camino dirigido se elimina
(Kettle ejecuta los steps de una transformación como hilos concurrentes, un
hop no ordena efectos de BD); mismo componente siempre notifica ahora. C1
queda explícito por par de steps distintos, no por coincidencia con C1-bis
(H42). Hops que cruzan grupos del corte (o referencian un step inexistente)
pasan de descartarse en silencio a Finding severity="error". untouched_comps
se inventaría en un Finding severity="info" cuando hay corte real.

D45 sesión B (puntos 1/2/6, 2026-07-30): resolución de tabla por SQL real
(`resolve_sql_tables` inyectado — `domain/sql_resolution.py`, ver
`services/adapters/sql_table_resolver.py`), clave de matriz `(connection,
table)` (`_connection_key`, `domain/table_layer.py`), `validate_stage_contract`
(S-13, chequeo a nivel etapa sobre el CONJUNTO de sub_dicts que salen del
corte).

D48 (2026-07-30): dentro de un componente conexo, el caso evidenciado en el
corpus (`err1.ktr`/`err2.ktr`, self-lookup "Existe? -> Filtrar Nuevos ->
Insertar Dim Pais") SÍ se puede partir — único writer, todos sus readers de
esa tabla son ancestros dirigidos suyos — separando el writer (+
descendientes) en un grupo posterior y materializando el hop que queda
colgando vía tabla de staging efímera (`_materialize_cut_hop`,
`split_ktr_by_cut`). Cualquier otro patrón dentro de un componente (más de un
writer, o un reader que no es ancestro) sigue sin partirse — "revisar a
mano", igual que antes de D48.

Algoritmo (resumen, detalle completo en 03-plan.md):
1. build_rw_matrix: {(conexión, tabla): {step: "R"|"W"|"RW"}} — reusa H19
   (rol por tipo de step) + el update=N de D16 para DimensionLookup en rol
   fact_lookup + resolución SQL real para TableInput/StreamLookup/ExecSQL
   (D45 punto 1).
2. Dos disparadores de corte: C1 (W+R por steps distintos) y C1-bis (doble
   escritor). Steps sin rol R/W no participan; un step CON rol R/W pero sin
   tabla resoluble notifica en vez de descartarse en silencio (T1/D62,
   D15: notifica, no bloquea).
3. Componentes conexos por hops habilitados (grafo no dirigido, ignorando
   tablas). Si escritor y lector de una tabla-disparadora ya caen en
   componentes distintos -> no hace falta partir más, alcanza con ordenarlos.
   Si caen en el mismo componente -> el patrón self-lookup (D48) se parte
   con materialización; cualquier otro caso siempre se notifica (D45), nunca
   se parte (partirlo rompería hops reales sin forma de reconectarlos).
4. Orden entre componentes: grafo dirigido componente-a-componente (una
   arista por cada relación tabla-disparadora escritor->lector/otro-escritor,
   más la arista sintética que un split D48 agrega), orden topológico. Ciclo
   real -> notifica (D15), no bloquea.
"""
from __future__ import annotations

from app.domain.sql_resolution import SqlTableResolver
from app.domain.step_table import resolve_step_table
from app.domain.table_layer import infer_table_layer
from app.services.ktr_builder.contracts import normalize_config, parse_cfg
from app.services.ktr_builder.validators.base import Finding

# Matriz R/W keyed by (conexión_lógica, tabla_lower) — D45 punto 2. Cierra
# C-7 (dos conexiones lógicas distintas al mismo nombre de tabla física no
# deben colapsar en la misma fila de la matriz) y la asimetría de H43
# (table_key_recovery._bare() quita el schema, el camino feliz no — con
# (connection, table) como clave, al menos el componente de conexión queda
# explícito y comparable entre archivos, aunque el schema todavía no entra
# a la clave, ver C.11/S-10 en 02-decisiones.md).
MatrixKey = tuple[str, str]

# H19 (01-hallazgos.md): rol por tipo de step. DimensionLookup es el único
# condicional — su rol depende de cfg["update"] (D16: "N" = fact_lookup,
# forzado solo-lectura por dimension_step_policy antes de llegar acá).
_WRITE_ONLY = {"TableOutput", "InsertUpdate", "Update", "Delete"}
_ALWAYS_RW = {"CombinationLookup"}
_READ_ONLY = {"DBLookup", "TableInput"}
_NOT_CLASSIFIABLE = {"ExecSQL"}

# D45 punto 1 (docs/refactor/02-decisiones.md): ExecSQL clasificado por
# operación real del SQL en vez de quedar siempre fuera de la matriz.
# CREATE queda sin rol -- DDL estructural, no efecto de datos que compita por
# una fila con otro step de la misma transformación.
_EXEC_SQL_ROLE: dict[str, str] = {
    "TRUNCATE": "W", "INSERT": "W", "UPDATE": "W", "DELETE": "W",
}


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


def _connection_key(cfg: dict, table: str) -> str:
    """Conexión lógica para la clave de matriz (D45 punto 2). Explícita si el
    step la declara (`connection`/`connection_name`); si no, inferida por
    prefijo de tabla (`domain/table_layer.py`) — MISMA heurística de nombre
    que `ktr_builder/connection.py` usa al emitir, pero sin `connection_names`/
    roles de pase (esos solo existen dentro de `build_ktr()`, que corre
    después del corte — ver nota de ejecución bajo D45 en 02-decisiones.md).
    Best-effort determinista: dos steps con la misma tabla y sin `connection`
    explícita infieren la MISMA clave acá (comparación determinista dentro
    de un archivo y entre archivos de la misma corrida), pero no hay garantía
    de que coincida 1:1 con la conexión real que build_ktr() termine
    resolviendo."""
    explicit = (cfg.get("connection") or cfg.get("connection_name") or "").strip()
    if explicit:
        return explicit
    layer = infer_table_layer(table)
    if layer == "dwh":
        return "conn_dwh"
    if layer == "staging":
        return "conn_staging"
    return "conn_origen"


def _fmt_key(key: MatrixKey) -> str:
    connection, table = key
    return f"{table} (conexión '{connection}')"


def build_rw_matrix(
    ktr_data: dict,
    step_type_aliases: dict[str, str],
    resolve_sql_tables: SqlTableResolver | None = None,
) -> tuple[dict[MatrixKey, dict[str, str]], list[Finding]]:
    """{(conexión, tabla_lower): {step_name: "R"|"W"|"RW"}}, [Finding] (SQL no
    parseable, D45 punto 1). Steps sin rol R/W propio (Sort, FilterRows...)
    no aportan y no notifican — no tienen tabla que resolver. Un step CON rol
    R/W (TableOutput, InsertUpdate, DimensionLookup...) pero sin tabla
    resoluble sí notifica (T1/D62, `domain/step_table.py`) en vez de
    descartarse en silencio.

    resolve_sql_tables (`domain/sql_resolution.py`, implementación real
    `services/adapters/sql_table_resolver.py`, D45 punto 1,
    docs/refactor/02-decisiones.md): `Table input` se define por SQL, no por
    un campo `table` — es el caso normal, no la excepción. Sin resolver
    (None, default — preserva el comportamiento previo a D45), `TableInput`/
    `StreamLookup`/`ExecSQL` quedan invisibles para la matriz, igual que
    antes. Con resolver: `TableInput` aporta el conjunto de tablas de su
    `FROM`/`JOIN` como "R"; `StreamLookup` hereda la tabla del `TableInput`
    que referencia (`cfg["step"]`); `ExecSQL` se clasifica por operación real
    (`_EXEC_SQL_ROLE`) sobre las tablas que afecta. Este módulo está en
    DOMAIN_MODULES (test_architecture_layers.py) — no puede importar
    `sqlglot` directo, por eso el resolver se inyecta en vez de importarse."""
    matrix: dict[MatrixKey, dict[str, str]] = {}
    findings: list[Finding] = []

    # TableInput se resuelve en una pasada previa: StreamLookup (más abajo)
    # necesita conocer la(s) clave(s) del TableInput que referencia antes de
    # llegar a su propio turno en el loop principal.
    table_input_keys: dict[str, frozenset[MatrixKey]] = {}
    if resolve_sql_tables is not None:
        for step in ktr_data.get("steps", []):
            canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
            if canonical != "TableInput":
                continue
            step_name = step.get("name", "")
            cfg = parse_cfg(step.get("config", {}))
            resolution = resolve_sql_tables(cfg.get("sql", ""))
            if resolution.error:
                findings.append(Finding(
                    severity="error", step_name=step_name,
                    message=(
                        f"TableInput '{step_name}': {resolution.error} — la tabla que lee queda "
                        "invisible para la matriz de lectura/escritura (corte, carreras). Revisar el SQL a mano."
                    ),
                ))
                continue
            keys = frozenset(
                (_connection_key(cfg, table), table) for table in resolution.tables
            )
            table_input_keys[step_name] = keys
            for key in keys:
                matrix.setdefault(key, {})[step_name] = "R"

    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        step_name = step.get("name", "")

        if canonical == "TableInput":
            continue  # ya resuelto arriba (o invisible sin resolver — comportamiento previo a D45)

        if canonical == "StreamLookup" and resolve_sql_tables is not None:
            cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
            source_step = cfg.get("step") or cfg.get("from") or ""
            for key in table_input_keys.get(source_step, frozenset()):
                matrix.setdefault(key, {})[step_name] = "R"
            continue

        if canonical == "ExecSQL":
            if resolve_sql_tables is None:
                continue  # comportamiento previo a D45: no clasificable
            cfg = parse_cfg(step.get("config", {}))
            resolution = resolve_sql_tables(cfg.get("sql", ""))
            if resolution.error:
                findings.append(Finding(
                    severity="error", step_name=step_name,
                    message=(
                        f"ExecSQL '{step_name}': {resolution.error} — no participa en la matriz de "
                        "lectura/escritura (corte, carreras). Revisar el SQL a mano."
                    ),
                ))
                continue
            role = _EXEC_SQL_ROLE.get(resolution.operation or "")
            if role is None:
                continue  # CREATE u operación no clasificada: sin efecto de datos que compita
            for table in resolution.tables:
                key = (_connection_key(cfg, table), table)
                matrix.setdefault(key, {})[step_name] = role
            continue

        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        rw = _step_rw(canonical, cfg)
        if rw is None:
            continue  # tipo de step sin rol R/W propio (Sort, FilterRows, ...) — no toca tabla, no hay nada que notificar
        table, message = resolve_step_table(step_name, cfg.get("table"))
        if table is None:
            # T1/D62: step con rol R/W pero sin tabla resoluble — sí amerita aviso
            findings.append(Finding(severity="error", step_name=step_name, message=message))
            continue
        table = table.lower()
        key = (_connection_key(cfg, table), table)
        matrix.setdefault(key, {})[step_name] = rw

    return matrix, findings


def _connected_components(steps: list[dict], hops: list[dict]) -> dict[str, int]:
    """Componente conexo (grafo NO dirigido de hops, ignorando tablas) por
    step_name. D45 punto 4: hops deshabilitados (`enabled=False`) no
    transportan filas — no conectan sus extremos. Antes de D45 este chequeo
    vivía solo en `_reaches` (que sí lo respetaba); al borrarse `_reaches`
    (D45: la excepción por camino dirigido que la usaba ya no existe), el
    respeto de `enabled` se mueve acá, la única fuente de componentes que
    queda."""
    names = [s.get("name", "") for s in steps]
    adjacency: dict[str, set] = {n: set() for n in names}
    for hop in hops:
        if not hop.get("enabled", True):
            continue
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


def _directed_neighbors(hops: list[dict], *, forward: bool) -> dict[str, set[str]]:
    """Adyacencia DIRIGIDA por hops habilitados — forward=True: from->to
    (descendientes); forward=False: to->from (ancestros). D48
    (docs/refactor/02-decisiones.md): a diferencia de _connected_components
    (no dirigido, decide qué está "junto"), acá la dirección real del hop
    importa — decide qué está antes/después."""
    adj: dict[str, set[str]] = {}
    for hop in hops:
        if not hop.get("enabled", True):
            continue
        a, b = hop.get("from", ""), hop.get("to", "")
        src, dst = (a, b) if forward else (b, a)
        adj.setdefault(src, set()).add(dst)
    return adj


def _reachable(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        for nxt in adjacency.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _directed_ancestors(target: str, hops: list[dict]) -> set[str]:
    return _reachable(target, _directed_neighbors(hops, forward=False))


def _directed_descendants(source: str, hops: list[dict]) -> set[str]:
    return _reachable(source, _directed_neighbors(hops, forward=True))


def compute_cut(
    ktr_data: dict,
    step_type_aliases: dict[str, str],
    resolve_sql_tables: SqlTableResolver | None = None,
) -> dict:
    """{"groups": [[step_name, ...], ...] ya en orden de ejecución,
    "notifications": [Finding]} — ver algoritmo completo en el docstring del
    módulo / reporte F2 en 03-plan.md. NO reordena steps dentro de un grupo
    (eso lo hace _auto_layout aguas abajo); solo decide partición + orden
    entre particiones.

    resolve_sql_tables: ver build_rw_matrix (D45 punto 1) — None preserva el
    comportamiento previo a D45 (TableInput/StreamLookup/ExecSQL invisibles).

    Fase 0 (D50, docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md):
    notifications pasó de list[str] a list[Finding] para que el caller
    (_build_ktr_stage, vía split_findings_by_severity) promueva por
    severidad real en vez de tratar todo como cosmético. V2 (lookup sin
    productor en esta etapa) es "warning" — advierte, no confirma un error,
    porque la tabla puede cargarse legítimamente en otra etapa/archivo. El
    caso "mismo componente sin relación segura" y el ciclo de orden son
    "error" — son exactamente la clase de carrera que este refactor
    persigue, salvo el caso evidenciado que D48 sí puede partir (ver abajo).

    D48 (docs/refactor/02-decisiones.md): dentro de un componente conexo,
    si TODOS los readers de la tabla-disparadora son ancestros dirigidos del
    (único) writer — el patrón "Existe? -> Filtrar Nuevos -> Insertar Dim
    Pais" del corpus (err1.ktr/err2.ktr) — el componente SÍ se puede partir:
    el writer (+ sus descendientes) pasa a un grupo posterior, el resto
    (incluidos los readers) queda en uno anterior, y el hop que queda
    colgando entre ambos se materializa vía tabla de staging
    (`split_ktr_by_cut`, `materialize_hops` en el dict de retorno) en vez de
    perderse. Cualquier otro caso dentro de un componente (más de un writer,
    o algún reader que NO es ancestro del writer — orden real ambiguo, no
    hay forma segura de decidir qué va antes) sigue sin partirse: "revisar a
    mano", como antes de D48."""
    steps = ktr_data.get("steps", [])
    hops = ktr_data.get("hops", [])
    matrix, resolution_findings = build_rw_matrix(ktr_data, step_type_aliases, resolve_sql_tables)
    comp = _connected_components(steps, hops)

    notifications: list[Finding] = list(resolution_findings)
    trigger_edges: set[tuple[int, int]] = set()
    # D48: comp_id (ANTES de partir) -> nombres de step que pasan al grupo
    # "posterior" (el writer + sus descendientes). Union de todas las tablas
    # que motivaron partir ESE componente — un solo punto de corte por
    # componente, aunque más de un trigger lo pida.
    component_splits: dict[int, set[str]] = {}

    # V2 (03-plan.md, F2): lookup sin productor — no es señal de corte, se
    # detecta en la misma pasada que arma la matriz R/W. Tabla leída por
    # algún step de esta etapa pero que ningún step de la misma etapa
    # escribe -> notificación accionable (D15), no afecta la partición.
    for key, roles in matrix.items():
        writers_v2 = [n for n, rw in roles.items() if rw in ("W", "RW")]
        if writers_v2:
            continue
        for reader in (n for n, rw in roles.items() if rw in ("R", "RW")):
            notifications.append(Finding(
                severity="warning",
                step_name=reader,
                message=(
                    f"Tabla '{_fmt_key(key)}': leída por '{reader}' pero ningún step de esta etapa la "
                    "escribe (V2) — verificar que se cargue en otra etapa/archivo antes de ejecutar en Spoon."
                ),
            ))

    for key, roles in matrix.items():
        writers = [n for n, rw in roles.items() if rw in ("W", "RW")]
        readers = [n for n, rw in roles.items() if rw in ("R", "RW")]
        # D45 punto 3: la carrera es entre steps DISTINTOS — un step RW que es
        # su propio único lector/escritor (loader de dimensión normal,
        # `update=Y`) no dispara solo por serlo. Antes de D45 esto dependía de
        # que C1-bis (len(writers) > 1) tapara el caso "todo lector es también
        # escritor" — condición frágil (H42), acá queda explícita.
        is_c1 = any(r != w for r in readers for w in writers)
        is_c1_bis = len(writers) > 1
        if not (is_c1 or is_c1_bis):
            continue

        pair_comps = {comp.get(n) for n in set(writers) | set(readers)}
        if len(pair_comps) <= 1:
            # D45 punto 4: la excepción por camino dirigido (self-lookup
            # "existe? -> filtra -> inserta" seguro si la lectura corre aguas
            # arriba de la escritura, vía _reaches) se elimina. En Kettle
            # TODOS los steps de una transformación arrancan como hilos
            # concurrentes — un hop transporta filas, no ordena efectos de
            # BD, así que un camino dirigido en el grafo de hops no garantiza
            # que la lectura termine antes que la escritura en runtime.
            #
            # D48: ESE mismo camino dirigido es justo lo que permite partir
            # con seguridad — no porque ordene efectos DENTRO de una
            # transformación (no lo hace), sino porque separar writer y
            # reader en DOS transformaciones distintas (job-level, secuencial
            # de verdad) sí lo hace. Solo cuando hay un único writer y TODOS
            # los readers de esta tabla son ancestros dirigidos de ese writer
            # — el reader necesita ver el estado de la tabla ANTES de que
            # este run escriba, que es exactamente lo que el patrón
            # "Existe?"/self-lookup pide.
            single_writer = len(set(writers)) == 1
            w = writers[0] if single_writer else None
            ancestors_of_w = _directed_ancestors(w, hops) if w else set()
            other_readers = set(readers) - {w}
            splittable = single_writer and other_readers and other_readers <= ancestors_of_w
            if splittable:
                after = {w} | _directed_descendants(w, hops)
                component_splits.setdefault(comp[w], set()).update(after)
                notifications.append(Finding(
                    severity="info",
                    message=(
                        f"Tabla '{_fmt_key(key)}': {sorted(other_readers)} lee(n) antes de que "
                        f"'{w}' escriba, dentro del mismo componente de hops — patrón self-lookup "
                        "reconocido (D48): el componente se parte en dos archivos, el hop que "
                        "cruza se materializa vía tabla de staging."
                    ),
                ))
                continue
            notifications.append(Finding(
                severity="error",
                message=(
                    f"Tabla '{_fmt_key(key)}': steps {sorted(set(writers) | set(readers))} comparten "
                    "componente de hops — Kettle los ejecuta como hilos concurrentes, el hop no "
                    "garantiza que la lectura corra antes que la escritura. Corte automático no "
                    "soportado dentro de un componente conexo (patrón no reconocido — D48 solo cubre "
                    "un único writer con todos sus readers como ancestros directos), revisar a mano."
                ),
            ))
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

    # D48: aplicar los splits recolectados — cada comp_id partido gana un
    # comp_id nuevo para su mitad "posterior" (writer + descendientes),
    # con una trigger_edge forzando ese orden. Tiene que pasar ANTES de
    # construir groups_by_comp (usa `comp` final) y antes de calcular
    # materialize_hops (necesita ver el corte ya aplicado).
    materialize_hops: list[tuple[str, str]] = []
    if component_splits:
        next_comp_id = max(comp.values(), default=-1) + 1
        for old_comp_id, after_names in component_splits.items():
            new_comp_id = next_comp_id
            next_comp_id += 1
            for name in after_names:
                comp[name] = new_comp_id
            trigger_edges.add((old_comp_id, new_comp_id))

        # Cualquier hop cuyos dos extremos ahora caen en comp_id distintos es,
        # por construcción, uno de los que el split de arriba acaba de cortar
        # (antes del split, un hop real SIEMPRE tenía los dos extremos en el
        # mismo componente — ver _connected_components). Se materializa en
        # vez de perderse (D15).
        for hop in hops:
            if not hop.get("enabled", True):
                continue
            frm, to = hop.get("from", ""), hop.get("to", "")
            cf, ct = comp.get(frm), comp.get(to)
            if cf is not None and ct is not None and cf != ct:
                materialize_hops.append((frm, to))
        materialize_hops.sort()

    groups_by_comp: dict[int, list[str]] = {}
    for name, c in comp.items():
        groups_by_comp.setdefault(c, []).append(name)

    # Solo los componentes que participan de una trigger_edge se ordenan/
    # separan — D6-bis: "componentes sin ninguna tabla-disparadora no se
    # tocan, se agrupan todos juntos en un único archivo por etapa". Sin este
    # filtro, cualquier ETL con 2+ ramas de hop desconectadas entre sí pero
    # sin ningún conflicto real de tabla (el caso común: 2 tablas de origen
    # independientes cargando 2 tablas de staging independientes) terminaba
    # con 1 archivo por rama — corte sin señal, justo lo que D6-bis prohíbe.
    triggered_comps = {c for pair in trigger_edges for c in pair}
    untouched_comps = [c for c in groups_by_comp if c not in triggered_comps]

    graph: dict[int, set[int]] = {c: set() for c in triggered_comps}
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
        notifications.append(Finding(
            severity="error",
            message=(
                "Ciclo detectado entre grupos al ordenar por dependencia de tabla — caso "
                "patológico (D15): no se pudo determinar un orden seguro, revisar a mano."
            ),
        ))
        final_order = list(triggered_comps)
    else:
        order.reverse()
        final_order = order

    # Los componentes sin trigger van todos juntos en un único grupo extra —
    # no hay relación de tabla que fije su posición relativa al resto, así
    # que su orden dentro de ese grupo (y respecto a los grupos con trigger)
    # no importa estructuralmente.
    groups: list[list[str]] = []
    if untouched_comps:
        groups.append([name for c in untouched_comps for name in groups_by_comp[c]])
    groups.extend(groups_by_comp[c] for c in final_order)

    # D45 punto 7: inventario de untouched_comps. Solo cuando el corte es
    # real (final_order no vacío — si no, groups tiene 1 solo elemento y no
    # hay nada que "quedó junto" respecto de otra cosa) y hay algo sin tocar
    # para inventariar. severity="info": D6-bis ya decidió que no se parte
    # sin señal estructural, esto no es un error a revisar, es transparencia
    # sobre por qué el archivo resultante mezcla ramas sin relación de tabla.
    if final_order and untouched_comps:
        untouched_steps = [name for c in untouched_comps for name in groups_by_comp[c]]
        notifications.append(Finding(
            severity="info",
            message=(
                f"Steps {sorted(untouched_steps)} quedaron juntos en un mismo archivo sin "
                "partir — ninguna de sus tablas disparó C1/C1-bis, y D6-bis prohíbe partir sin "
                "señal estructural."
            ),
        ))

    return {
        "groups": groups,
        "notifications": notifications,
        # D48: [(from, to), ...] de hops que el split de arriba dejó
        # cruzando grupos — split_ktr_by_cut los materializa vía tabla de
        # staging en vez de reportarlos como perdidos.
        "materialize_hops": materialize_hops,
    }


def split_ktr_by_cut(
    ktr_data: dict,
    step_type_aliases: dict[str, str],
    resolve_sql_tables: SqlTableResolver | None = None,
) -> tuple[list[dict], list[Finding]]:
    """F3 punto 1 (03-plan.md): parte ktr_data en 1..N sub-dicts según
    compute_cut(), en el orden de ejecución que el corte determina.

    resolve_sql_tables: ver build_rw_matrix (D45 punto 1).

    0 o 1 grupo (D6-bis: sin señal estructural, o ktr_data vacío) -> devuelve
    [ktr_data] tal cual, mismo objeto — cero costo, cero cambio de
    comportamiento para el caso universal de hoy.

    N>1 grupos -> un sub-dict por grupo, cada uno con "steps"/"hops" filtrados
    a ese grupo (orden relativo original preservado, no el de compute_cut) y
    el resto de las claves (name/description/connections) compartidas —
    normalize_step_configs/build_ktr ya toleran una lista de connections con
    entradas no usadas por ningún step del sub-dict.

    D48 (docs/refactor/02-decisiones.md): `cut["materialize_hops"]` (hops que
    el split dentro de un componente conexo dejó cruzando grupos, patrón
    self-lookup reconocido — ver compute_cut) se materializan acá vía tabla
    de staging (`_materialize_cut_hop`), en vez de reportarse como perdidos."""
    cut = compute_cut(ktr_data, step_type_aliases, resolve_sql_tables)
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
        sub_dicts.append({**ktr_data, "steps": list(sub_steps), "hops": list(sub_hops)})

    materialize_hops: set[tuple[str, str]] = set(cut.get("materialize_hops", []))
    group_of: dict[str, int] = {name: i for i, group in enumerate(groups) for name in group}
    materialize_notifications: list[Finding] = []
    for i, (frm, to) in enumerate(sorted(materialize_hops)):
        table = f"etl_corte_{i + 1}"
        materialize_notifications.append(
            _materialize_cut_hop(sub_dicts[group_of[frm]], sub_dicts[group_of[to]], frm, to, table)
        )

    # D45 punto 5: un hop habilitado transporta filas — si sus dos extremos
    # no caen en el mismo grupo (incluido el caso colgante, extremo que no es
    # ningún step conocido), se descartaba en silencio antes de D45 (el
    # filtro de sub_hops de arriba ya lo excluye de todo grupo). Perder filas
    # sin error es exactamente lo que D15 prohíbe. Con el algoritmo actual un
    # grupo es siempre la unión completa de 1+ componentes conexos, así que
    # un hop con los dos extremos conocidos nunca cruza un grupo por sí solo
    # — salvo los que D48 acaba de materializar arriba (excluidos acá). Lo
    # que llega a este loop es el caso colgante genuino (nombre de step
    # inexistente) — sigue sin forma de reconectarse.
    cross_group_notifications: list[Finding] = []
    for hop in all_hops:
        if not hop.get("enabled", True):
            continue
        frm, to = hop.get("from", ""), hop.get("to", "")
        if (frm, to) in materialize_hops:
            continue
        gf, gt = group_of.get(frm), group_of.get(to)
        if gf is None or gt is None or gf != gt:
            cross_group_notifications.append(Finding(
                severity="error",
                message=(
                    f"Hop '{frm}' -> '{to}' cruza grupos del corte (o referencia un step "
                    "inexistente) — se descarta sin reconectar, filas perdidas. Revisar a mano."
                ),
            ))

    return sub_dicts, [*cut["notifications"], *materialize_notifications, *cross_group_notifications]


def _materialize_cut_hop(
    emitter_sub: dict, receiver_sub: dict, frm: str, to: str, table: str,
) -> Finding:
    """D48: reconecta un hop que el split dentro de un componente conexo dejó
    cruzando grupos — un `TableOutput` al final de la mitad "antes" (mismo
    step de origen `frm`) + un `TableInput` al principio de la mitad
    "después" (alimenta al mismo destino `to`), contra una tabla de staging
    nueva, sin campos explícitos (Kettle escribe/lee todas las columnas del
    stream por nombre — `specify_fields`/`SELECT *`).

    Decisiones de implementación que D48 dejó abiertas (`02-decisiones.md`):
      - Nombre: `etl_corte_N`, determinista dentro de la etapa (orden de
        `sorted(materialize_hops)`). Prefijo deliberadamente FUERA de
        `domain/table_layer.py` (STAGING_TABLE_PREFIXES/DWH_TABLE_PREFIXES)
        — si empezara con `stg_`, `guard_staging_layer.py` (Fase 2-ter) la
        marcaría como violación de "staging sin reglas de negocio" (D42),
        que no aplica acá: es plomería interna del motor de corte, no la
        capa de staging del contrato del usuario.
      - Conexión: `conn_staging` explícita (no inferida por prefijo, ya que
        el nombre no matchea ningún prefijo a propósito) — reusa la conexión
        de staging real en vez de pedir una tercera conexión al usuario.
      - Ciclo de vida: `truncate=True` en el `TableOutput` — la tabla es
        efímera, vive solo para pasar filas de un archivo al siguiente
        dentro de la MISMA corrida; sin truncar, una corrida vieja podría
        dejar filas que la corrida nueva no esperaba."""
    output_step = f"Escribir {table}"
    input_step = f"Leer {table}"
    emitter_sub["steps"].append({
        "name": output_step, "type": "TableOutput",
        "config": {"table": table, "connection": "conn_staging", "truncate": True},
    })
    emitter_sub["hops"].append({"from": frm, "to": output_step, "enabled": True})
    receiver_sub["steps"].append({
        "name": input_step, "type": "TableInput",
        "config": {"connection": "conn_staging", "sql": f"SELECT * FROM {table}"},
    })
    receiver_sub["hops"].append({"from": input_step, "to": to, "enabled": True})
    return Finding(
        severity="info",
        message=(
            f"Hop '{frm}' -> '{to}' cruzaba grupos del corte (D48) — materializado vía tabla de "
            f"staging efímera '{table}' ('{output_step}' en el archivo emisor, '{input_step}' en "
            "el receptor)."
        ),
    )


def validate_stage_contract(
    sub_dicts: list[dict],
    step_type_aliases: dict[str, str],
    resolve_sql_tables: SqlTableResolver | None = None,
) -> list[Finding]:
    """D45 punto 6 (S-13, docs/refactor/03c-investigacion-vocabulario-
    dimension-kettle.md): chequeo a nivel ETAPA — el entregable de una etapa
    son N sub-.ktr (`split_ktr_by_cut`) + 1 `.kjb`, y hasta acá nada validaba
    el CONJUNTO. Llamar con la lista completa de `sub_dicts` que
    `split_ktr_by_cut` devolvió para una misma etapa, en el mismo orden
    (el que `_build_job_plan` va a usar para las entradas del `.kjb`).

    Qué cubre y qué no, de los 3 ítems de S-13:
      - "orden del job coincide con el topológico del corte": no es un
        chequeo aparte — `_build_ktr_stage`/`_build_job_plan` usan el MISMO
        list en el MISMO orden que devuelve `split_ktr_by_cut` sin
        reordenar en ningún punto intermedio (garantía de construcción,
        ver test_fragmentation_wiring.py). El único modo en que ese orden
        deja de alcanzar es el caso de abajo.
      - "ningún fragmento lee lo que otro fragmento POSTERIOR escribe": SÍ
        se chequea acá — es el gap real. V2 (dentro de `compute_cut`) solo
        mira "¿algún step de ESTE archivo escribe la tabla?"; si el escritor
        real vive en un fragmento posterior de la MISMA etapa (típicamente
        una tabla que cae en un componente `untouched` ordenado antes que su
        escritor real, o cuyo trigger no la conectó), V2 no lo distingue de
        "se escribe en otra etapa/archivo, es legítimo" y queda como
        warning cosmético en vez de la carrera real que es.
      - "ningún hop de datos descartado sin error": ya cubierto por
        `split_ktr_by_cut` (D45 punto 5, cross_group_notifications) — esta
        función no lo repite.

    resolve_sql_tables: igual que build_rw_matrix (D45 punto 1)."""
    findings: list[Finding] = []
    if len(sub_dicts) < 2:
        return findings

    per_fragment: list[dict[MatrixKey, dict[str, str]]] = []
    for sub in sub_dicts:
        matrix, resolution_findings = build_rw_matrix(sub, step_type_aliases, resolve_sql_tables)
        findings.extend(resolution_findings)
        per_fragment.append(matrix)

    # Primer fragmento (más temprano en el orden de ejecución) que escribe
    # cada clave — si el mismo (connection, table) se re-escribe en más de
    # un fragmento (caso raro, ej. loader particionado a mano), el primero
    # es el que importa para decidir si un lector más temprano ya llega tarde.
    writer_index: dict[MatrixKey, int] = {}
    for idx, matrix in enumerate(per_fragment):
        for key, roles in matrix.items():
            if any(rw in ("W", "RW") for rw in roles.values()):
                writer_index.setdefault(key, idx)

    for idx, matrix in enumerate(per_fragment):
        for key, roles in matrix.items():
            if not any(rw in ("R", "RW") for rw in roles.values()):
                continue
            writer_idx = writer_index.get(key)
            if writer_idx is None or writer_idx <= idx:
                continue
            readers = sorted(n for n, rw in roles.items() if rw in ("R", "RW"))
            findings.append(Finding(
                severity="error",
                message=(
                    f"Tabla '{_fmt_key(key)}': leída por {readers} en el fragmento {idx + 1} de "
                    f"esta etapa, pero el fragmento {writer_idx + 1} (posterior en el orden del "
                    ".kjb) es quien la escribe — la lectura correría antes de que la fila exista "
                    "(S-13). Revisar el corte a mano."
                ),
            ))
    return findings


# ─── Nota de estado (2026-07-24, wiring de servicio + D20) ─────────────────
# Hecho (ver test_fragmentation_wiring.py + test_etl_generate_response_shape.py):
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
# 4. D20 (02-decisiones.md): ETLGenerateResponse reemplazó los slots fijos
#    ktr_xml/ktr2_xml/kjb_xml por `etapas: list[EtapaOutput]` (2 en el flujo
#    de inferencia, 1 en el monolítico legacy) + `kjb_master`. Los call sites
#    en vivo (_build_response_from_two_ktr_data / _build_response_from_data,
#    etl_generator.py) ahora invocan _build_ktr_stage() de verdad — cuando
#    compute_cut() detecta groups>1, la etapa sale como N archivos + su .kjb
#    intermedio (tipo="kjb"), no como un .ktr sin partir con una advertencia.
#
# Sigue pendiente (ver "NO hecho" en 03-plan.md, fila F3):
# 5. Frontend: consumir el nuevo shape de ETLGenerateResponse y armar el ZIP
#    con carpetas por etapa partida (D20-punto4/punto5) — sesión aparte,
#    deliberadamente fuera de esta.
