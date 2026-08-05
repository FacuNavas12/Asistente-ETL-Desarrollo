# Fragmentación — cómo el backend decide en cuántos .ktr materializa una etapa

**Referencia, no investigación.** Destila el diseño e implementación del motor de corte (`backend/app/services/ktr_builder/fragmentation.py`). Verificado contra código 2026-08-05. Cuando este archivo y el código diverjan, gana el código.

## Por qué existe

El LLM propone el ETL lógico (una fase: Origen→STG o STG→DWH). El backend decide, de forma determinística, en cuántos archivos `.ktr` físicos se materializa esa fase — nunca el LLM. Poner esa decisión en el modelo introduce no-determinismo justo en la capa que existe para eliminarlo: el flujo forzado a 2 KTR fijos era la causa raíz de una clase de errores reales (carreras lectura/escritura sobre la misma tabla, doble escritor, dimensiones nunca cargadas).

**Principio rector — la fragmentación es un mecanismo de corrección, no de legibilidad.** Corta únicamente por señal estructural: una tabla escrita y leída por steps distintos en la misma etapa, o escrita por dos steps distintos. Un `.ktr` largo pero estructuralmente correcto no se parte — no hay umbral de tamaño ni criterio de "esto se ve muy largo". Un componente sin ninguna tabla-disparador no se toca: todos sus steps quedan juntos en el mismo archivo.

Consecuencia práctica: crear una tabla nueva, agregar una rama de validación, o reescribir SQL nunca son "fragmentación" — ningún análisis de grafo produce eso. Las reglas de corte se derivan de casos reales de falla (`err1.ktr`/`err2.ktr`: un KTR único con `dim_producto` escrita por un `DimensionLookup` en una rama muerta y leída por otro en la rama de hechos, sin hop entre ambos — carrera real), no de una lista abstracta de buenas prácticas de Pentaho.

El conocimiento de qué tabla toca cada step, con qué alias, y si lee o escribe, vive en un único lugar (`STEP_CONTRACTS`) — el motor de corte lo consume, no lo reimplementa.

## El algoritmo

**1. Matriz R/W por etapa** (`build_rw_matrix`): para cada step, resolver `{(connection, table): "read"|"write"}`. La clave es `(connection, table)` normalizada, no solo el nombre de tabla — evita que dos conexiones lógicas distintas apuntando al mismo nombre físico se traten como la misma entrada, y cierra la asimetría de namespace entre variantes con/sin schema.

Resolución de tabla por step:
- `TableInput`/`TableOutput`/`DimensionLookup`/`CombinationLookup`/etc. — vía sus alias declarados en `STEP_CONTRACTS`.
- `DimensionLookup` y `CombinationLookup` son **R+W siempre**, no condicionalmente: `DimensionLookup` porque el builder hardcodea `<update>Y</update>`; `CombinationLookup` porque es la semántica nativa del step (sin flag para desactivarlo). Un step `RW` cuenta como entrada en `readers` **y** en `writers` — así una tabla cuyo único step visible es RW no queda inmune al chequeo de carrera.
- `DBLookup` es R puro (nunca escribe).
- `StreamLookup` hereda la tabla del `TableInput` que lo alimenta (antes invisible al corte).
- `TableInput`/`ExecSQL` resuelven su tabla parseando el SQL real (sqlglot) en vez de por coincidencia de contenido — `ExecSQL` se clasifica por operación real (`TRUNCATE`/`INSERT`/`UPDATE`/`DELETE` → escritura; `CREATE` → sin rol, estructural). SQL no parseable → `Finding(severity="error")`, nunca aborta.
- Steps sin tabla (transformaciones puras) no aportan al mapa.

**2. Dos disparadores de corte:**
- **C1** — tabla T escrita por el step A y leída por el step B, A≠B, en la misma etapa.
- **C1-bis** — tabla T escrita por dos steps distintos A≠B en la misma etapa (sin que ninguno la lea).

**3. Componentes conexos:** se parte el grafo de hops en componentes (ignorando tablas). Para cada tabla que dispara C1/C1-bis:
- Si escritor y lector/segundo-escritor ya caen en componentes de hop **distintos** → alcanza con ordenar los dos componentes, no hace falta partir nada más.
- Si caen en el **mismo** componente:
  - **Excepción self-lookup / insert-new-only:** si el único writer tiene TODOS sus readers de esa tabla como ancestros dirigidos suyos (patrón "¿existe? → filtrar → insertar", reforzado con `UNIQUE` sobre la clave natural) — el componente **se parte igual**: el writer (+ descendientes) pasa a un grupo posterior, el resto a uno anterior. El hop que el corte deja colgando entre ambos se materializa (ver punto 5).
  - **Cualquier otra relación dentro del mismo componente** (más de un writer — C1-bis real; o un reader que no es ancestro del writer — orden ambiguo) → no se parte, `Finding(severity="error")` notificando el conflicto para revisión manual. No hay evidencia en el corpus real de que este caso general necesite resolverse automáticamente.
- Componentes sin ninguna tabla-disparador no se tocan (principio rector de arriba).

