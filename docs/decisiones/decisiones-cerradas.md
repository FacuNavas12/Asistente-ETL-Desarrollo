# Decisiones cerradas — archivo frío

**Complemento de [`decisiones.md`](decisiones.md), citado igual desde comentarios de código.** Cuerpo append-only, no se edita — entradas movidas acá cuando la decisión y su fase quedaron cerradas. El cuerpo de cada entrada es exactamente el que tenía en el archivo caliente al moverse.

**Sesión de archivado:** 2026-08-04.

En `decisiones.md`, la fila de índice de cada una de estas queda como stub de una línea apuntando acá.

---

<a id="d17"></a>
### D17 — F2 (diseño del corte) aprobado por el usuario `[F2]`

**Aprobado 2026-07-23.** El diseño de F2 (Reporte F2 en `03b-reportes.md`, 2026-07-22: matriz R/W, disparadores C1/C1-bis, componentes conexos, excepción self-lookup, orden topológico, validado contra `err1.ktr`/`err2.ktr`) queda aprobado tal como está documentado. Desbloquea uno de los tres prerrequisitos de F3 (los otros dos: F2.5 en código, D16 camino 1 en código — ninguno de los dos escrito todavía).

---

<a id="d19"></a>
### D19 — F3 punto 1-3 (wiring del corte) cerrado a nivel de servicio; el flujo HTTP en vivo se queda en modo notificación hasta extender `ETLGenerateResponse` `[F3]`

**Contexto (2026-07-24):** al arrancar F3 punto 1 (wiring de `compute_cut()` a `etl_generator.py`, ver `03-plan.md`), apareció un hueco no listado en la sección "Archivos a tocar" del reporte F2: `ETLGenerateResponse` (`backend/app/schemas/etl_schemas.py:119-136`) y el ZIP del frontend (commit `338bff2`) están cableados a exactamente 1 KTR por etapa + 1 `.kjb` (2 archivos + 1 job). Si `compute_cut()` devuelve `groups>1` en una etapa real — exactamente el patrón de `err1.ktr`/`err2.ktr` (H21), el caso que motivó todo el refactor — no hay dónde poner los archivos extra en la respuesta HTTP.

**Decisión (confirmada por el usuario, alcance de sesión):** separar "capacidad de servicio" de "entrega por HTTP". Esta sesión implementó y probó a nivel de servicio (`etl_generator.py`/`lineage_builder.py`) la partición real: `split_ktr_by_cut()`, `_build_ktr_stage()` (llama `build_ktr()` una vez por grupo), `_build_job_plan()` generalizado a N por etapa (jerarquía de 3 niveles, F2.5/H7), `stitch_lineage_many()` generalizado a M archivos. Todo esto es código-listo y probado (`test_fragmentation_wiring.py`, 13 tests) pero el flujo HTTP en vivo (`_build_response_from_two_ktr_data`/`_build_response_from_data`) **no** invoca `_build_ktr_stage()` para partir de verdad — solo llama `compute_cut()` para sus notificaciones. Si detecta `groups>1`, entrega el `.ktr` sin partir + un `Validacion(tipo="error")` explícito señalando la tabla y los steps en conflicto, en vez de fallar en silencio o dropear archivos.

**Por qué no se resolvió el hueco de `ETLGenerateResponse`/frontend en la misma sesión:** es un cambio de contrato público (schema de respuesta + consumidor del ZIP en el frontend), de otro orden de magnitud que "llamar `build_ktr()` una vez por grupo" — amerita su propio diseño (¿lista de KTRs? ¿mantener los 2 slots históricos + un array de "extras"?) y su propia sesión, no una decisión de paso mientras se wireaba el corte.

**Efecto inmediato, sin esperar la extensión del schema:** todo pipeline de generación real ahora corre `compute_cut()` (antes no corría en absoluto) — un ETL que hoy dispara C1/C1-bis (carrera/doble-escritor, el bug de origen del refactor) sale con un `Validacion(tipo="error")` explícito en vez de silencioso. Es una mejora de diagnóstico entregada ya, independiente de cuándo se resuelva el hueco.

**Estado: F3 sigue "EN CURSO"**, no cierra hasta que el hueco de arriba se resuelva (ver "Estado F3" en `03b-reportes.md`) y corra un test de integración end-to-end contra el pipeline HTTP completo con un caso que dispare un corte real.

---

<a id="d20"></a>
### D20 — Forma de la respuesta con N archivos (diseño, cierra el hueco de D19) `[F3]`

**Contexto (2026-07-24):** D19 dejó abierto cómo extender `ETLGenerateResponse` (hoy fija a `ktr_xml`/`ktr2_xml`/`kjb_xml`) para entregar N archivos por etapa cuando `compute_cut()` devuelve `groups>1`. Esta sesión cierra el diseño; implementación (backend) y consumo (frontend, ZIP) quedan para sesiones separadas — ver punto 5.

**Respuestas del usuario que fijan el diseño:**

1. **No hay más casos conocidos de N>1, y no hacen falta.** El criterio ya es estructural, no un catálogo de casos: "si un step escribe una tabla y otro step la lee, no pueden vivir en la misma transformación." Esto **ya es exactamente C1/C1-bis** (F2, `03-plan.md`), no una regla nueva. Confirma que D7 (reglas derivadas de casos reales) y D6-bis (señal estructural, no legibilidad) alcanzan por sí solas para cualquier N futuro — el algoritmo generaliza porque la señal es la misma sin importar cuántas veces dispare, no hace falta enumerar escenarios.

2. **Sin compatibilidad hacia atrás que preservar (refuerza D4).** Único consumidor de `ktr_xml`/`ktr2_xml`/`kjb_xml` es el frontend de este mismo repo. Se puede romper el schema de respuesta sin período de convivencia — el frontend se arregla después, en su propia sesión (punto 5).

3. **Forma de la respuesta — jerarquía de 2 a 4 niveles, no lista plana.** El usuario describe 4 combinaciones, una por cada etapa (Origen→Staging, Staging→DWH) siendo simple o partida:
   - (a) ambas partidas: 1 KJB maestro → 2 sub-KJB (uno por etapa) → cada sub-KJB orquesta 1+ KTR.
   - (b) solo Origen→Staging partida: 1 KJB maestro → 1 sub-KJB (orquesta 1+ KTR) + 1 KTR directo (Staging→DWH).
   - (c) solo Staging→DWH partida: simétrico a (b).
   - (d) ninguna partida (caso vigente hoy): 1 KJB maestro → 2 KTR directos. La response no cambia de forma en este caso.

   Mapea 1:1 con lo que el backend ya construye a nivel de servicio (`_build_job_plan` N-ario, D19): cada etapa es o bien un KTR único (`entry_type="trans"` directo) o un KJB intermedio + N KTR (`entry_type="job"`). **La respuesta debe reflejar esa estructura, no aplanarla.** Diseño concreto para `ETLGenerateResponse`: reemplazar los slots fijos `ktr_xml`/`ktr2_xml` por una lista de 2 `EtapaOutput` (una por fase lógica, orden fijo Origen→Staging / Staging→DWH), cada una con forma:
   - `{tipo: "ktr", archivo: {xml, filename}}` — caso simple.
   - `{tipo: "kjb", kjb: {xml, filename}, archivos: [{xml, filename}, ...]}` — caso partido.

   Más `kjb_master: {xml, filename}` al tope, sin cambios respecto a hoy. Esto es diseño, **no implementado todavía** — próxima sesión de backend.

