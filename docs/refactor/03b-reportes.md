# Reportes — Track F (investigación, diseño, narrativa de sesión)

**Append-only.** Cada reporte se escribe una vez, al cierre de la sesión que lo produjo, y no se reedita — una corrección se agrega como nota fechada, no reescribe el reporte original.

**Última actualización:** 2026-07-27

Detalle de apoyo para [`03-plan.md`](03-plan.md): algoritmos, investigación y narrativa de cierre de sesión que por sí solos no son el estado vigente de una fase. El estado vigente vive únicamente en [`ESTADO.md`](ESTADO.md). Si algo acá contradice `ESTADO.md` o [`02-decisiones.md`](02-decisiones.md), gana `02-decisiones.md` — esto queda desactualizado hasta que alguien lo corrija.

---

<a id="reporte-f1"></a>
## Reporte F1 (2026-07-22)

**Q1 — ¿Cada step expone tabla + modo R/W de forma confiable antes del XML?** No. `ETL_OUTPUT_SCHEMA.ktr.steps[*]` (`etl_output.py:90-117`) solo tiene `name`/`type`/`config` (config como string JSON, forma libre por tipo — `etl_output.py:101-104`). `data_1["ktr"]`/`data_2["ktr"]` (`etl_generator.py:433-434`) traen esa misma forma. Tabla + modo hay que derivarlos, y hoy existen dos extractores parciales y divergentes: `contracts.STEP_CONTRACTS.key_aliases` (`contracts.py:318-360`, resuelve alias pero no calcula modo) y `lineage_builder._extract_table`/`_TABLE_FIELD_TYPES` (`lineage_builder.py:20-27,51-59`, ignora los alias de `contracts.py` — H4 — y no cubre `DBLookup` — H11). El motor de corte no puede apoyarse en ninguno de los dos tal cual están; necesita la matriz de H19 centralizada bajo D8 antes de F2.

**Q2 — mapa tipo_step → {R,W}:** construido, ver **H19** en `01-hallazgos.md`. Hallazgo central: `DimensionLookup` y `CombinationLookup` son R+W **siempre**, no condicionalmente — `DimensionLookup` porque el builder hardcodea `<update>Y</update>` (`ktr_builder/steps/lookups.py:47`), `CombinationLookup` porque es la semántica nativa del step (sin flag para desactivar el insert). `DBLookup` es R puro (nunca escribe). `ExecSQL` no es clasificable sin parsear su SQL — el corte debe fallar fuerte ante él (D5), no asumir.

**Q3 — ¿`build_kjb_xml` soporta `JobEntryJob`?** No — cero ocurrencias, confirmado (H7, ya resuelto en sesión previa). Qué haría falta: discriminador en `JobEntry` (`job_schemas.py:42-46`, hoy sin campo de tipo), una función `_job_entry()` nueva con el XML de `JobEntryJob` (tags distintos a `_trans_entry`, no un swap de string — `job_analyzer.py:359-388`), branch en el loop de `build_kjb_xml` (`job_analyzer.py:272-274`), y un call site nuevo para `job_master.kjb`. Detalle completo en H7 actualizado.

**Q4 — ¿`_build_job_plan` ordena por FK o fijo?** Fijo. `etl_generator.py:224-246` arma siempre 2 `JobEntry` (`:240-244`); el docstring dice explícitamente que el orden nunca fue ambiguo con 2 archivos (`:225-229`). No hay ningún ordenamiento por grafo de FK en el código hoy — bajo N>1 por etapa, ese ordenamiento (dims antes que hechos, per `00-objetivo.md`) es lógica nueva a escribir, no una extensión de algo existente.

**Q5 — ¿matriz sin re-parsear XML?** Sí. `build_lineage(ktr_data)` (`lineage_builder.py:87-132`) ya opera sobre el dict pre-XML — mismo dato que cita D6 evidencia #3. El fallback XML (`_parse_ktr_xml`) solo aplica al flujo `CreateJob` (`.ktr` de autoría externa), no al de generación.