**4. Orden entre componentes:** grafo dirigido componente-a-componente, una arista por cada relación de tabla-disparador (escritor → lector/otro-escritor). Orden topológico de ese grafo = orden de los KTR dentro de la etapa (dimensiones antes que hechos). Ciclo → caso patológico, se notifica, no se bloquea.

**5. Lookup sin productor** (ej. `dim_tiempo` consultada por `DBLookup` sin que ningún step de la etapa la cargue): no es señal de corte — se detecta en la misma pasada que arma la matriz R/W (tabla leída que nunca aparece escrita) y se emite como notificación accionable (qué tabla, qué step la consulta, que no tiene productor en esta etapa). Puede cargarse legítimamente en otra etapa/archivo.

**6. Materialización de hops que cruzan grupos:** cuando el corte del punto 3 separa un componente (caso self-lookup), el hop entre el grupo emisor y el receptor no puede seguir siendo un hop de Kettle normal — ya no están en el mismo `.ktr`. Se descartó el mecanismo nativo de Kettle (`Copy rows to result`/`Get rows from result`): el `Result` que viaja por el `.kjb` tiene una sola lista de filas sin nombre ni canal, soporta como máximo un stream cruzado a la vez, y el corte puede producir varios. Se eligió en cambio una **tabla de staging efímera**: un `Table output` (`truncate=True`) en el grupo emisor + un `Table input` (`SELECT *`) en el grupo receptor, nombrada `etl_corte_N` y deliberadamente fuera de los prefijos de staging/DWH del contrato de usuario (es plomería interna del motor de corte, no la capa de staging que el usuario ve). La tabla entra sola a la matriz R/W, y el orden queda garantizado por el chequeo de etapa del punto 7.

**7. Chequeo a nivel de etapa** (`validate_stage_contract`, corre después de partir en sub-archivos): ningún fragmento posterior escribe una tabla que un fragmento **anterior** ya necesitaba leer — matriz R/W por fragmento, primer escritor de cada `(connection, table)`, error si un lector de un fragmento anterior depende de un escritor posterior.

## Validación contra el corpus real

Aplicado a `err1.ktr`/`err2.ktr` (el caso que motivó el diseño): `dim_producto` dispara C1 (escrita por `Cargar Dim Producto`, leída por `Lookup Dim Producto`, componentes de hop ya distintos) → 2 KTR, `Cargar Dim Producto` antes que la rama de hechos. `dim_tiempo` (leída por `DBLookup` sin productor en la etapa) → notificación, sin afectar el corte. Coincide con la partición que un modelador humano haría a mano, y con una segunda validación independiente (dos soluciones Kettle no relacionadas entre sí, partiendo del mismo `.ktr`, convergieron en la misma partición).

## Dónde vive en el código

- `backend/app/services/ktr_builder/fragmentation.py` — `build_rw_matrix()`, `compute_cut()` (componentes + notificaciones), `split_ktr_by_cut()` (parte `ktr_data` en N sub-dicts según los grupos; 1 grupo → mismo objeto, cero costo), `validate_stage_contract()`.
- `backend/app/services/etl_generator.py` — `_build_ktr_stage()` llama `split_ktr_by_cut()` y luego `build_ktr()` una vez por grupo, entre `repair_integrity_gaps` y `build_ktr()`. `_build_job_plan()` generaliza de 2 `JobEntry` fijos a N por etapa: 1 archivo → `entry_type="trans"` directo (comportamiento histórico); N>1 → `.kjb` intermedio + `entry_type="job"` en el job maestro.
- `backend/app/services/lineage_builder.py` — `stitch_lineage_many()` generaliza de 2 KTR fijos a M archivos (matching de sink→source por nombre de tabla entre archivos no adyacentes); `stitch_lineage(a, b)` es un wrapper de `stitch_lineage_many([a, b])`.
- `backend/app/services/adapters/sql_table_resolver.py` — `resolve_sql_tables()`, implementación real (sqlglot) del protocolo `domain/sql_resolution.py:SqlTableResolver` que `build_rw_matrix` recibe inyectado.
- `backend/app/domain/table_layer.py` — `infer_table_layer()`, heurística de prefijo staging/DWH usada tanto por la clave `(connection, table)` de la matriz como por `ktr_builder/connection.py`.

## Capas (ver también `arquitectura-objetivo.md`)

La matriz R/W y el algoritmo de corte (componentes, orden topológico) son reglas que siguen siendo ciertas sin importar qué DB o qué proveedor de LLM esté detrás → `domain/`. Coordinar ese razonamiento y disparar la escritura de N archivos `.ktr` + KJB es un caso de uso completo → `services/`. Cuántos `<transformation>`/`<job>` resultan y cómo se serializan a XML es una proyección de infraestructura — la entidad de dominio no sabe que existe un archivo físico.

## Gaps conocidos

- El caso general de corte multi-par dentro de un mismo componente (más de una relación conflictiva simultánea) no está resuelto — se notifica como error para revisión manual. No se construyó una solución general sin evidencia de que el caso ocurra en la práctica.
- `ExecSQL` con SQL no parseable por sqlglot queda fuera de la matriz con un `Finding` de error — no participa del corte, no se asume su modo R/W.