4. **UX del multi-archivo — confirma agrupación por carpeta, convención de nombres ya vigente.** El nombre de archivo ya codifica tipo/tabla/etapa (`ktr_builder`, existente). Cuando una etapa es `tipo:"kjb"`, sus KTR van agrupados en una carpeta nombrada por esa etapa/sub-job dentro del ZIP; el sub-KJB queda expuesto junto al maestro, no escondido en la carpeta. Caso (d) — el vigente hoy — el ZIP se mantiene plano, sin carpetas, sin cambio de UX percibido. Trabajo de ZIP/frontend (`etlCardActions.js`, JSZip) — **no entra en esta sesión** (punto 5).

5. **Alcance de sesión — entregas separadas.** Esta sesión cierra el diseño de la respuesta (arriba). Implementación en dos tandas futuras, no en la misma sesión: primero backend (`ETLGenerateResponse` + conectar `_build_ktr_stage()` de verdad en `_build_response_from_two_ktr_data`/`_build_response_from_data` en vez de solo notificar), después frontend (consumo del nuevo shape + ZIP con carpetas).

**Consecuencia sobre D19 y `03-plan.md`:** el hueco que D19 dejaba abierto (qué forma tiene la respuesta) queda **diseñado, no implementado**. F3 sigue "EN CURSO" — no cierra hasta que la implementación backend del punto 5 esté en código y probada end-to-end (ver "Estado F3" en `03b-reportes.md`; esos puntos no cambian de contenido, solo se resuelve la pregunta de diseño que bloqueaba empezarlos).

*Por qué D20 y no una edición directa de D19:* D19 documentó el hueco cuando apareció, a mitad de sesión, sin la información para cerrarlo. D20 es la sesión siguiente cerrando esa pregunta con datos del usuario — mismo patrón que D16→"resuelto 2026-07-23", se separa para que quede trazable qué se sabía en cada momento.

**Backend implementado 2026-07-24 (sesión 3).** `ETLGenerateResponse` (`etl_schemas.py`) reemplazó `ktr_xml`/`ktr_filename`/`ktr2_xml`/`ktr2_filename`/`kjb_xml`/`kjb_filename` por `etapas: list[EtapaOutput]` (`ArchivoKtr{xml,filename}`, `EtapaOutput{tipo:"ktr"|"kjb", archivo?, kjb?, archivos[]}`) + `kjb_master: ArchivoKtr|None`, exactamente como quedó diseñado arriba. `_build_response_from_two_ktr_data`/`_build_response_from_data` (`etl_generator.py`) dejaron de llamar `build_ktr()` directo y ahora pasan por `_build_ktr_stage()` → cuando `compute_cut()` detecta `groups>1` en una etapa, esa etapa sale como `tipo="kjb"` con sus N archivos reales, no como un `.ktr` sin partir con una advertencia (el hueco que D19 dejaba). Sin período de convivencia (D4/D20-punto2): el shape viejo desapareció del todo — **el frontend actual no puede leer una respuesta nueva hasta su propia sesión** (D20-punto5, no tocado acá).

Dos bugs reales encontrados y corregidos al conectar el corte de verdad (invisibles mientras `compute_cut()` solo generaba notificaciones, D19):
1. **`build_ktr()` prioriza `ktr_data["name"]` por sobre el nombre pasado por parámetro** (`build.py:188`). `split_ktr_by_cut()` copia `{**ktr_data, "steps":..., "hops":...}` preservando `"name"` sin cambios en cada sub-dict — sin fix, los N archivos de un corte real comparten el mismo `<name>` interno y el mismo filename (el modelo siempre manda `ktr.name`, `ETL_OUTPUT_SCHEMA` lo exige). Fix en `_build_ktr_stage()` (`etl_generator.py`): pisa `sub["name"]` con el nombre por-grupo antes de llamar a `build_ktr()`, solo cuando hay más de 1 grupo.
2. **`compute_cut()` separaba en archivos distintos cualquier par de componentes de hop desconectados, incluso sin ninguna señal estructural entre ellos** — contradecía la doctrina que el propio docstring del módulo ya declaraba (D6-bis: "componentes sin tabla-disparadora se agrupan todos juntos"), pero el código no lo implementaba: cada componente conexo se devolvía como su propio grupo sin condición. Invisible mientras el corte no se aplicaba de verdad. Caso real que lo dispara: 2 tablas de origen independientes cargando 2 tablas de staging independientes (sin ningún hop entre las dos ramas) — el caso más común de un ETL con más de una tabla de origen. Fix en `compute_cut()` (`fragmentation.py`): los componentes sin ninguna `trigger_edge` se fusionan en un único grupo adicional; solo los componentes conectados por una relación de tabla real (C1/C1-bis) se ordenan y separan.

Tests: `test_etl_generate_response_shape.py` (nuevo, 5 casos — split real en `_build_response_from_two_ktr_data`/`_build_response_from_data`, round-trip JSON del contrato, rechazo de `tipo` inválido, end-to-end HTTP contra `/api/v1/etl/generate-from-inference` con un caso que dispara corte real) + 2 casos nuevos en `test_fragmentation.py`/`test_fragmentation_wiring.py` cubriendo el bug de componentes desconectados sin señal. Suite completa corrida en frío: mismos 45 fallos preexistentes de antes de esta sesión (2 bugs no relacionados en `test_ktr_xml_validator.py`/`test_structured_outputs.py`, 6 en `test_ktr_build_job_api.py` por un bug preexistente y no relacionado de `ConnectionsMapRequest`/`InlineConnection` — el test manda un `connection_id` string donde el schema espera un objeto `InlineConnection`, sin tocar en esta sesión —, y 37 en `test_api.py` por apuntar a un servidor real en `localhost:8000` que no corre en CI), cero fallos nuevos.

**F3 sigue "EN CURSO"** — falta D20-punto5 (frontend: consumir el nuevo shape + ZIP con carpetas), sesión aparte.

---

<a id="d24"></a>
### D24 — Track A retomada; A0 (inventario) ejecutada `[Track A]`

**Contexto (2026-07-25):** `03-plan.md` tenía a Track A pospuesta desde 2026-07-22, con la condición "se retoma cuando Track F esté suficientemente asentado" — sin criterio numérico, juicio a tomar en el momento.

**Decisión:** Track F llegó a ese punto — F1, C.2, F1.5, F2, F2.5 y F5 cerrados; F3 con el algoritmo de corte y el wiring de servicio cerrados y probados end-to-end (D19/D20), solo pendiente el consumo de frontend (D20-punto5, sesión aparte); F4 con triage completo de los 8 ítems de intake y 3 gaps reales cerrados (D22). Lo que queda abierto de Track F (frontend F3, emisión de miembro inferido R5-b/R11, implementación del validador de contrato de D23, y los 9 residuales de `04-deuda-abierta.md`) es trabajo de código aislado y ortogonal a un inventario de arquitectura — sin conflicto de tocar los mismos archivos en la misma sesión, y `04-deuda-abierta.md` ya deja explícito que ninguno de esos residuales bloquea seguir con las fases.

**Ejecutado:** A0 (Fase 0 — inventario), prompt `fase-0-inventario.md` (`Contexto Cambios/Arquitectura/`). Salida en `docs/auditoria/00-inventario.md` — árbol de directorios de `backend/app/`, tabla de endpoints con cadena de llamadas, recorrido completo del flujo de un step (incluida la lista exhaustiva de las 35 call-sites que leen/parsean/mutan `config`, sección 3.3), fuentes de datos externas, estructuras de datos que representan un step o su config (6 representaciones distintas coexistiendo, hallazgo central), e inventario de tests con sus dependencias externas. Sin modificación de código, según manda la fase.

