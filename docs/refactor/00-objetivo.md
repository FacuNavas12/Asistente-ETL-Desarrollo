# Objetivo — Refactor de fragmentación

**Mutable, poco frecuente.** Se edita solo si cambia el objetivo mismo del refactor, no su estado de avance (eso vive en `ESTADO.md`).

**Última actualización:** 2026-07-22

Este archivo expande el objetivo de [`02-decisiones.md`](02-decisiones.md). No lo contradice — si algo acá choca con ese archivo, gana `02-decisiones.md` y esto queda obsoleto en ese punto.

---

## Qué habilita

Hoy el sistema fuerza todo ETL a exactamente 2 KTR (Origen→Staging, Staging→DWH) + 1 KJB plano. El LLM genera los steps de cada etapa; el backend los serializa a XML sin decidir nada sobre cuántos archivos hacen falta.

Esa rigidez tiene consecuencias documentadas en casos reales de falla (ver [`01-hallazgos.md`](01-hallazgos.md)):
- carreras lectura/escritura dentro del mismo KTR (una tabla se escribe y se lee en la misma etapa, sin frontera transaccional real),
- dimensiones consultadas por un step pero nunca cargadas por otro dentro del mismo archivo,
- dos escritores distintos sobre la misma tabla dentro de un KTR.

Fragmentar en más de un archivo por etapa, cuando corresponde, elimina esta clase de error por construcción — no por revisión manual del XML generado.

## Estado final deseado

El backend decide, con reglas deterministas sobre el grafo de steps (no el LLM, D6), cuántos archivos físicos materializan cada fase lógica:

- **Fase lógica** (Origen→Staging, Staging→DWH) se mantiene como concepto — D1.
- **Archivo físico**: puede ser 1 KTR (caso simple, sigue siendo válido y esperado) o N KTR cuando el corte lo justifica.
- Cuando una fase se parte en N > 1 KTR, se genera un KJB que orquesta esos N archivos en el orden correcto (dimensiones antes que hechos, respetando el grafo de FK).
- La jerarquía de jobs resultante, según el prompt de fragmentación ya escrito (sesión "Fragmentación"):
  - `job_origen_stg.kjb` — orquesta los KTR de Origen→STG.
  - `job_stg_dwh.kjb` — orquesta los KTR de STG→DWH.
  - `job_master.kjb` — ejecuta los dos anteriores en orden.
- **El corte es separación constructiva, no una compuerta que corta y después valida (corrección 2026-07-22, ver D15).** Se basa en una matriz step × tabla × {lee, escribe}: toda tabla que aparezca como W y R dentro de la misma etapa, o con doble escritor, marca una frontera de corte — esa es la señal, no un umbral. Los componentes conexos resultantes son los KTR; el orden entre componentes sale del grafo de FK. Un ETL válido es un DAG, y separar por esa señal produce un resultado válido por construcción: no existe el caso "no se pudo cortar".
- **V1** (ninguna tabla W y R en el mismo KTR) y **V3** (un solo escritor por tabla por KTR) son exactamente esa señal — no gates posteriores, las reglas que deciden dónde va cada frontera. Se satisfacen por construcción, no se re-chequean después esperando que puedan fallar.
- **V2** (toda tabla leída por un lookup tiene productor en el job) juega un rol distinto: no dice dónde separar, dice si el ETL está completo. Un lookup sin productor es un dato faltante, no una señal de fragmentación.
- Casos genuinamente patológicos — V2 falla (lookup sin productor), ciclo real en el grafo, `config` malformado que ni el fail-fast de detección salvó (H6) — no son una rama del algoritmo de corte. El backend emite el mejor esfuerzo, marca el archivo afectado y notifica de forma accionable por el canal de D13 (qué archivo, qué se infirió, qué revisar antes de correr en Spoon) — D15, que actualiza el alcance de D5. Fail-fast se mantiene en la detección misma del problema — nada de tragar el error antes de poder notificarlo; lo que D15 retira es únicamente el rechazo de la emisión.

