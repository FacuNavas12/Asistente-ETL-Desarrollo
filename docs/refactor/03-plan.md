# Plan — Refactor de fragmentación

**Última actualización:** 2026-07-22

Deriva de [`00-objetivo.md`](00-objetivo.md) y [`01-hallazgos.md`](01-hallazgos.md), evaluado contra [`02-decisiones.md`](02-decisiones.md). Consolida dos planes que llegaron por separado y que hoy conviven sin fusionar:

- **Track A — Auditoría de arquitectura:** prompts ya escritos, fase-0 a fase-7, uno por sesión (`Contexto Cambios/Arquitectura/`). **Ninguna fase se ejecutó todavía** — `docs/arquitectura-objetivo.md` ya está en el repo (actualizada 2026-07-22 con D6/D6-bis), pero `docs/auditoria/` no existe: nadie corrió Fase 0 en adelante. `00-plan-auditoria.md` es la versión vigente; `prompt-auditoria-arquitectura.md` está marcado `SUPERSEDIDO` por el propio material, no usar.
- **Track F — Motor de fragmentación:** prompt de 3 fases + track de errores de 6 puntos (`Contexto Cambios/Fragmentacion/handoff_fragmentacion_y_errores.md`). Tampoco se ejecutó — es la Fase 1 (investigar y reportar) la que sigue, y requiere aprobación explícita antes de cada fase siguiente.

Los dos tracks comparten un tema — el borde tipado de entrada — pero no dependen de él de la misma forma. `00-plan-auditoria.md` lo declaró **PASO 1 obligatorio** de Track A, en su versión grande (H2: schema `string → object`, tipo validado por construcción). Track F **no** necesita esa versión grande para arrancar: **D14** (`02-decisiones.md`) separa lo que el motor de corte requiere en concreto — H4, H11, H6 — que es chico, ya tiene dirección decidida (D5, D8), y no depende de ningún spike ni de Track A. Ese subconjunto pasa a una fase previa propia (F1.5) dentro de Track F.

---

## Intake de hallazgos de tests — taxonomía S/G/D/Env

Los tests de fragmentación siguen viniendo (2026-07-22: un test simple, `bitacora_etl_ventas.md`, ya trajo 12 reglas de las cuales solo 3 son corte — ver `01-hallazgos.md`, sección "Intake"). Sin un clasificador, cada test agrega H-numbers sueltos que nadie rutea. Mecanismo, adoptado de la taxonomía S/G/D/E que la propia bitácora ya usa (ahí "E" es fuerza de confirmación — log/DDL/archivo/contraste — no categoría de ruteo; acá se separan los dos ejes):

**Eje 1 — qué tipo de problema es (determina el ruteo):**

| Tag | Qué cubre | Rutea a |
|---|---|---|
| **S** | Estructural-de-corte: races, doble escritor, dimensión sin loader antes del hecho — corrección estructural en el sentido de D6-bis, nada más | Track F (F2/F3) |
| **G-step** | Selección de step por forma de tabla o por rol (loader vs. lookup), SCD1/SCD2, materialización de claves en el INSERT | Eje `dim_contracts`/`dimension_step_policy` (D11) — **no** Track F |
| **D-dialecto** | SQL dependiente del motor: tipos de `COALESCE`, `DISTINCT ON`, `generate_series`, alineación de tipos de clave contra el DDL | F4 (contenido generado) + cruza con D12/C.1 (plan de dialecto) |
| **D-integridad** | Completitud referencial: dimensión sin productor (converge con V2 si es exactamente ese caso), claves no resueltas antes del insert del hecho | F4, algunas bloqueadas por decisión de negocio (ver Abiertos en `02-decisiones.md`) |
| **D-ddl-constraint** | Constraints que el backend podría recomendar/emitir sobre el DDL destino | Nuevo — sin dueño hasta decisión de producto (superficie que hoy no existe) |
| **Env** | Comportamiento específico del motor de ejecución/entorno (versión de PDI, pooler de conexión) que determina qué step usar | Nuevo hallazgo de entorno — destino natural es una regla en `system_etl.txt`, no código del backend |

**Eje 2 — cómo se confirmó (metadato, no determina ruteo):** archivo (análisis estático) / DDL (derivado del esquema) / log (evidencia de ejecución real) / contraste (confirmado por una segunda derivación independiente). Cuanto más fuerte la confirmación, menos discutible el hallazgo — pero no cambia a dónde va.