*Consecuencia sobre el plan:* A0.5 (censo de fallos silenciosos) queda desbloqueada — depende solo de A0 (`03-plan.md`).

*Por qué D24 y no solo una nota en `03-plan.md`:* mismo criterio que D16/D19/D20/D22/D23 — la condición de reanudación era un juicio pendiente sin fecha ni dato; esta sesión lo cierra con la evidencia concreta de qué estado tenía Track F al momento de decidirlo.

---

<a id="d25"></a>
### D25 — A0.5 (censo de fallos silenciosos) ejecutada; hallazgo derivado (H29) toca Track F, no solo Track A `[Track A]`

**Ejecutado (2026-07-25):** A0.5 (Fase 0.5 — censo de fallos silenciosos), sin prompt propio en `Contexto Cambios/Arquitectura/` (no existe ese archivo — confirmado por búsqueda en el repo y en `Escritorio`; alcance definido en esta sesión contra la doctrina ya vigente: D5, D15, D9/D13, R11 de `arquitectura-objetivo.md:70`). Salida en `docs/auditoria/00b-fallos-silenciosos.md` — grep sistemático de `except`/`continue` sobre `backend/app/` (114 + ~60 ocurrencias), clasificado en silencio total / logueado-sin-canal-de-usuario / notificado-correctamente, cruzado contra `01-hallazgos.md` para no reabrir H6/H12/H26. Sin modificación de código, según manda la fase.

**Resultado más relevante — no es un hallazgo de Track A, es uno de Track F, en la pieza más nueva del propio refactor.** `services/ktr_builder/fragmentation.py` (escrito 2026-07-24 para resolver races/dobles-escritores, F3) tiene en su propia función central (`build_rw_matrix()`) el mismo defecto de fondo que motivó H6: un step puede volverse invisible para la matriz R/W sin dejar rastro — por una vía distinta a la que H6 cerró (acá el `config` sí parsea; el campo `table` específicamente viene vacío). Contradice el propio docstring del módulo, que promete notificación (D15) para ese caso y no la implementa. Mismo gap duplicado, de forma independiente, en `dimension_step_policy.py` y `fields_validate.py` — los tres módulos reaccionan cada uno por su cuenta ante "tabla no resuelta", sin avisar. Catalogado como **H29** en `01-hallazgos.md` — detalle completo ahí, no repetido acá.

**Por qué se registra acá como decisión y no solo como hallazgo:** a diferencia de H24-H28 (triage de tests, hallazgos aislados), H29 nace directamente de una fase de Track A (A0.5) pero su remedio cae en Track F (mismo mecanismo de `notifications` que ya usa `compute_cut()`, mismo archivo que F3 todavía tiene abierto por el pendiente de frontend, D20-punto5). Se dejaría fuera de foco si solo viviera como una entrada más de hallazgos — esta decisión fija que **no bloquea F3** (D15 ya cubre "genera y notifica" como comportamiento por defecto; lo que falta es que ese "notifica" se cumpla en este caso puntual) y que no tiene dueño de track asignado todavía — a decidir junto con el resto de lo pendiente de F3.

*Por qué D25 y no solo una entrada de hallazgo:* mismo criterio que D24 — deja explícito que A0.5 se ejecutó, y evita que el cruce Track A → Track F de H29 quede implícito solo en el hallazgo.

---

<a id="d28"></a>
### D28 — D20-punto5 cerrado: frontend consume `etapas`/`kjb_master`; linaje recalculado se borra; datos viejos se rechazan explícitos; `EtapaOutput` gana `nombre`; Superset fuera de alcance `[F3]`

**Contexto (2026-07-27):** D20 cerró el diseño y el backend del contrato N-ario (`etapas`/`kjb_master`) en 2026-07-24, dejando explícitamente D20-punto5 (frontend) para una sesión aparte. Al retomarla, 4 preguntas no estaban decididas en ningún D anterior — se resuelven acá.

**1. Linaje — se borra el recálculo del front, no se generaliza el endpoint.** El backend ya manda `result.lineage` calculado N-ario (`stitch_lineage_many`, `etl_generator.py:658`/`:552`) en toda respuesta de generación. El único consumidor del recálculo del lado front, `frontend/src/api/lineage.js` → `POST /api/ai/lineage-from-ktr`, seguía cableado a exactamente 2 XML (`_KtrXmlBody`, `routers/ai.py:403-420`) y no tenía variante N-aria — `stitch_lineage_many_from_xml` nunca existió. Generalizar ese endpoint hubiera sido trabajo de contrato HTTP extra para un camino que el front no necesita (el backend ya entrega el linaje resuelto). Se borra `api/lineage.js` y el `useEffect` de recálculo en `EtlDetail.jsx`. El endpoint `/api/ai/lineage-from-ktr` **queda en el backend sin consumidores en este repo** — no se borra (fuera de alcance de esta sesión, podría tener otro consumidor futuro), pero se anota en `04-verificacion.md`.

**2. Datos viejos (shape sin `etapas`) — rechazo explícito, sin shim de traducción.** Antes de esta sesión, un `result` en el shape viejo (`ktr_xml`/`ktr2_xml`/`kjb_xml`) producía fallos silenciosos: botón de descarga ausente sin explicación, items de menú deshabilitados sin tooltip, ZIP que nunca se generaba. Coherente con D4/D20-punto2 (sin período de convivencia) y con la doctrina de A0.5/D25 (fallos silenciosos son la clase de bug que este refactor existe para eliminar), se decide **no** escribir un traductor viejo→nuevo — sería reintroducir la convivencia que D20-punto2 descartó — sino detectar el shape viejo explícitamente y mostrar un mensaje accionable ("generado con un formato anterior, regenerar"). Aplica tanto a ETLs ya persistidos en la DB como a archivos `etl_full` exportados e importados de vuelta.

**3. `EtapaOutput` gana el campo `nombre: str`.** D20-punto4 especificó que los KTR de una etapa partida van "en una carpeta nombrada por esa etapa/sub-job", pero el schema (`etl_schemas.py:77-89`) nunca expuso ese nombre — el backend lo conoce internamente (las etiquetas `"origen_stg"`/`"stg_dwh"`/`"proceso"` que ya usa `_build_job_plan`, `etl_generator.py:646`) pero lo descartaba al construir la respuesta. Se agrega el campo en vez de que el frontend infiera el nombre de carpeta por índice (acoplaría UI a un orden implícito) o del filename del `.kjb` (acoplaría a una convención de nomenclatura ajena).

**4. Superset queda fuera de alcance del proyecto — ya no se lo considera al tocar el flujo de generación de ETL.** No se modifica `superset_client/`, `superset_export/` ni `utils/supersetExport.js`. Se corrigen únicamente los gates rotos que dependían del shape viejo (`EtlDetail.jsx` tenía su bloque de UI de Superset ya comentado desde antes de esta sesión — se terminó de retirar el código muerto asociado, `canExportSuperset`/`handleExportSuperset`/`supersetBusy`/el import; `EtlCardMenu.jsx` tenía el item **activo** gateado por `ktr_xml` — se corrigió el gate a `supersetBusy`, sin quitar la función, porque el pedido fue sacar la dependencia rota, no retirar la feature).