**Alcance del corte — D6-bis (2026-07-22):** la fragmentación responde únicamente a corrección estructural (races, fallas silenciosas, conflictos de lectura/escritura sobre la misma tabla). Un KTR largo pero correcto **no se parte**. No hay umbrales hardcodeados tipo "partir si >15 steps" — el backend corta por señal estructural o no corta. Bajo esta regla, crear una tabla nueva, agregar una rama de validación de calidad, o reescribir SQL nunca son "fragmentación", aunque hayan aparecido mezclados con un corte real en algún caso histórico — eso viajó de polizón, no es parte de la regla.

## Qué cambia respecto de hoy

| Hoy | Estado final |
|---|---|
| 2 KTR fijos + 1 KJB plano, siempre | N KTR por fase (N ≥ 1, decidido por reglas) + jerarquía de KJB cuando N > 1 |
| El KJB builder solo sabe emitir `JobEntryTrans` (verificado: cero ocurrencias de `JobEntryJob` en el backend) | Soporta `JobEntryJob` para anidar `job_master.kjb` sobre los KJB de fase — **gap no resuelto, ver 01-hallazgos.md H7** |
| El corte de fragmentación no existe: todo lo generado por el LLM en una etapa va a un solo archivo | Corte determinista en backend, sobre una matriz R/W derivada del conocimiento de dominio centralizado (D8) |
| El conocimiento de "qué tabla toca cada step y en qué modo" está duplicado y ya divergente en al menos 4-5 lugares (ver H3, H4) | Una sola fuente de verdad (`STEP_CONTRACTS` extendido con el eje dest-side), con funciones finitas por proyección (`step_tables()`, `stream_field_keys()`, `dest_field_keys()`) — no un accessor único |
| El campo `config` de un step llega del LLM como string con JSON escapado adentro (`etl_output.py:101`), y se re-parsea en 5 puntos distintos con manejo de error inconsistente | Border único de entrada que produce un tipo válido por construcción, o falla fuerte (D5) — alcance exacto todavía no decidido, ver "Deliberadamente no decidido" en `02-decisiones.md` |
| El linaje (`lineage_builder.py`) es cosmético: alimenta reportes y warnings de UI | El linaje es insumo directo de una decisión de generación de código (qué se parte, en qué orden lo encadena el KJB) — un error de linaje deja de ser un warning feo y se vuelve un KTR mal partido o un KJB que ejecuta fuera de orden |
| Persistencia y contrato de salida asumen "1 documento KTR por llamada" | El modelo de salida cambia de forma: N KTR + KJB(s) en vez de una tupla fija — toca schema, persistencia y probablemente la API (`etl.py`, `job.py`, `ktr_build_job.py`) |
| ETLs guardados anteriores al refactor | Descartables (D3, **verificado** 2026-07-22: nadie tiene trabajo apoyado en ellos) — no hay migración ni modo de compatibilidad, ni período de convivencia entre parseo viejo y nuevo (D10). Regenerar desde datos base es el camino esperado, y sirve además como corpus de prueba del sistema nuevo |

## Qué no cambia

- El orden macro de fases (Origen→Staging, Staging→DWH) — D1 lo preserva como concepto, solo dejan de estar atadas 1:1 a un archivo.
- El principio de que el password nunca se persiste ni se embebe en el `.ktr` (ver `CLAUDE.md`, sección "Credenciales de conexión") — el refactor no toca esa decisión.
- El LLM sigue proponiendo el ETL lógico (steps, no archivos); el backend decide la materialización física de forma determinística — D6, re-verificada en frío y confirmada 2026-07-22.

## Qué queda deliberadamente fuera de este documento

Ver "Deliberadamente no decidido" en `02-decisiones.md`: si el borde tipado va antes o en paralelo a la fragmentación, el cambio `string → object` del schema del LLM, qué hace `build-from-raw` ante un raw incompleto, y el alcance exacto de las reglas de corte. Este documento no resuelve nada de eso — lo señala como pendiente y remite al archivo de decisiones.