**Proceso de intake:** cada finding nuevo de un test se tagea con el Eje 1 al momento de registrarlo (antes de escribir nada en el código). El tag determina la fila/documento destino mecánicamente:
- **S** → celda de F2/F3 en la tabla de Track F, este archivo.
- **G-step** → hallazgo en `01-hallazgos.md`, referenciado desde `dimension_step_policy.py`; si cambia el contrato de `derive_dimension_step_type` es candidato a decisión (D-numerada) en `02-decisiones.md`, no una fase de Track F.
- **D-dialecto / D-integridad** → tabla de F4 abajo (ampliada, ver nota en la fila de F4) o "Abiertos" en `02-decisiones.md` si necesita decisión de negocio primero.
- **D-ddl-constraint / Env** → hallazgo nuevo en `01-hallazgos.md`, sin asignar a ninguna fase existente hasta que alguien decida dónde vive esa superficie (DDL) o ese canal (prompt).

No se crea un H-number por cada regla — solo para información genuinamente nueva (un gap de código, un comportamiento de entorno no documentado). Reglas que ya caen dentro de un mecanismo existente (ej. R5-a, que es exactamente V2) se anotan como referencia cruzada, no como hallazgo nuevo.

---

## Orden macro

```
D3 ✓ · D6/D6-bis ✓ · D7 ✓ (ubicación entregada) · H16 ✓ acotado · D14 ✓ (rompe circularidad F2/F3)
                                        │
Track A: pospuesta (A0 no arranca) ────┤── PASO 1 grande (borde tipado completo, H2) — no bloquea Track F (D14)
                                        │
Track F: F1 ✓ (2026-07-22)
         │
         │  C.2 ✓ (2026-07-22) — nada que eliminar, handoff ya cumplía D6-bis
         v
    F1.5 — cerrar H4 + H11 + H6 (alcance chico de D14, no el borde grande) — pendiente, código no escrito
         v
    F2 ✓ (diseño, 2026-07-22) — algoritmo + validado contra err1.ktr/err2.ktr (H21) + archivos a tocar
         v
    F2.5 — soporte JobEntryJob (H7) — pendiente, código no escrito
         v
    F3 — implementación (corte + jerarquía de jobs + V1/V2/V3) — requiere F1.5 y F2.5 en código, más aprobación del diseño de F2, más D16 (ampliar dim_contracts, o riesgo aceptado)
```

D3, D6, D6-bis, D7, F1+C.2, D14 y ahora F2 (diseño) dejaron de bloquear nada — ver `02-decisiones.md`. **F1.5 y F2.5 siguen sin implementarse en código** — F2 pudo diseñarse sin ellas porque es fase de diseño, no de implementación, pero F3 sí las necesita terminadas antes de arrancar. Ninguna fase escribe código todavía sin aprobación explícita del usuario sobre el diseño de F2.

---

## Fases

### Verificaciones humanas previas — todas resueltas 2026-07-22