**Implementación (esta sesión):**
- Backend: `nombre` en `EtapaOutput` (`etl_schemas.py`), poblado en `_etapa_output()`/`etl_generator.py`. Único cambio de backend de esta sesión.
- Frontend: módulo nuevo `frontend/src/utils/etlArtifacts.js` (`readEtlArtifacts`/`buildZipEntries`) — único punto de lectura de `result.etapas`/`kjb_master` o del shape viejo; normaliza a 3 estados (`ok`/`legacy`/`none`) con mensaje accionable en los dos últimos. Migrados sobre este módulo: `etlCardActions.js`, `EtlDetail.jsx`, `EtlCardMenu.jsx`, `etlImport.js` (rechazo en el import). Nueva sección "Archivos generados" en `ResultView.jsx` para el caso de etapa partida.
- Tests (D13): infraestructura de test de frontend inexistente hasta esta sesión — se agregó vitest (`frontend/package.json`, script `test`), sin jsdom/testing-library (los dos tests exigidos apuntan al módulo puro). `etlArtifacts.test.js`: 12 casos, con fixtures espejo de `backend/tests/test_etl_generate_response_shape.py` para que el test del front falle si el backend cambia el shape.

**Verificación:** `pytest backend/tests/test_etl_generate_response_shape.py` (5/5) + suite completa sin regresión (mismos 8 fallos preexistentes de D20/D26, cero nuevos). `npm run test` (12/12), `npm run lint` (sin errores nuevos en archivos tocados), `npm run build` limpio.

**Estado:** ejecutado. **F3 cierra** con esta sesión — ver `ESTADO.md`.

---

<a id="d59"></a>
### D59 — O1, lote E-04…E-08: 5 steps de emisión corregidos contra `readData()` real de Kettle `[O1]`

Estado: decidido, ejecutado, mismo turno.

Alcance. Cierra el "lote barato" de `10-estabilizar-emision.md` (E-04
StringOperations, E-05 Unique, E-06 ExcelInput, E-07 JsonInput, E-08
TextFileOutput) — los ítems 3, 5, 6, 7 y 8 de
`investigacion-tags-validos-por-step.md` § A. Quedan fuera, a propósito:
E-09 (`CombinationLookup`, falta el bloque `<fields><return>`) y E-10
(`DataValidator`, mapeo `name`/`fieldname` invertido) — estructurales,
más caros que 1-3 líneas, sesión aparte de O1 (E-11, `SplitFieldToRows`,
tampoco entra: es un problema de alias→`<type>` en `step_types.py`, no de
un builder de `steps/*.py`).

Método. Cada fix se verificó leyendo `readData()`/`getXML()` real de la
clase `*Meta.java` en `github.com/pentaho/pentaho-kettle` (rama
`master`), citando clase y método — la autoridad que exige
`docs/README.md` § "Autoridad sobre comportamiento de Pentaho". Un
commit por step, cada uno con test propio contra la salida real de
`build_ktr()` (patrón de `test_build_ktr_emission.py`, no fixtures
consumidas como input).

1. **StringOperations** (`steps/transform.py:_step_StringOperations`,
   commit `d0a79b9`) — `StringOperationsMeta.readData()` lee
   `trim_type`/`lower_upper` como los literales `none/left/right/both` y
   `none/lower/upper`; el emisor escribía índices numéricos (`"0".."3"`),
   que nunca matchean — el step no recortaba ni cambiaba
   mayúsculas/minúsculas con ninguna configuración. Corregido a los
   literales; `"title"` (no existe como código real de `lower_upper`) se
   resuelve vía el flag `init_cap`, independiente en Kettle.
2. **Unique** (`steps/transform.py:_step_Unique`, commit `3194463`) —
   `UniqueRowsMeta.readData()` lee `case_insensitive` (ausente = `true`,
   siempre case-insensitive); el emisor escribía `case_sensitive`,
   inexistente, con la polaridad invertida. Corregido a `case_insensitive`
   con la polaridad real.
3. **ExcelInput** (`steps/input.py:_step_ExcelInput`, commit `58d4e89`) —
   `ExcelInputMeta.readData()` parsea `spreadsheet_type` vía
   `SpreadSheetType.valueOf()` dentro de un try/catch que cae a `JXL`
   (motor legado, no lee `.xlsx`) ante tag ausente o no reconocido; el
   emisor nunca lo escribía. Corregido: se emite por extensión de archivo
   (`.xls`→`JXL`, cualquier otro caso→`POI`, que lee Excel 2007+). Valores
   reales del enum confirmados en `SpreadSheetType.java`: `JXL`, `POI`,
   `SAX_POI`, `ODS`.
4. **JsonInput** (`steps/input.py:_step_JsonInput`, commit `1462d85`) —
   `JsonInputMeta.getincludeNulls()` cae, sin el tag `includeNulls`, a
   `kettle.properties` del entorno de ejecución
   (`KETTLE_JSON_INPUT_INCLUDE_NULLS`) — no-determinismo entre máquinas
   para el mismo `.ktr`. Corregido: se emite siempre explícito (default
   `"N"`, igual al fallback real de la property).
5. **TextFileOutput** (`steps/output.py:_step_TextFileOutput`, commit
   `37e792d`) — `TextFileOutputMeta.readData()` lee `create_parent_folder`
   como hijo directo de `<step>`, no anidado en `<file>`; el emisor lo
   anidaba, inocuo hasta hoy solo porque el único valor emitido (`"Y"`)
   coincide con el default ante tag ausente. Corregido: se emite al nivel
   correcto.

Evidencia. 5 commits (`d0a79b9`, `3194463`, `58d4e89`, `1462d85`,
`37e792d`), 5 tests nuevos en `test_build_ktr_emission.py`
(`test_string_operations_emits_literal_kettle_codes_not_numeric_indices`,
`test_unique_emits_case_insensitive_tag_with_correct_polarity`,
`test_excel_input_emits_spreadsheet_type_by_extension`,
`test_json_input_emits_include_nulls_explicit`,
`test_text_file_output_emits_create_parent_folder_at_step_level`), los 12
tests del archivo en verde. Suite completa corrida antes del lote: 693
passed / 55 failed (failures preexistentes, de red/API-key y del rojo ya
conocido E-03 — ninguno en los 3 archivos tocados por este lote).

---

<a id="d61"></a>
### D61 — O2-a: `common.py` partido en dominio (`common.py`) e infraestructura (`xml_helpers.py`) `[O2]`

Estado: decidido, ejecutado, mismo turno.

`common.py` era una fila **partido** del mapa capa-objetivo (`docs/arquitectura-objetivo.md`): `_yn`/`KtrBuilderError` son puros (normalización de un valor de config, una excepción de dominio) mientras que `_sub` arma un `xml.etree.ElementTree.Element` — infraestructura de serialización XML. Mismo criterio ya aplicado a `registry.py` → `step_types.py`/`step_emitters.py`.

Ejecutado: `_sub` se mudó a `xml_helpers.py` (nuevo, `services/ktr_builder/`). `common.py` queda con `_yn`/`KtrBuilderError`, docstring actualizado explicando el split. Todo import de `_sub` en `build.py`, `connection.py`, `steps/control.py`, `steps/input.py`, `steps/output.py`, `steps/transform.py` apunta ahora a `xml_helpers.py`; donde un módulo también usaba `_yn`, el import se separó en dos líneas (`common` para `_yn`, `xml_helpers` para `_sub`).