**Recomendación de dónde insertar el corte:** entre `repair_integrity_gaps` y `build_ktr()` (`etl_generator.py:801-804` → `:438-460`) — mismo punto del pipeline que `repair_ktr_steps`/`repair_integrity_gaps`/`enforce_dimension_step_policy` (D6 evidencia #4). Detalle en **H20**.

**Nota — el "2" está hardcodeado en 3 puntos, no 1** (evidencia en H1 actualizado): dos llamadas al LLM por `mode` (`etl_generator.py:782-786`, duplicado en `:931-935`) + `_build_job_plan` (`:240-244`). F2/F3 reemplazan estructura, no ajustan un número.

---

<a id="reporte-f2"></a>
## Reporte F2 (2026-07-22)

**Nota de estado antes de empezar:** F1.5 (centralizar H4+H11+H6) no estaba implementado en código todavía en este momento de la sesión, solo diseñado por D14 — ya cerrado en código desde entonces, ver tabla de estado en `03-plan.md`. Lo que sí estaba hecho es C.2 y el reporte de F1. F2 es una fase de **diseño**, no de implementación (el handoff original: "reportá el plan, no implementes") — el diseño de abajo referencia dónde F1.5 tiene que aterrizar sin asumir que ya aterrizó.

**Actualización (2026-07-22, `bitacora_etl_ventas.md`/`extracto_corte_F2.md`):** F3 tiene un tercer prerrequisito además de F1.5/F2.5, externo a Track F — ver D16 en `02-decisiones.md`. C1-bis (validado contra `err1.ktr`/`err2.ktr`, H21) se preguntó si era un fantasma (artefacto de step mal elegido, no señal estructural real); verificado contra código: **no lo es, todavía** — `dim_contracts`/`dimension_step_policy` no deriva ningún step de solo lectura para el lado del hecho (H22), así que un lookup de FK sigue siendo R+W por construcción y C1-bis sigue disparando correctamente sobre ese patrón. El fix real vive en el eje `dim_contracts` (D11), no en el algoritmo de corte.

**Insumo obligatorio (D7):** contenido de `err1.ktr`/`err2.ktr` analizado — ver **H21** en `01-hallazgos.md`. Resumen: un solo `.ktr` de STG→DWH con (a) `dim_producto` escrita+leída por dos `DimensionLookup` distintos (`Cargar Dim Producto`, rama muerta sin hop de salida; `Lookup Dim Producto`, en la rama de hechos) sin hop entre ambos — carrera + doble escritor reales (E4/E5); (b) `dim_tiempo` leída por `Lookup Dim Tiempo` (`DBLookup`) sin ningún productor en el archivo — dimensión nunca cargada (E6).

### Algoritmo

**1. Matriz R/W por etapa** (sobre `STEP_CONTRACTS` extendido en F1.5 + la tabla de H19): para cada step, resolver `{tabla: {"read"|"write"}}`. Steps sin tabla (StreamLookup, transformaciones puras) no aportan al mapa. `ExecSQL` (SQL arbitrario, no clasificable — Q2 de F1) queda **fuera** de la matriz — no participa del corte, y dispara una notificación D15 ("`ExecSQL` en step 'X' — SQL no analizado, verificar manualmente contra el resto del corte") en vez de asumir modo.

**2. Dos disparadores de corte, no uno** — el handoff solo escribió C1 (W+R misma tabla). El corpus real (H21) muestra que **doble escritor sin lectura intermedia** es un caso separado y real (E4 de `00-objetivo.md`, segunda viñeta), así que el diseño agrega **C1-bis**:
   - **C1** (ya en el handoff): tabla T escrita por el step A y leída por el step B, A≠B, en la misma etapa → corte.
   - **C1-bis** (nuevo, motivado por H21): tabla T escrita por dos steps distintos A≠B en la misma etapa (sin necesidad de que ninguno la lea) → corte. Caso real: si `dim_tiempo` tuviera además un segundo `CombinationLookup` cargándola en otra rama, sería este caso; en `err1`/`err2` el disparador real es C1 (dos `DimensionLookup`, cada uno R+W, cuentan como escritor Y lector de la tabla). **Reconciliado (2026-07-22):** se preguntó si C1-bis era un fantasma. No lo es todavía — ver H22/D16: hasta que `dim_contracts` derive un step de solo lectura para el lado del hecho, un lookup de FK sigue siendo R+W por construcción y C1/C1-bis siguen siendo la señal correcta sobre ese patrón, no un falso positivo del algoritmo.

**3. Componentes:** partir del grafo de hops (componentes conexos, ignorando tablas). Para cada tabla que dispara C1/C1-bis:
   - Si el step escritor y el step lector/segundo-escritor ya caen en componentes de hop **distintos** (caso `err1`/`err2`: `Cargar Dim Producto` es su propio componente, `Lookup Dim Producto` está en el componente de hechos) → no hace falta partir nada más, alcanza con **ordenar** los dos componentes.
   - Si caen en el **mismo** componente, hay dos sub-casos (refinado 2026-07-22 con `bitacora_etl_ventas.md`, ver H21):
     - **Excepción self-lookup/insert-new-only:** si todos los steps que LEEN T tienen camino de hops hacia todos los steps que ESCRIBEN T dentro del componente (lectura estrictamente aguas arriba de la escritura — el idioma "chequear si existe → filtrar → insertar"), **no dispara corte.** Es un patrón seguro y a propósito, reforzado con `UNIQUE` sobre la clave natural (R7/L2-E05, `02-decisiones.md` C.5). Aplicar C1 tal cual sobre este patrón sobre-corta.
     - **Cualquier otra relación dentro del mismo componente** → caso genuinamente difícil, **sin evidencia en el corpus actual**: el step "después" de un corte hipotético perdería el stream en memoria y tendría que reconstruir lo que necesita solo desde BD. **Alcance implementado para F3: caso "componentes ya separados" + excepción self-lookup (ambos evidenciados); este sub-caso se detecta y se notifica (D15) como no soportado automáticamente, en vez de generar un corte que probablemente no compile en Kettle.**
   - Componentes sin ninguna tabla-disparador no se tocan (D6-bis: sin señal, no hay corte) — se agrupan todos juntos en un único archivo por etapa, salvo que una relación de tabla los fuerce a separarse.

**4. Orden entre componentes:** grafo dirigido componente-a-componente, una arista por cada relación de tabla-disparador (escritor → lector/otro-escritor). Orden topológico de ese grafo = orden de los KTR dentro de la etapa (dims antes que hechos, per `00-objetivo.md`). Si el grafo tiene ciclo → caso patológico genuino, cae bajo D15 (notificar, no bloquear).

**5. V2 (lookup sin productor, caso `dim_tiempo`):** no es señal de corte (D15 ya lo fija). Se detecta en la misma pasada que arma la matriz R/W (una tabla leída que nunca aparece como escrita por ningún step de la etapa) y se emite como notificación accionable: qué tabla, qué step la consulta, que no tiene productor.

### Validación contra `err1.ktr`/`err2.ktr` (H21)

Aplicando el algoritmo: `dim_producto` dispara C1 (escrita+leída por `Cargar Dim Producto` y `Lookup Dim Producto`, componentes de hop ya distintos) → 2 KTR:
- `KTR_A`: `Leer Staging Productos`, `Cargar Dim Producto`.
- `KTR_B`: `Leer Staging Ventas`, `Filtrar Ventas Anuladas`, `Descartar Anuladas`, `Castear Campos Ventas`, `Calcular Importe`, `Lookup Dim Producto`, `Lookup Dim Tiempo`, `Cargar Fact Venta`.

Orden: `KTR_A` antes que `KTR_B` (escritor de `dim_producto` antes que su lector). `dim_tiempo` → notificación V2/D15 sobre `Lookup Dim Tiempo`, sin afectar el corte. Coincide con la partición que un modelador humano haría a mano — es la prueba de humo que pide D7.

**Segunda validación independiente (2026-07-22, `bitacora_etl_ventas.md`/R3):** dos soluciones que no se vieron entre sí (una SQL-colapsada, otra steps-Kettle con `StreamLookup`), partiendo del mismo `.ktr` de origen (`dim_producto` + `fact_venta`), convergieron en la misma partición: dimensión en KTR separada, secuenciada antes del hecho vía KJB, KTR de Origen→Staging intacto. Refuerza la validación de `err1`/`err2` con un caso corrido en verde contra Postgres real, no solo análisis estático — ver R3 en la tabla de intake de `01-hallazgos.md`.

### Archivos a tocar (diseño original para F3)

- **Nuevo** `backend/app/services/ktr_builder/fragmentation.py`: `build_rw_matrix()`, `compute_cut()` (componentes + notificaciones D15), `order_components()` (orden topológico). Consume `STEP_CONTRACTS` extendido (F1.5), no reimplementa resolución de alias/tabla.
- `backend/app/services/etl_generator.py` — punto de inserción entre `repair_integrity_gaps` y `build_ktr()` (H20); `_build_job_plan` generalizado de 2 `JobEntry` fijos a N por etapa.
- `backend/app/services/lineage_builder.py` — `stitch_lineage` generalizado de 2 KTR fijos a M archivos con prefijos por índice.
- `backend/app/services/job_analyzer.py` — jerarquía de 3 niveles (F2.5/H7): `.kjb` por etapa reusa `build_kjb_xml()` ya existente (generalizada a N entries), `job_master.kjb` necesita `JobEntryJob`.
- `backend/app/services/ktr_xml_validator.py` / `build.py` — conversión del `raise KtrXmlValidationError` a anota-y-notifica (D15).

**Nota:** este reporte fue el punto de aprobación (D17, 2026-07-23) — ver estado de implementación real en [Estado F3](#estado-f3) abajo y D19/D20 en `02-decisiones.md`.

---

<a id="estado-f3"></a>
## Estado F3 — narrativa de sesión

#### Sesión 1 (2026-07-24) — algoritmo puro

`backend/app/services/ktr_builder/fragmentation.py` — `build_rw_matrix()` (rol R/W/RW por step sobre tabla, reusa H19 + el flag `update` de D16 para `DimensionLookup`) y `compute_cut()` (disparadores C1/C1-bis, componentes conexos por hops, excepción self-lookup/insert-new-only, orden topológico entre grupos, notificación V2 y notificaciones D15 para el caso patológico/ciclo). Algoritmo completo del diseño de F2, ningún atajo. Validado con `tests/test_fragmentation.py` (4 tests, todos verdes): reproduce la partición exacta de `err1.ktr`/`err2.ktr` (loader de `dim_producto` separado de la rama del hecho, en ese orden), confirma que un ETL simple no dispara corte (D6-bis), y confirma la excepción self-lookup.

#### Sesión 2 y 3 (2026-07-24) — wiring de servicio (D19) + backend de la respuesta (D20)

**Hecho (wiring, puntos 1-4):**
1. `split_ktr_by_cut()` (`fragmentation.py`) — parte `ktr_data` en N sub-dicts según `compute_cut()["groups"]` (1 grupo → mismo objeto, cero costo/cero cambio de comportamiento).
2. `_build_ktr_stage()` (`etl_generator.py`) — usa `split_ktr_by_cut()` + llama `build_ktr()` una vez por grupo, en el punto H20 (entre `repair_integrity_gaps` y `build_ktr()`).
3. `_build_job_plan()` (`etl_generator.py`) generalizado de 2 `JobEntry` fijos a N por etapa — jerarquía de 3 niveles (F2.5/H7): 1 archivo por etapa → `entry_type="trans"` directo (comportamiento histórico); N>1 → `.kjb` intermedio + `entry_type="job"` en el job maestro.
4. `stitch_lineage_many()` (`lineage_builder.py`) generalizado de 2 KTR fijos a M archivos (prefijo `F{idx}::`, matching de sink→source por nombre de tabla entre archivos no adyacentes). `stitch_lineage(a, b)` pasa a ser un wrapper de `stitch_lineage_many([a, b])`.

Tests: `tests/test_fragmentation_wiring.py` (13, todos verdes) — split, `_build_ktr_stage` (mock de `build_ktr`), `_build_job_plan` N-ario (incl. validación XML real del `.kjb` intermedio y del maestro), `stitch_lineage_many` (caso no-adyacente, no-self-match, equivalencia con `stitch_lineage` de 2 archivos).

**Hueco encontrado durante el wiring (ver D19 en `02-decisiones.md`):** `ETLGenerateResponse` y el ZIP del frontend seguían fijos a exactamente 1 KTR por etapa + 1 KJB — no había dónde poner los archivos extra de un corte real. El flujo HTTP en vivo llamaba `compute_cut()` directamente (notificaciones V2/patológico incluidas) pero no invocaba `_build_ktr_stage()` para partir de verdad.

**Diseño de la extensión — cerrado (D20).** Slots fijos `ktr_xml`/`ktr2_xml` pasan a una lista de 2 `EtapaOutput` (Origen→Staging, Staging→DWH, orden fijo), cada una `{tipo:"ktr", archivo:{...}}` o `{tipo:"kjb", kjb:{...}, archivos:[...]}`. `kjb_master` se mantiene igual. Sin requisito de compatibilidad hacia atrás (único consumidor es el frontend de este repo).

**Hecho (sesión 3) — backend de D20 implementado y conectado de verdad:**
1. `ETLGenerateResponse` (`etl_schemas.py`) reemplazó `ktr_xml`/`ktr2_xml`/`kjb_xml` por `etapas: list[EtapaOutput]` + `kjb_master`. `_build_response_from_two_ktr_data`/`_build_response_from_data` (`etl_generator.py`) ya no llaman `build_ktr()` directo — pasan por `_build_ktr_stage()`, así que un `groups>1` real sale como N archivos + `.kjb` intermedio.
2. **Test de integración end-to-end contra el pipeline HTTP completo:** `test_etl_generate_response_shape.py::test_generate_from_inference_http_endpoint_delivers_real_split` — `TestClient` contra `POST /api/v1/etl/generate-from-inference` con LLM mockeado y un caso que dispara C1 de verdad.
3. Registro de 2 bugs reales encontrados al conectar el corte de verdad — detalle completo en D20 (`02-decisiones.md`, sección "Backend implementado 2026-07-24"): nombre/filename duplicado entre sub-archivos (`build_ktr()` prioriza `ktr_data["name"]`); `compute_cut()` separaba componentes de hop desconectados sin ninguna señal estructural (violaba su propio docstring).

Tests: `test_etl_generate_response_shape.py` (5 casos) + 2 tests nuevos en `test_fragmentation.py`/`test_fragmentation_wiring.py`. Suite completa: mismos 45 fallos preexistentes de antes de la sesión, cero nuevos.

**Falta para cerrar F3:** frontend (D20-punto5) — consumir `etapas`/`kjb_master`, armar el ZIP con carpetas por etapa partida. Rompe sin período de convivencia (D4/D20-punto2): un ETL generado con el backend de esta sesión no lo puede leer el frontend actual hasta que esa sesión corra.