1. ~~Confirmar que nadie del equipo tenga trabajo apoyado en ETLs guardados.~~ **Verificado: nadie.** D3 confirmado sin condición.
2. ~~Re-verificar D6 en frío.~~ **Hecho** — D6/D6-bis resueltas en `02-decisiones.md`, backend determinístico, solo corrección estructural.
3. ~~Recolectar los casos reales donde forzar 2 archivos produjo error.~~ **Ubicación entregada:** `C:\Users\05147\OneDrive\Escritorio\Test_Asistente_ETL\Simplificado\Sol\02\Errores\` (`err1.ktr`, `err2.ktr`). Insumo listo para F2/F3 y F4 — el contenido todavía no fue analizado, eso es trabajo de esas fases, no de esta sesión.

Ninguna verificación humana previa sigue bloqueando el arranque de Track F.

---

### Track A — Auditoría de arquitectura

**Actualizado 2026-07-22: A0 se pospone, no corre en paralelo con Track F.** El argumento más fuerte para correrla ahora era que produce H1 como subproducto — y H1 quedó desinflado (ver `01-hallazgos.md`). El costo de releer un inventario completo del backend que además va a quedar desactualizado en todo lo que Track F toque no se justifica todavía. Se retoma cuando Track F esté suficientemente asentado.

| Fase | Entrada | Salida | Modifica código | Depende de |
|---|---|---|---|---|
| A0 — Fase 0 (inventario) | `arquitectura-objetivo.md` reescrito (ver nota abajo) | `docs/auditoria/00-inventario.md` | No | Pospuesta — no arranca junto con Track F |
| A0.5 — Fase 0.5 (censo fallos silenciosos) | A0 | `docs/auditoria/00b-fallos-silenciosos.md` | No | A0 |
| A1 — Fase 1 (doc vs. realidad) | A0 | `docs/auditoria/01-doc-vs-real.md` | No | A0. **Solapa con esta sesión de consolidación** — ver nota abajo |
| A2 — Fase 2 (cumplimiento por capas) | A0 | `docs/auditoria/02-cumplimiento.md` | No | A0 |
| A3 — Fase 3 (bordes de entrada y modelo de dominio) | A0, A2, A0.5 | `docs/auditoria/03-bordes.md` | No | A0.5, A2. **Parte A ya diagnosticada** por H2-H4, H6, H11 — no repetir, sí completar Partes B/C/D (otros bordes: filas de DB, uploads, config de usuario, env vars — ninguno cubierto todavía por ningún material) |
| A4 — Fase 4 (acoplamiento) | A2, A3 | `docs/auditoria/04-acoplamiento.md` | No | A2, A3. Cubre H5 (acoplamiento temporal del linaje) formalmente |
| A5 — Fase 5 (plan de remediación) | Todos los reportes previos | `docs/auditoria/05-plan.md` | No | A0-A4. **PASO 1 = el borde**, ya decidido por `00-plan-auditoria.md`. Ver "Ajustes por D1/D2" abajo — el formato de verificación de esta fase necesita modificarse antes de correrla |
| A6 — Fase 6 (consolidar doctrina) | Plan aprobado | `CLAUDE.md` + `docs/arquitectura-objetivo.md` actualizados | Solo docs | A5 aprobado |
| A7 — Fase 7 (ejecución) | A5 | Un PASO del plan por sesión | Sí | A6 (doctrina consolidada primero) |

**Nota sobre A1:** esta sesión de consolidación ya cubre una porción de lo que A1 pediría (contrastar `CLAUDE.md` contra el estado real del código) para el recorte de fragmentación específicamente. A1 sigue teniendo valor porque su alcance es el backend completo, no solo el flujo de fragmentación — pero al correrla, señalar que `docs/refactor/00-objetivo.md` y `01-hallazgos.md` ya existen para evitar duplicar diagnóstico.

**Nota sobre `docs/arquitectura-objetivo.md` — hecho 2026-07-22:** escrita al repo con una sección nueva ("Ejemplo aplicado — el motor de fragmentación") que incorpora D6 y D6-bis, situando la fragmentación en el modelo de capas sin duplicar el contenido de las decisiones. Sigue sin commitear a git — ver nota de cierre de esta sesión. A0 sigue pospuesta igual: que la doctrina esté escrita no obliga a correr el inventario todavía.

---

### Track F — Motor de fragmentación

| Fase | Objetivo | Depende de | Hallazgos que toca |
|---|---|---|---|
| F1 — Investigar (Fase 1 del handoff) | Responder las 5 preguntas ya escritas: estructura de steps pre-XML, matriz tipo→{lee,escribe}, soporte de `JobEntryJob`, orden de `_build_job_plan`, costo de construir la matriz sin re-parsear XML | Ninguna estructural. **H7 ya adelanta la pregunta 3** (hoy no hay `JobEntryJob` — falta el costo de agregarlo). **La pregunta 4 (orden de `_build_job_plan`) queda parcialmente pre-respondida por D6**: la función existe y ya orquesta el KJB en Python puro (`etl_generator.py:224`) — falta confirmar si ordena por grafo de FK o por orden fijo, eso sigue abierto | H1, H7 — **hecho 2026-07-22, ver reporte abajo y H1/H7/H19/H20 en `01-hallazgos.md`** |
| C.2 (gate, no numerada F) — Contrastar reglas de corte del handoff contra D6-bis | Releer las reglas de fragmentación ya escritas en `handoff_fragmentacion_y_errores.md` y eliminar las que respondan a legibilidad/tamaño en vez de corrección estructural | Ninguna — barato. **Bloquea F2**: sin esto el pase nace contradiciendo D6-bis | — **hecho 2026-07-22: nada que eliminar, ver reporte abajo y `02-decisiones.md`** |

---

### Reporte F1 (2026-07-22)

**Q1 — ¿Cada step expone tabla + modo R/W de forma confiable antes del XML?** No. `ETL_OUTPUT_SCHEMA.ktr.steps[*]` (`etl_output.py:90-117`) solo tiene `name`/`type`/`config` (config como string JSON, forma libre por tipo — `etl_output.py:101-104`). `data_1["ktr"]`/`data_2["ktr"]` (`etl_generator.py:433-434`) traen esa misma forma. Tabla + modo hay que derivarlos, y hoy existen dos extractores parciales y divergentes: `contracts.STEP_CONTRACTS.key_aliases` (`contracts.py:318-360`, resuelve alias pero no calcula modo) y `lineage_builder._extract_table`/`_TABLE_FIELD_TYPES` (`lineage_builder.py:20-27,51-59`, ignora los alias de `contracts.py` — H4 — y no cubre `DBLookup` — H11). El motor de corte no puede apoyarse en ninguno de los dos tal cual están; necesita la matriz de H19 centralizada bajo D8 antes de F2.

**Q2 — mapa tipo_step → {R,W}:** construido, ver **H19** en `01-hallazgos.md`. Hallazgo central: `DimensionLookup` y `CombinationLookup` son R+W **siempre**, no condicionalmente — `DimensionLookup` porque el builder hardcodea `<update>Y</update>` (`ktr_builder/steps/lookups.py:47`), `CombinationLookup` porque es la semántica nativa del step (sin flag para desactivar el insert). `DBLookup` es R puro (nunca escribe). `ExecSQL` no es clasificable sin parsear su SQL — el corte debe fallar fuerte ante él (D5), no asumir.

**Q3 — ¿`build_kjb_xml` soporta `JobEntryJob`?** No — cero ocurrencias, confirmado (H7, ya resuelto en sesión previa). Qué haría falta: discriminador en `JobEntry` (`job_schemas.py:42-46`, hoy sin campo de tipo), una función `_job_entry()` nueva con el XML de `JobEntryJob` (tags distintos a `_trans_entry`, no un swap de string — `job_analyzer.py:359-388`), branch en el loop de `build_kjb_xml` (`job_analyzer.py:272-274`), y un call site nuevo para `job_master.kjb`. Detalle completo en H7 actualizado.

**Q4 — ¿`_build_job_plan` ordena por FK o fijo?** Fijo. `etl_generator.py:224-246` arma siempre 2 `JobEntry` (`:240-244`); el docstring dice explícitamente que el orden nunca fue ambiguo con 2 archivos (`:225-229`). No hay ningún ordenamiento por grafo de FK en el código hoy — bajo N>1 por etapa, ese ordenamiento (dims antes que hechos, per `00-objetivo.md`) es lógica nueva a escribir, no una extensión de algo existente.

**Q5 — ¿matriz sin re-parsear XML?** Sí. `build_lineage(ktr_data)` (`lineage_builder.py:87-132`) ya opera sobre el dict pre-XML — mismo dato que cita D6 evidencia #3. El fallback XML (`_parse_ktr_xml`) solo aplica al flujo `CreateJob` (`.ktr` de autoría externa), no al de generación.

**Recomendación de dónde insertar el corte:** entre `repair_integrity_gaps` y `build_ktr()` (`etl_generator.py:801-804` → `:438-460`) — mismo punto del pipeline que `repair_ktr_steps`/`repair_integrity_gaps`/`enforce_dimension_step_policy` (D6 evidencia #4). Detalle en **H20**.

**Nota — el "2" está hardcodeado en 3 puntos, no 1** (evidencia en H1 actualizado): dos llamadas al LLM por `mode` (`etl_generator.py:782-786`, duplicado en `:931-935`) + `_build_job_plan` (`:240-244`). F2/F3 reemplazan estructura, no ajustan un número.

---

### Reporte F2 (2026-07-22)

**Nota de estado antes de empezar:** la fila de F2 en la tabla de abajo dice "F1.5 hecho, C.2 hecho" en su columna "Depende de". Es inexacto — F1.5 (centralizar H4+H11+H6) **no está implementado en código todavía**, solo diseñado por D14. Lo que sí está hecho es C.2 y el reporte de F1. F2 es una fase de **diseño**, no de implementación (el handoff original: "reportá el plan, no implementes") — el diseño de abajo referencia dónde F1.5 tiene que aterrizar sin asumir que ya aterrizó. F3 sí necesita F1.5 (y F2.5) terminadas en código antes de arrancar.

**Actualización (2026-07-22, `bitacora_etl_ventas.md`/`extracto_corte_F2.md`):** F3 tiene un tercer prerrequisito además de F1.5/F2.5, externo a Track F — **ver D16 en `02-decisiones.md`**. C1-bis (validado contra `err1.ktr`/`err2.ktr`, H21) se preguntó si era un fantasma (artefacto de step mal elegido, no señal estructural real); verificado contra código: **no lo es, todavía** — `dim_contracts`/`dimension_step_policy` no deriva ningún step de solo lectura para el lado del hecho (H22), así que un lookup de FK sigue siendo R+W por construcción y C1-bis sigue disparando correctamente sobre ese patrón. El fix real vive en el eje `dim_contracts` (D11), no en el algoritmo de corte. F3 espera esa decisión (D16) o arranca con el riesgo documentado (D15) — a definir por el usuario, no algo que este reporte resuelva.

**Insumo obligatorio (D7):** contenido de `err1.ktr`/`err2.ktr` analizado — ver **H21** en `01-hallazgos.md`. Resumen: un solo `.ktr` de STG→DWH con (a) `dim_producto` escrita+leída por dos `DimensionLookup` distintos (`Cargar Dim Producto`, rama muerta sin hop de salida; `Lookup Dim Producto`, en la rama de hechos) sin hop entre ambos — carrera + doble escritor reales (E4/E5); (b) `dim_tiempo` leída por `Lookup Dim Tiempo` (`DBLookup`) sin ningún productor en el archivo — dimensión nunca cargada (E6).

#### Algoritmo

**1. Matriz R/W por etapa** (sobre `STEP_CONTRACTS` extendido en F1.5 + la tabla de H19): para cada step, resolver `{tabla: {"read"|"write"}}`. Steps sin tabla (StreamLookup, transformaciones puras) no aportan al mapa. `ExecSQL` (SQL arbitrario, no clasificable — Q2 de F1) queda **fuera** de la matriz — no participa del corte, y dispara una notificación D15 ("`ExecSQL` en step 'X' — SQL no analizado, verificar manualmente contra el resto del corte") en vez de asumir modo. Esto es una decisión de alcance de F2 que corresponde confirmar antes de F3 la implemente.

**2. Dos disparadores de corte, no uno** — el handoff solo escribió C1 (W+R misma tabla). El corpus real (H21) muestra que **doble escritor sin lectura intermedia** es un caso separado y real (E4 de `00-objetivo.md`, segunda viñeta), así que el diseño agrega **C1-bis**:
   - **C1** (ya en el handoff): tabla T escrita por el step A y leída por el step B, A≠B, en la misma etapa → corte.
   - **C1-bis** (nuevo, motivado por H21): tabla T escrita por dos steps distintos A≠B en la misma etapa (sin necesidad de que ninguno la lea) → corte. Caso real: si `dim_tiempo` tuviera además un segundo `CombinationLookup` cargándola en otra rama, sería este caso; en `err1`/`err2` el disparador real es C1 (dos `DimensionLookup`, cada uno R+W, cuentan como escritor Y lector de la tabla). **Reconciliado (2026-07-22, `bitacora_etl_ventas.md`/`extracto_corte_F2.md`):** se preguntó si C1-bis era un fantasma (síntoma de step mal elegido en vez de señal real). No lo es todavía — ver H22/D16: hasta que `dim_contracts` derive un step de solo lectura para el lado del hecho, un lookup de FK sigue siendo R+W por construcción y C1/C1-bis siguen siendo la señal correcta sobre ese patrón, no un falso positivo del algoritmo.

**3. Componentes:** partir del grafo de hops (componentes conexos, ignorando tablas). Para cada tabla que dispara C1/C1-bis:
   - Si el step escritor y el step lector/segundo-escritor ya caen en componentes de hop **distintos** (caso `err1`/`err2`: `Cargar Dim Producto` es su propio componente, `Lookup Dim Producto` está en el componente de hechos) → no hace falta partir nada más, alcanza con **ordenar** los dos componentes.
   - Si caen en el **mismo** componente, hay dos sub-casos, no uno (refinado 2026-07-22 con `bitacora_etl_ventas.md`, sección 3 del `extracto_corte_F2.md` — ver H21):
     - **Excepción self-lookup/insert-new-only:** si todos los steps que LEEN T tienen camino de hops hacia todos los steps que ESCRIBEN T dentro del componente (lectura estrictamente aguas arriba de la escritura — el idioma "chequear si existe → filtrar → insertar"), **no dispara corte.** Es un patrón seguro y a propósito (Lectura 3 de la bitácora: `DBLookup/StreamLookup existe? → FilterRows → Table Output`), reforzado con `UNIQUE` sobre la clave natural (R7/L2-E05, `02-decisiones.md` C.5). Aplicar C1 tal cual sobre este patrón sobre-corta.
     - **Cualquier otra relación dentro del mismo componente** (escritura aguas arriba de una lectura posterior, o sin relación de hops determinable) → caso genuinamente difícil, **sin evidencia en el corpus actual** (ni `err1`/`err2` ni la bitácora lo ejercitan): el step "después" de un corte hipotético perdería el stream en memoria (los hops no cruzan archivos) y tendría que reconstruir lo que necesita solo desde BD. **Alcance propuesto para F3: implementar el caso "componentes ya separados" + la excepción self-lookup (ambos evidenciados); este sub-caso se detecta y se notifica (D15) como no soportado automáticamente en la primera vuelta, en vez de generar un corte que probablemente no compile en Kettle.** Confirmar este recorte antes de F3.
   - Componentes sin ninguna tabla-disparador no se tocan (D6-bis: sin señal, no hay corte) — se agrupan todos juntos en un único archivo por etapa, salvo que una relación de tabla los fuerce a separarse.

**4. Orden entre componentes:** grafo dirigido componente-a-componente, una arista por cada relación de tabla-disparador (escritor → lector/otro-escritor). Orden topológico de ese grafo = orden de los KTR dentro de la etapa (dims antes que hechos, per `00-objetivo.md`). Si el grafo tiene ciclo (tabla A escrita por comp. 1 y leída por comp. 2, y tabla B al revés) → caso patológico genuino, cae bajo D15 (notificar, no bloquear) — no es una rama del algoritmo de corte en sí.

**5. V2 (lookup sin productor, caso `dim_tiempo`):** no es señal de corte (D15/03-plan.md ya lo fija). Se detecta en la misma pasada que arma la matriz R/W (una tabla leída que nunca aparece como escrita por ningún step de la etapa) y se emite como notificación accionable: qué tabla, qué step la consulta, que no tiene productor.

#### Validación contra `err1.ktr`/`err2.ktr` (H21)

Aplicando el algoritmo: `dim_producto` dispara C1 (escrita+leída por `Cargar Dim Producto` y `Lookup Dim Producto`, componentes de hop ya distintos) → 2 KTR:
- `KTR_A`: `Leer Staging Productos`, `Cargar Dim Producto`.
- `KTR_B`: `Leer Staging Ventas`, `Filtrar Ventas Anuladas`, `Descartar Anuladas`, `Castear Campos Ventas`, `Calcular Importe`, `Lookup Dim Producto`, `Lookup Dim Tiempo`, `Cargar Fact Venta`.

Orden: `KTR_A` antes que `KTR_B` (escritor de `dim_producto` antes que su lector). `dim_tiempo` → notificación V2/D15 sobre `Lookup Dim Tiempo`, sin afectar el corte. Coincide con la partición que un modelador humano haría a mano — es la prueba de humo que pide D7.

**Segunda validación independiente (2026-07-22, `bitacora_etl_ventas.md`/R3):** dos soluciones que no se vieron entre sí (una SQL-colapsada, otra steps-Kettle con `StreamLookup`), partiendo del mismo `.ktr` de origen (`dim_producto` + `fact_venta`), convergieron en la misma partición: dimensión en KTR separada, secuenciada antes del hecho vía KJB, KTR de Origen→Staging intacto. Refuerza la validación de `err1`/`err2` con un caso corrido en verde contra Postgres real, no solo análisis estático — ver R3 en la tabla de intake de `01-hallazgos.md`.

#### Archivos a tocar (para F3, no se tocan en F2)

- **Nuevo** `backend/app/services/ktr_builder/fragmentation.py` (o `cut.py`): `build_rw_matrix()`, `compute_cut()` (componentes + notificaciones D15), `order_components()` (orden topológico). Consume `STEP_CONTRACTS` extendido (F1.5), no reimplementa resolución de alias/tabla.
- `backend/app/services/etl_generator.py` — punto de inserción entre `repair_integrity_gaps` y `build_ktr()` (H20, `:801-804`→`:438-460`); `_build_job_plan` (`:224-246`) generalizado de 2 `JobEntry` fijos a N por etapa.
- `backend/app/services/lineage_builder.py` — `stitch_lineage` (`:138-213`) hoy cose exactamente 2 KTR (`ktr_data_1`, `ktr_data_2`) con un solo prefijo `K2::`; bajo N archivos por etapa necesita generalizarse a M archivos con prefijos por índice, no por "K2".
- `backend/app/services/job_analyzer.py` — depende de F2.5 (H7) para la jerarquía de 3 niveles; el `job_origen_stg.kjb`/`job_stg_dwh.kjb` por etapa usa la misma `build_kjb_xml()` ya existente (solo generalizada a N entries en vez de 2), el `job_master.kjb` sí necesita `JobEntryJob` (F2.5).
- `backend/app/services/ktr_xml_validator.py` / `build.py:401` — conversión del `raise KtrXmlValidationError` a anota-y-notifica (D15), scope de F3 ya anotado en la fila de F3.

**Nota:** no se escribió código en esta sesión — este es el reporte de diseño que pide la Fase 2 del handoff. Pará acá y esperá aprobación antes de F3/F2.5.

| F1.5 — Centralizar dominio mínimo para el corte | Cerrar H4 (alias vía `contracts.STEP_CONTRACTS.key_aliases`, incluye el `or` inline de `dimension_step_policy.py:107`), H11 (`DBLookup` en la matriz R/W) y H6 (fail-fast en `parse_cfg`, D5) | F1 aprobada. Independiente del borde tipado grande — ver D14 en `02-decisiones.md` | H4, H6, H11 |
| F2 — Diseñar el corte (Fase 2 del handoff) | **Corte constructivo, no compuerta (corrección 2026-07-22, ver D15).** F2 diseña dónde separar, no un fallback para cuando falla. Reglas: (a) aceptar 1 KTR por etapa si cumple el proceso, sin dudas; (b) separar en N KTR + KJB dentro de una etapa solo donde la señal estructural lo pida — V1 (tabla W+R por steps distintos) y V3 (doble escritor), consistente con D6-bis, sin umbral de tamaño; (c) KJB maestro orquesta por etapa — primero `ktr_Org_Stg`, después `kjb_Stg_Dwh` (jerarquía de 3 niveles, H7/F2.5); (d) la señal de corte se deriva de casos reales (`err1.ktr`/`err2.ktr`, D7), no de una lista imaginada. **V1 y V3 guían la separación; V3 no confundir con V2** (todo lookup tiene productor) — V2 es un chequeo de integridad del ETL, no un criterio de corte: un lookup sin productor es un error a notificar (D15), no una decisión de dónde separar. El caso patológico (ciclo real, input malformado) no lo maneja el corte — cae en D15 | **Diseño hecho 2026-07-22** — ver reporte arriba (algoritmo, validación contra H21, archivos a tocar). F1.5 **no** está hecho todavía (nota de estado al inicio del reporte) — F2 es diseño, no requiere F1.5 en código; **F3 sí la requiere**. C.2 hecho, fixtures ya ubicadas (D7: `err1.ktr`/`err2.ktr`) | H1, H8, H21 |
| F2.5 — Soporte `JobEntryJob` | Cerrar H7: discriminador de tipo en `JobEntry` (`job_schemas.py:42-46`), función `_job_entry()` nueva junto a `_trans_entry()` (`job_analyzer.py:359-388`), branch en el loop de `build_kjb_xml` (`job_analyzer.py:272-274`), call site para `job_master.kjb` (detalle completo en H7) | F1 aprobada. Independiente de F1.5/F2 — puede correr en paralelo con ambas | H7 |
| F3 — Implementar el corte (Fase 3 del handoff) | Corte + jerarquía de jobs (`job_origen_stg.kjb`, `job_stg_dwh.kjb`, `job_master.kjb`), construidos según el diseño de F2 (V1/V3 ya satisfechas por construcción, no se re-chequean). **Solo V2 extiende infraestructura de validación existente** (`ktr_xml_validator.py`/`error_catalog_checks.py`, H8) — como chequeo de integridad, no de corte — y anota-y-notifica en vez de abortar. **Incluye convertir `ktr_xml_validator.py:100-117` (`raise KtrXmlValidationError`, hoy wireado y fail-hard en `build.py:401`) al patrón anota-y-notifica de D15** | **F2 aprobado, F2.5 hecho** | H1, H8 |
| F4 — Track de errores (6 puntos del handoff §2 **+ intake de tests, ampliado 2026-07-22**) | Decidir estrategia de fix (derivación determinista desde `dim_contracts` vs. parche de prompt — evidencia apunta a lo primero), resolver E3, key vacía, E14, confirmar E1/E2, validador de contrato staging→DWH. **Ampliado:** los 6 puntos originales del handoff ya no son el único intake de F4 — toda regla tageada D-dialecto/D-integridad por el mecanismo de "Intake de hallazgos de tests" (arriba) también cae acá. De `bitacora_etl_ventas.md`: R4/R6/R10/R12 (dialecto, cruza con D12/C.1), R5-b/R11 (huérfanos/FK no resuelta, bloqueado por C.6 en `02-decisiones.md`), R8 (clave natural como value en `Insert/Update` de dimensión, mientras el LLM arme ese config — extiende H16) | Independiente de F1-F3 — son fixes puntuales sobre el generador ya existente, pueden correr en paralelo. `dim_contracts` (149b836) confirmado como precedente compatible, no como obstáculo (D11). **No** absorbe G-step (R1/R2/R8-si-D16-camino-1) ni Env (R9) — esos van al eje `dim_contracts` o a `system_etl.txt`, fuera de F4 | H9, H10, H14, H16, H23 |
| F5 — Limpieza de bajo costo, sin dependencias | Dedup de los 4 `_parse_cfg`/`_parse_config` restantes (H3), fix docstring `etl_output.py` (H12), `s["name"]` sin `.get()` en `validate.py` | Ninguna — "cero riesgo" según el propio material de origen | H3, H12 |

**Nota sobre H16 (acotada 2026-07-22):** la base sí autogenera `sk_producto` (secuencia vía `DEFAULT`), pero solo si el `INSERT` omite la columna — `_step_InsertUpdate` no filtra claves técnicas del mapeo. Confirmar contra `err1.ktr`/`err2.ktr` (D7) si el caso real llegó a mapear algo a `sk_producto` es trabajo de F1/F4, no un bloqueo aparte. Ver H16 en `01-hallazgos.md`.

---

## Ajustes por D1/D2 al material recibido — resueltos 2026-07-22

El material de Track A fue escrito antes de que D1 y D2 quedaran fijadas. Dos puntos del prompt de **Fase 5 (`fase-5-plan-remediacion.md`)** perdían sentido tal como estaban escritos — ya no son candidatos especulativos, se resolvieron con D9 y D10 en `02-decisiones.md`:

**1. El criterio de verificación "comparación de artefacto generado antes y después" → resuelto por D9.**
D2 mata la política de preservar comportamiento, no la necesidad de verificar. Reemplazo fijado: **contra qué se compara es el delta declarado, no el output viejo** — se enumera qué va a cambiar antes de correr el paso, y cero deltas sin explicar es el criterio de aprobación. Herramienta: normalización canónica (aplanar todos los `.ktr` a una secuencia de steps ignorando fronteras de archivo) para generar la lista de deltas de forma confiable. D9 también separa cuatro clases de cambio (costura del corte / funcionalidad nueva / rediseño / corrección) que un diff ingenuo mezclaba sin distinguir.

**2. La sección "Compatibilidad durante la transición" → eliminada por D10.**
D3 quedó verificado (nadie usa datos guardados), así que el requisito de compatibilidad no existe. Sin período de convivencia entre parseo viejo y nuevo — el mecanismo de vuelta atrás es revertir el commit.

**3. La tensión con la Restricción 1 de Fase 5 ("cada paso deja el sistema funcionando... mergeable solo") → resuelta, se parte en dos lecturas (D9).**
Lectura A ("el artefacto sigue produciendo lo mismo"): eliminada, es lo que D2 dice que no se protege. Lectura B ("el repo queda verde, cada paso es revertible por separado"): se mantiene — es regla de tamaño de paso, no de preservación de comportamiento. No hay contradicción real una vez separadas.

Ninguna otra fase de Track A o Track F pierde sentido bajo D1/D2 — el resto (inventario, censo de fallos silenciosos, cumplimiento por capas, acoplamiento, doctrina) es diagnóstico neutral a la decisión de cuántos archivos se generan.

## Requisito transversal — D13, definición de terminado

Toda fase de Track A y de Track F, sin excepción, cierra solo con: (1) dos tests — uno de lo que la fase trabajó, uno del contrato que expone hacia la fase siguiente; (2) el registro de deltas de esa fase (D9), como warnings del pase, cubriendo tanto lo determinístico del backend como lo que produce el LLM; (3) `CLAUDE.md` + archivo de progreso actualizados. Ver D13 en `02-decisiones.md` para el detalle completo y el porqué.

---

## Paralelizable — actualizado 2026-07-22

- **Track A está pospuesto completo**, incluido A0 — no corre en paralelo con Track F por ahora (ver nota en la tabla de Track A).
- F1 (investigar) y C.2 (limpiar reglas de corte contra D6-bis) pueden arrancar ya, en paralelo entre sí.
- **F1.5 (H4+H11+H6) y F2.5 (H7) pueden arrancar ya** — dependen solo de F1, ya hecho, y son independientes entre sí (D14).
- F4 (track de errores) es independiente de todo lo demás y puede hacerse en cualquier momento.
- **F5 (limpieza) no es independiente de F1.5**: ambas tocan `dimension_step_policy.py` (F5 línea 53, F1.5 línea 107) y `lineage_builder.py` (F5 línea 41, F1.5 líneas 20-59). Sin conflicto lógico — funciones distintas — pero coordinar el orden (sugerido: F5 primero, es mecánico y "cero riesgo"; F1.5 después, sobre el archivo ya deduplicado) evita un merge innecesario.
- H16 verificado contra la base (sequence confirma) — lo que queda es confirmar contenido de `err1.ktr`/`err2.ktr`, cae dentro de F1/F4.
- F2 está bloqueado por F1.5 + C.2 (ya no por sí misma — ver D14). F3 está bloqueado por F2 aprobado + F2.5 hecho (ya no por sí misma).
- Reescribir `docs/arquitectura-objetivo.md` (incorporando D6/D6-bis) puede hacerse ya, aunque A0 esté pospuesta — es trabajo de documentación, no de código.

## Backlog — fuera de alcance de este plan, con sesión propia

Ítems confirmados como reales pero explícitamente no planificados todavía (ver `02-decisiones.md`, sección "Abiertos"):

- **C.1** — plan de soporte multi-motor SQL (Postgres queda de default por D12, pero el resto no tiene plan).
- **C.4** — auditoría retroactiva de cambios no declarados en commits pasados de generación de KTR. Falta acotar hasta qué commit.

## Qué queda fuera de este plan

Todo lo listado en "Deliberadamente no decidido" de `02-decisiones.md`: si el borde tipado *grande* (H2, `string → object`, tipo validado por construcción) va como parte de A7-PASO1 o antes de eso, el comportamiento de `build-from-raw` ante raw incompleto, y el plan de soporte multi-motor SQL (C.1). El alcance chico que Track F sí necesita (H4, H11, H6) ya no está acá — quedó resuelto por D14 y asignado a F1.5/F2.5. Este plan no fuerza ninguna de las decisiones grandes que siguen abiertas.