Nota de capa física: el mapa marca `common.py` como `domain/` "ejecutado", pero el archivo sigue viviendo en `services/ktr_builder/common.py`, no en `backend/app/domain/`. Es la misma distinción que ya usa `arquitectura-objetivo.md` para `step_types.py`: el mapa fotografía la capa lógica a la que pertenece el contenido, no compromete una fecha de reubicación física — mudar el archivo es la migración grande (`ports/`/`infrastructure/` físicos), pospuesta a propósito (ver `20-arquitectura.md` § "Lo que O2 NO hace antes de entregar").

`docs/services/ktr_builder/README.md` actualizado: fila `common.py` marcada "Ejecutado (O2-a)", fila nueva `xml_helpers.py` agregada. `test_architecture_layers.py`: comentario de `DOMAIN_MODULES` actualizado para reflejar el split ya ejecutado (ya no dice "se incluye para permitir que `contracts.py` importe la mitad pura" — ahora todo el módulo es dominio puro sin excepción parcial).

**Verificación:** `test_architecture_layers.py` verde. `FROZEN_*` sin cambios (esta sesión no corrige ninguna violación existente, solo mueve código ya conforme).

---

<a id="d62"></a>
### D62 — O2-b (T1): `resolve_step_table()` en `domain/`, tres call sites dejan de tragar la tabla vacía en silencio `[O2]`

Estado: decidido, ejecutado, mismo turno.

**Problema (T1, `docs/refactor/05-transversales.md`):** `fragmentation.build_rw_matrix`, `dimension_step_policy.enforce_dimension_step_policy` y `fields_validate.validate_dimension_lookup_races` reimplementaban, cada uno por separado, "extraer candidato de tabla, normalizar, y si viene vacío, `continue` sin dejar rastro". D40 (`table_key_recovery.py`) adelantó la resolución de la causa (recupera `table` por contenido antes de que estos 3 módulos corran) pero no tocó la reacción — los 3 `continue` mudos seguían intactos, tal como registra el `Estado` de T1.

**Decisión:** `resolve_step_table(step_name, table_raw) -> (tabla | None, mensaje | None)` nueva en `domain/step_table.py`. Reemplaza la parte realmente duplicada (`.strip()`, chequeo de vacío, notificación) — no decide qué candidato mirar (`cfg["table"]` vs. `cfg["target_table"]`/`cfg["table_name"]`, prioridad entre ellos) ni si el tipo de step "debería" tener tabla: eso sigue siendo contrato de cada caller. Sin ese filtro previo, notificar por cada step sin `table` sería ruido (la mayoría de los steps de una transformación — `Sort`, `FilterRows`, `JavaScript`... — legítimamente no tocan ninguna tabla), no señal.

**Por qué NO devuelve `Finding` (`services/ktr_builder/validators/base.py`), pese a que R12 pide una entidad tipada:** se intentó primero, y cierra un ciclo de imports real y verificado — `domain/step_table.py` → `validators.base` fuerza la ejecución de `validators/__init__.py` (para llegar al submódulo `base`), que importa `guard_staging_layer`, que importa `fragmentation`, que importa `domain/step_table.py` de vuelta (`ImportError: cannot import name 'resolve_step_table' from partially initialized module`, reproducido antes de revertir). `resolve_step_table()` devuelve un mensaje de texto plano; cada caller lo envuelve en su propia forma de notificación (`Finding` en `fragmentation.py`, dict `{"tipo","campo","mensaje"}` en `dimension_step_policy.py`, string plano acumulado en `errors` en `fields_validate.py` — mismo contrato que ya tenía esa función). `domain/step_table.py` queda sin ningún import de proyecto — cumple la regla direccional Y el proxy conservador ("domain solo importa stdlib") a la vez, sin necesidad de una excepción nombrada.

**Los tres call sites, reordenados para notificar solo donde corresponde** (antes: extraían la tabla ANTES de saber si el step era relevante, así que el `continue` mudo cubría tanto "step sin tabla porque no le corresponde" como "step que sí debería tener tabla y no la tiene" — indistinguibles):

1. **`fragmentation.build_rw_matrix`** — `_step_rw(canonical, cfg)` (no depende de `table`, solo de `canonical`+`cfg["update"]`) se evalúa primero; si es `None` (step sin rol R/W, ej. `Sort`), `continue` sin tabla ni aviso, igual que antes. Si tiene rol R/W (`TableOutput`, `InsertUpdate`, `DimensionLookup`...) y la tabla no resuelve, se agrega un `Finding(severity="error")` a la lista que la función ya devuelve (`tuple[dict, list[Finding]]` — sin cambio de firma).
2. **`dimension_step_policy.enforce_dimension_step_policy`** — la función sigue necesitando `table` para CUALQUIER step (no solo `DIMENSION_STEP_TYPES`: el desenlace "tipo de step fuera de `{DimensionLookup, CombinationLookup}` sobre una tabla de `dim_contracts`" depende de resolverla primero). Se preserva ese comportamiento; lo que cambia es que un `DimensionLookup`/`CombinationLookup` (`DIMENSION_STEP_TYPES`) SIN tabla resoluble — antes invisible — ahora agrega `{"tipo": "error", "campo": "", "mensaje": ...}` a `results` antes del `continue`. Sin cambio de firma (sigue devolviendo `list[dict]`).
3. **`fields_validate.validate_dimension_lookup_races`** — ya filtraba por `canonical in ("DimensionLookup", "CombinationLookup", "DBLookup")` ANTES de resolver tabla, así que acá el mensaje se agrega siempre que la tabla no resuelva (los tres tipos, por contrato, tienen que tocar una tabla). Sin cambio de firma (sigue devolviendo `list[str]`, mismo canal que ya promueve `build.py` a `Validacion tipo="error"` vía `FIELD_INTEGRITY_PREFIX`).

**No tocado, a propósito:** `table_key_recovery.py` — resuelve la causa (recupera `table` antes de que estos 3 corran), no la reacción; esta entrada hace lo que D40 no hizo, no lo repite. Casing preservado por sitio: `dimension_step_policy.py` seguía comparando con `.strip()` sin forzar minúsculas (para no cambiar el casing en sus propios mensajes al usuario), mientras que `fragmentation.py`/`fields_validate.py` siguen normalizando a minúsculas después de llamar a `resolve_step_table()` — la función no fuerza ningún casing, cada caller decide, igual que antes.

**Verificación:** `test_architecture_layers.py`, `test_build_ktr_emission.py`, `test_contract_validate.py`, `test_dimension_field_repair.py`, `test_dimension_step_policy.py`, `test_fragmentation.py`, `test_ktr_xml_validator.py` — 77 passed / 1 failed (`test_build_ktr_get_system_info_without_fields_gets_default_field`, preexistente e independiente, ver D60). Suite completa corrida contra la misma base.

---

<a id="d63"></a>
### D63 — O1-b: dedupe de vocabulario cruzado en `DimensionLookup` — canal único `check_dimension_lookup_fields` `[O1]`

Estado: decidido y ejecutado en la sesión que cerró el Bloque 1 (D60); esta entrada es el registro faltante — se escribió el resultado (el bloque de reporte se borró de `dimension_step_policy.py:551-567`) sin dejar la justificación, y una sesión posterior (Bloque 0 de la siguiente) la pidió por separado. Auditado retroactivamente acá, sin encontrar regresión.

**Problema:** con el Sitio 3 de D60 (`enforce_dimension_step_policy`, rama `already_readonly`) y `validators/dimension_lookup_fields.py::check_dimension_lookup_fields` corriendo los dos, un `DimensionLookup` que llega ya en modo N con `fields` heredado en vocabulario modo Y se reportaba DOS VECES — mismo step, mismo defecto, dos redacciones distintas (`enforce_dimension_step_policy` inline vs. el validador pre-emisión). Se decidió un canal único: `check_dimension_lookup_fields` (corre incondicional en `build.py` para TODO `DimensionLookup`, ambos modos — cubre lo que el bloque borrado cubría y más). El bloque de `dimension_step_policy.py` se borró, dejando solo el comentario que explica por qué (líneas 539-551).

**Verificación (auditoría retroactiva, esta sesión), en el orden pedido:**

1. **¿El Finding llega al frontend?** Sí, sin regresión. `check_dimension_lookup_fields` corre vía `run_passes()` dentro de `build.py` (`table_findings`, línea ~187) → `split_findings_by_severity()` marca cada `Finding(severity="error")` con `PRE_EMIT_ERROR_PREFIX` → esa lista entra a `warnings` que `build_ktr()` devuelve → `_build_ktr_stage()` la acumula en `ktr_warnings` → `etl_generator.py` la pasa a `_split_integrity_warnings()` (líneas ~1099, ~1237), que reconoce `PRE_EMIT_ERROR_PREFIX` (junto a `FIELD_INTEGRITY_PREFIX`/`CONTRACT_PREFIX`/`ERROR_CATALOG_PREFIX`) y promueve a `Validacion(tipo="error")` en la respuesta. Cadena completa verificada archivo por archivo, no por inspección superficial.
2. **Cobertura por timing.** El bloque borrado corría dentro de `enforce_dimension_step_policy()` (llamado en `etl_generator.py` ANTES de `split_ktr_by_cut`/`compute_cut`, sobre el dict completo de la etapa). `check_dimension_lookup_fields` corre dentro de `build_ktr()`, llamado una vez POR sub-transformación después del corte (`_build_ktr_stage`, un `build_ktr()` por elemento de `sub_dicts`). Verificado que no hay pérdida: `split_ktr_by_cut()` → `compute_cut()` → `_connected_components()` (`fragmentation.py:240-266`) arma la lista `names` a partir de TODOS los steps de `ktr_data["steps"]` (no solo los que tienen hops — un step aislado es un componente singleton) y a cada `name` le asigna un `comp_id`; `groups` particiona esa asignación completa. Cada step del dict original cae en exactamente un grupo, y `_build_ktr_stage` llama `build_ktr()` una vez por grupo — la unión de lo que ven las N llamadas es exactamente el conjunto que el bloque borrado veía en una sola pasada. Sin gap de cobertura.
3. **Whitespace (hueco 0a).** Confirmado el sentido correcto: Kettle compara `<field><update>` con `equalsIgnoreCase()`, que NO recorta whitespace. Antes de `392a0f9`, `check_dimension_lookup_fields` matcheaba con `field_type.lower()` (la variable YA stripeada, usada para detectar ausencia) en vez de `raw_field_type` — divergencia real entre lo que el validador aceptaba y lo que Kettle acepta, registrada como **E-19** (`errores.md`, origen E-01). `392a0f9` ya lo corrigió a `str(raw_field_type).lower() not in valid_vocab` (línea 103) — sin strip, lee como Kettle. `lookups.py` (Sitio 4, mismo commit) no adoptó ningún strip: el bloque que abortaba (`if field_value not in valid_vocab: raise KtrBuilderError`) se borró entero, no se invirtió — el emisor ahora solo emite `field_value` tal cual llegó (D60 política de los 4 sitios), sin comparación propia. No hay inversión que revertir.
4. **Fragilidad del test.** `test_already_readonly_fact_lookup_with_crossed_vocabulary_is_left_untouched` (`test_dimension_step_policy.py`) asertaba `not any(r["campo"]=="dim_producto" and "vocabulario cruzado" in r["mensaje"] for r in results)` — frágil: pasa igual si `enforce_dimension_step_policy` empezara a emitir un finding con otra redacción para el mismo defecto. Con el fixture de ese test (loader ya coincide con `expected`, lookup ya `already_readonly`), NINGÚN branch de la función agrega nada a `results` — se cambió el assert a `results == []`, estructural: falla ante cualquier finding nuevo para este caso, no solo ante la reaparición de una frase puntual.

**Ejecutado en esta sesión:** fix de E-19 (assert) en `test_dimension_step_policy.py`, registro de E-19 en `errores.md`, esta entrada.

**Verificación runtime:** `test_dimension_step_policy.py` + `test_dimension_lookup_fields.py` + `test_build_ktr_emission.py` — 50 passed / 0 failed (corrida completa de los 3 archivos tocados por D60/D63, incluido el assert estructural nuevo).

---

<a id="d64"></a>
### D64 — O1: Alcance punto 3 (`10-estabilizar-emision.md`) verificado en corrida real — canal ya existía, sin cambio de código `[O1]`

Estado: verificado, mismo turno. **Ningún archivo de código se modificó en esta sesión** — solo trazado + corrida real + esta documentación.

**Pregunta (Alcance punto 3, pendiente desde que se escribió `10-estabilizar-emision.md`):** los findings de `enforce_dimension_step_policy` (canal (a): `results` → `job.model_json["step_policy_conflictos"]`) — ¿llegan al usuario, y por qué camino?

**Trazado (canal a), archivo por archivo:** `enforce_dimension_step_policy()` (`dimension_step_policy.py:507-523`) agrega `{"tipo": "error", "campo": tabla, "mensaje": "...falta(n)... Sobra(n)...", "repairable": True, ...}` a `results`. Ese `results` (tras el intento de `_repair_dimension_loader_fields()`, que lo deja intacto si el gate no cierra) se persiste sin transformar en:
- Flujo async (`generate_etl_async`, `etl_generator.py:2074`): `job.model_json["step_policy_conflictos"]`, leído por `_try_build()` (`etl_generator.py:1820`) y convertido con `Validacion(**c)` — Pydantic v2 ignora las claves extra (`repairable`/`step_name`/`missing`/`sobra`) por default (`Validacion` no declara `model_config(extra=...)`), así que `tipo`/`campo`/`mensaje` (el texto completo, con los nombres de columna) pasan intactos a `extra_validaciones`.
- Flujo síncrono (`etl_generator.py:1683`) y `build_etl_from_raw()` (`etl_generator.py:1393`/`1433`): mismo patrón, `Validacion(**r)` o `.extend(step_policy_results)` directo a `data_2["validaciones"]` (que Pydantic valida igual al construir `ETLGenerateResponse`).

En los tres casos, `extra_validaciones`/`data_2["validaciones"]` entra a `ETLGenerateResponse.validaciones` (`_build_response_from_two_ktr_data`, `etl_generator.py:1248-1251`) — el MISMO campo, la MISMA lista, donde cae el canal (b) (`check_dimension_lookup_fields` vía `_split_integrity_warnings`, D63). El frontend (`ResultView.jsx:116-121`, `ValidationItem` línea 28) renderiza `validaciones` sin distinguir canal: un badge por `tipo` (`Error`/`Advertencia`/`Info`), campo, mensaje completo sin truncar, dentro de la sección "Validaciones".

**Conclusión: no hay hueco que cerrar — el canal ya era el mismo (canónico) desde `149b836` (commit que introdujo `step_policy_conflictos`, anterior a toda la serie D57/D58/D60).** El punto 3 del Alcance se escribió como pendiente pero la wiring ya existía; lo que faltaba era la verificación contra una corrida real, no el código.

**Verificación (corrida real, no unit test con mocks):** `build_etl_from_raw()` invocado directamente con el corpus real de E-01 (`docs/refactor/fase4_manual/sonnet/etl-llm-raw-test-01_sonnet_fase4.json`) y `dim_contracts` reconstruidos a mano desde `DDL-inferido-test-con-raw.txt` (`dim_producto` SCD1: `technical_key=sk_producto`, `attributes_scd1=[bk_producto, nombre_producto, nombre_categoria, precio_unitario]`), `llm=None` (sin costo, sin red — mismo modo que "Reutilizar respuesta"). Resultado en `result.validaciones`:

```
[error] campo='dim_producto': Step 'Cargar dim_producto' es la única candidata para 'dim_producto'
(dimensión declarada en dim_contracts), pero no trae en 'fields' los atributos que el contrato
declara — falta(n): nombre_categoria. Sobra(n) (no pertenecen a esta dimensión): fk_categoria,
precio_lista, stock. Probable loader faltante...
```

más 6 findings `[Dimension lookup/update]` (canal b) nombrando cada atributo (`nombre_producto`, `fk_categoria`, `precio_lista`, `precio_unitario`, `stock`, `bk_producto_calculado`) con `type='Update'` fuera de vocabulario modo N. **Ambas señales — vocabulario cruzado Y los 3 nombres de columna inexistentes — llegan al usuario antes de ejecutar, en la misma corrida.** Build completo, sin excepción: 1 archivo (`origen_stg`) + 2 archivos + 1 `.kjb` (`stg_dwh`, partido por `compute_cut`) + `.kjb` maestro. Los 3 `.ktr` generados son XML bien formado (verificado con `xml.etree.ElementTree.parse()` — no se abrió Spoon literalmente en este entorno, mismo proxy que el resto de este objetivo usa).

**Repair no se disparó en esta corrida** (el finding de canal (a) llegó sin reparar, con `llm=None`): `_repair_dimension_loader_fields()` retorna sin intentar nada apenas `llm is None` (`etl_generator.py:700-702`), ANTES de evaluar `_deterministic_field_mapping()` — que no necesita LLM y hubiera resuelto `nombre_categoria`→`categoria` (prefijo `nombre_`) igual. No es un bug de esta verificación: es una oportunidad de repair gratis que hoy queda gateada detrás de un chequeo que no debería aplicarle — registrado como **E-21** (`errores.md`), no corregido acá (fuera del alcance de este punto — el piso, entregar con el problema documentado, se cumple igual con o sin repair).

**Encontrado, no buscado — E-20 (`errores.md`):** los 6 findings de canal (b) aparecen **duplicados** (12, no 6) en `result.validaciones`. Causa confirmada con stack trace: `_recover_table_keys()` (H29, `etl_generator.py:305-334`) corre `run_passes()` — el tuple `PRE_EMIT_PASSES` COMPLETO, no solo `recover_table_key` — sobre el `ktr_data` completo ANTES del corte; `build_ktr()` (vía `_build_ktr_stage`) corre el mismo `run_passes()` completo otra vez sobre el sub-dict ya partido. `check_dimension_lookup_fields` (y cualquier otro pass de `PRE_EMIT_PASSES` insensible a si `table` ya se recuperó) no tiene forma de saber que ya corrió — el mismo finding sale dos veces, byte a byte. No es específico de este corpus: aplica a toda corrida con dimensiones (sync, async, `build_etl_from_raw`), desde que `_recover_table_keys` se cableó (H29). No bloquea el criterio de aceptación (el finding SÍ llega, con toda la info) pero es ruido real para el usuario — el mismo error se ve dos veces sin explicación. Abierto, `Origen=E-01` (encontrado verificando su cierre), no se corrige en esta sesión (regla de escritura: descubrir es libre, actuar necesita ruta — y esto no estaba en el alcance del prompt que originó esta sesión).

**Verificación runtime:** ninguna (sin cambio de código, no aplica correr la suite). La corrida real de arriba se hizo con un script ad-hoc (`repro_dim_producto.py`, scratchpad), no un test nuevo — no se agrega a `backend/tests/` porque no hay código nuevo que cubrir; si E-20 se corrige en una sesión futura, ESE cambio sí necesita test.

---

## D65 — O1-b cierra; con eso, O1 queda completo

**Fecha:** 2026-08-03
**Commit:** `80a1e3b`

**Qué se decidió**
O1-b se da por cerrada. O1-a y O1-c ya estaban cerradas, así que O1 queda completo.

**Evidencia**

- Test `test_e01_corpus_through_real_async_pipeline_reaches_built` (`backend/tests/test_ktr_build_job_api.py`): corre el corpus real de E-01 por el camino asíncrono completo — `/generate-async` → `/connections` → `/status` —, ruta nunca antes ejercitada (D64 solo había corrido `build_etl_from_raw()` directo). Resultado: `model_status == "done"`, `build_status == "built"`, y el finding de vocabulario cruzado llega a `result.validaciones` nombrando los 3 campos inventados (`fk_categoria`, `precio_lista`, `stock`).
- Sin Spoon en esta máquina (verificado: no hay Pentaho Data Integration instalado). En su lugar se hizo cross-check de los `<type>` XML emitidos contra `investigacion-tags-validos-por-step.md`: 13 tipos de step del corpus, todos con plugin id real verificado, ninguno cae en la trampa de E-11.
- Fix de Bloque 3: `_build_response_from_two_ktr_data` (`backend/app/services/etl_generator.py`) ya no descarta la etapa origen→STG cuando la etapa STG→DWH falla estructuralmente. Ahora entrega esa etapa sola más un `Validacion(tipo="error")` con el motivo del fallo de la otra. Test: `test_stg_dwh_structural_failure_still_delivers_the_origen_stg_stage_built` (`backend/tests/test_etl_generate_response_shape.py`).
- Suite completa: 733 passed / 30 failed. Baseline previo a esta sesión: 730 passed / 31 failed. Cero regresión, 3 tests nuevos en verde.

**Qué supersede**
La baja a "parcial" de los criterios 3 y 4 que hizo la sesión de auditoría anterior. Ambos vuelven a "Hecho", ahora respaldados por corrida real y no solo por lectura de código.

**Efectos colaterales registrados, NO arreglados**
Quedan abiertos en `errores.md`; no bloquean el cierre.

- **E-23** — impacto de E-21 confirmado empíricamente: con LLM disponible, el repair determinístico resuelve el caso sin llegar a llamar al modelo.
- **E-24** — nuevo: los findings de "vocabulario modo N" sobreviven en `validaciones` después de que el repair H51 reclasifica el step a modo Y con vocabulario correcto. El archivo final queda bien, pero el finding que ve el usuario describe un estado ya superado.

---

<a id="d66"></a>
### D66 — O2-c: `lineage_builder.py` partido en dominio (`domain/lineage.py`) e infraestructura, registro retroactivo `[O2]`

Estado: decidido y ejecutado en la sesión que cerró O2-c (misma sesión que cerró O2-a/O2-b, 2026-08-03); esta entrada es el registro faltante — la fila del mapa (`arquitectura-objetivo.md`) y `docs/README.md` ya decían "cerrada"/"Ejecutado (O2-c)" sin que existiera una D-N propia. `docs/README.md` había anotado "D63 pendiente de redactar" como placeholder; D63 se usó después para un tema distinto (dedupe E-20, O1-b) y la referencia quedó apuntando a un número equivocado — corregida en la sesión que escribe esta entrada (ver D67).

**Problema:** `lineage_builder.py` era la última fila **partido** barata del mapa capa-objetivo. `build_lineage`, `stitch_lineage_many` y `stitch_lineage` son funciones puras sobre el dict KTR (armar el grafo de linaje origen→staging→DWH); `_parse_ktr_xml` lee XML ya serializado — infraestructura.

**Decisión:** las tres funciones puras se mueven a `domain/lineage.py`, devolviendo `LineageGraphData` — dataclass propia de stdlib, no `schemas.lineage.Lineage` (`BaseModel` de Pydantic, prohibido en `domain/` por `domain/README.md` § "Qué NO va acá", motivo no explícito en la fila original del mapa hasta esta ejecución). `services/lineage_builder.py` queda como borde: convierte `LineageGraphData` → `Lineage` para la API y conserva `_parse_ktr_xml` (infra). Firmas públicas sin cambios: `build_lineage`, `stitch_lineage_many`, `stitch_lineage`, `build_lineage_from_xml`, `stitch_lineage_from_xml` siguen expuestas desde `services/lineage_builder.py` — `routers/ai.py` y `etl_generator.py` (congelado, `90-congelado.md` T8, no tocado) no necesitaron ningún cambio.

`domain.lineage` agregado a `DOMAIN_MODULES` en `test_architecture_layers.py`. `FROZEN_R1` sigue vacío — el import a `schemas.lineage` que tenía el módulo original ya no existe del lado `domain`, sin excepción nueva que registrar. Mapa (`arquitectura-objetivo.md`, fila `services/lineage_builder.py`) marcado "Ejecutado (O2-c)".

**Verificación:** suite completa 697 passed / 54 failed, igual a la cifra de O1-c — cero regresión. `test_architecture_layers.py` verde.

---

<a id="d67"></a>
### D67 — O2 verificado completo al pedir "empezar O2"; nada ejecutado, solo verificación y corrección de docs `[O2]`

Estado: verificado, mismo turno. **Ningún archivo de código se modificó en esta sesión** — solo trazado contra código/git, `docs/README.md` y esta documentación.

**Contexto:** el pedido de sesión fue "Leé `docs/README.md` y `docs/refactor/10-estabilizar-emision.md`. Comienza O2." Antes de escribir código, se verificó el estado real de O2-a/O2-b/O2-c contra el código (Regla A de `docs/README.md`: ningún documento de estado es autoridad sobre si algo está hecho).

**Hallazgo:** las tres sesiones de O2 (`20-arquitectura.md`) ya estaban ejecutadas:

- `domain/common.py` + `services/ktr_builder/xml_helpers.py` existen (O2-a, D61).
- `domain/step_table.py` existe, con `resolve_step_table()` consumida por los tres call sites (O2-b, D62).
- `domain/lineage.py` existe, 11 KB (O2-c) — sin D-N propia hasta esta sesión, ver D66.
- `backend/tests/test_architecture_layers.py`: 4 passed, `FROZEN_R1` vacío.
- Mapa capa-objetivo (`arquitectura-objetivo.md`) marca las tres filas correspondientes "Ejecutado".

**Discrepancia encontrada y corregida en el mismo turno (Regla 8 de `docs/README.md`):** `docs/README.md`, tabla de sesiones, fila O2-c decía "D63 pendiente de redactar". D63 ya estaba escrita — para un tema distinto (dedupe de vocabulario cruzado, O1-b). La referencia quedó de un placeholder anterior a que D63 se asignara a otra decisión. Corregida para no apuntar a un número equivocado; la D-N real de O2-c es D66 (arriba).

**Decisión:** no hay nada que ejecutar para O2 — los criterios de terminado de `20-arquitectura.md` (O2-a/b/c con su D-N, suite verde, `FROZEN_*` no creció, filas del mapa marcadas) se cumplen. O2 queda cerrado. Próximo paso natural: O3 (`30-decision-python-llm.md`), que según `docs/README.md` necesita O1 cerrado (D65) + `referencia/` escrita (sesión REF, cerrada 2026-08-03) — ambas precondiciones ya cumplidas.

**Verificación:** `test_architecture_layers.py` corrido esta sesión, 4 passed. Sin cambio de código, no aplica correr la suite completa.

---

<a id="d69"></a>
### D69 — O2-d: el borde de un upload vive en infraestructura, no en el router `[O2]`

**Contexto:** una sesión de validación de `routers/`+`repositories/` contra `docs/arquitectura-objetivo.md` encontró que `routers/schema.py::infer_schema` manejaba el ciclo de vida completo del upload (crear el `tempfile`, iterar `UploadFile.read()` con el límite de 50 MB, borrar el archivo en un `finally`) dentro del router — viola R2 ("el router no toca... el disco. Solo llama a un service"). No estaba en ninguna lista `FROZEN_*` de `test_architecture_layers.py`: ese test cubre a propósito solo un recorte de R1/R3/R4 (ver su docstring), nunca midió R2. No era deuda ya registrada, era un hueco del radar de verificación. Registrado como E-25 en `errores.md`.

**Decisión:** se agrega `infer_schema_from_upload(filename, chunks)` a `services/file_schema.py`, dueña de la extensión permitida, el límite de tamaño, el tempfile y su cleanup. `infer_file_schema(path, source_name)` no cambia de firma — sigue recibiendo un path ya escrito, los 7 tests que la llaman directo no se tocan. El router queda como traductor puro: arma un `AsyncIterator[bytes]` desde `UploadFile.read()`, llama al service, y mapea `UnsupportedFileType`→422, `FileTooLarge`→413, `ValueError`→422, el resto→500.

**Por qué NO se copió el patrón de `job_analyzer.py`:** ese service recibe `fastapi.UploadFile` directo — es una violación de R3 ya congelada (`FROZEN_R3`). Copiarla acá hubiera hecho fallar `test_services_do_not_import_fastapi`, porque `file_schema.py` no está congelado. `infer_schema_from_upload` recibe `filename: str | None` + `chunks: AsyncIterator[bytes]`, sin conocer `fastapi` — el test fuerza el diseño correcto en vez de dejarlo a criterio.

**Por qué se ejecutó sin abrir un objetivo nuevo:** la regla de migración prohíbe sesiones cuyo único fin es mover archivos, pero acá no se movió un archivo — se reubicó una responsabilidad que estaba del lado equivocado de una regla, en un cambio acotado a 2 archivos de código con contrato HTTP idéntico. Se reabrió O2 (cerrado 2026-08-03, D67) como O2-d en `20-arquitectura.md` en vez de crear un objetivo nuevo.

**Alcance descartado a propósito:** no se tocó `job_analyzer.py` (mismo problema de fondo, R3 en vez de R2, congelado en `FROZEN_R3`, superficie mucho mayor sin corrida real que la ejerza) ni `routers/ai.py`/`routers/connections.py` (violaciones de R2 más amplias — `db.commit()`/`db.rollback()` directo en el router —, ya con su parte de ORM cubierta por `FROZEN_R4`).

**Verificación:** `test_file_schema.py` con 2 tests nuevos (413 por tamaño excedido, `.xlsx` completo por endpoint). `test_architecture_layers.py` verde con `FROZEN_*` sin cambios — R2 no es lo que ese test mide, así que este fix ni la achica ni la agranda. `grep -n "tempfile\|os.unlink" backend/app/routers/schema.py` sin resultados.

**Estado:** ejecutado, esta sesión (2026-08-04).
