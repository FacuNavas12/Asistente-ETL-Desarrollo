# Decisiones — Refactor de fragmentación

**Última actualización:** 2026-07-25

Este archivo es la fuente de verdad del refactor. Manda sobre cualquier análisis, plan o conclusión de sesión que lo contradiga. Cuando un análisis choca con una decisión de acá, gana la decisión y el análisis queda marcado como obsoleto.

Toda sesión que tome una decisión cierra actualizando este archivo.

---

## Índice por fase

Navegación rápida — clic para ir directo a la decisión. Grupos según la taxonomía de fases de [`03-plan.md`](03-plan.md). El tag `[Fase]` al final de cada título de decisión repite este agrupamiento in situ, para orientarse sin volver acá.

**Fundamentos** (doctrina general, aplica a todo el refactor, no a una fase puntual)
[D1](#d1) fase lógica ≠ archivo físico · [D2](#d2) no se preserva comportamiento actual · [D3](#d3) datos guardados descartables · [D4](#d4) compat. hacia atrás no es requisito · [D5](#d5) ante la duda, falla · [D9](#d9) criterio de verificación: delta declarado · [D10](#d10) sin convivencia parseo viejo/nuevo · [D13](#d13) definición de terminado (toda fase) · [D15](#d15) fail-fast en detección, no fail-hard en emisión

**Eje `dim_contracts` / G-step** (fuera de Track F, pero lo cruza en F3/F4)
[D11](#d11) `dim_contracts` no choca con fragmentación

**F1.5** — dominio mínimo para el corte
[D8](#d8) conocimiento de dominio: una sola casa · [D14](#d14) F1.5/F2.5 no dependen circularmente de sí mismas · [D18](#d18) H2 (config string→object) pospuesto, no decidido

**F2** — diseño del corte
[D6](#d6) el backend decide la fragmentación, determinístico · [D6-bis](#d6-bis) fragmentación = corrección, no legibilidad · [D7](#d7) reglas derivadas de casos reales · [D17](#d17) F2 aprobado por el usuario

**F3** — implementación del corte
[D16](#d16) dependencia externa real: eje `dim_contracts` · [D19](#d19) wiring de servicio cerrado, HTTP en modo notificación · [D20](#d20) forma de la respuesta con N archivos

**F4** — track de errores / contenido generado
[D12](#d12) dialecto SQL: Postgres por defecto + notificación obligatoria · [D21](#d21) miembro inferido (cierra C.6) · [D22](#d22) triage F4, 3 gaps cerrados por prompt · [D23](#d23) alcance del validador de contrato entre KTR (cierra ítem pendiente de D22)

**Otras secciones del archivo**
[Deliberadamente no decidido](#deliberadamente-no-decidido) · [Verificaciones pendientes](#verificaciones-pendientes) · [Abiertos](#abiertos-no-bloquean-el-arranque-del-refactor-sí-bloquean-ítems-puntuales) — [C.1](#c1) dialecto multi-motor `[F4]` · [C.2](#c2) reglas de corte vs. D6-bis `[F2]` ✓ · [C.3](#c3) verificaciones DB real `[F1/F4]` · [C.4](#c4) auditoría retroactiva `[Fundamento]` · [C.5](#c5) constraints DDL `[F4]` · [C.6](#c6) FK no resuelta `[F4]` ✓ resuelta por D21

---

## Objetivo

Hoy el sistema fuerza todo ETL a exactamente dos archivos KTR (Origen→Staging, Staging→DWH). **Ese forzado es la falla:** cuando un proceso necesitaba separarse, meterlo igual dentro de dos archivos produjo errores.

El refactor desacopla la fase lógica del archivo físico. El orden macro Origen→Staging / Staging→DWH se mantiene como concepto de fases, pero deja de determinar la cantidad de archivos. El backend decide, en base a reglas concretas, cómo se materializan esas fases: puede ser un KTR, pueden ser varios. Cuando son varios, se genera además un KJB que los ordena.

Fragmentar no es obligatorio ni el caso por defecto: es una decisión razonada sobre el conjunto de steps y sus dependencias. Para un ETL simple, el resultado correcto puede seguir siendo dos archivos.

**Razón:** corrección estructural — races de lectura/escritura, dimensiones consultadas pero no cargadas, doble escritor sobre la misma tabla, arreglos de KTR que fallen silenciosamente. **No** es legibilidad ni buenas prácticas de organización en general — ver D6-bis. Un KTR largo pero correcto no se parte.

Todo lo demás del proyecto es río abajo de este objetivo y se evalúa contra él.

---

## Decisiones vigentes

<a id="d1"></a>
### D1 — Fase lógica ≠ archivo físico `[Fundamento]`

La cantidad de archivos KTR deja de estar fijada. Se deriva de reglas aplicadas sobre el conjunto de steps y su grafo de dependencias.

*Por qué:* hoy los dos conceptos están mapeados 1:1 y hardcodeados, y esa es la causa raíz de los errores que motivan el refactor.

*Consecuencia:* hay que encontrar y remover la partición fija en dos, y revisar qué código asume que siempre son dos.

*Qué la invalidaría:* que se demuestre que ningún caso real requiere más de dos archivos.

<a id="d2"></a>
### D2 — No optimizamos por preservar el comportamiento actual `[Fundamento]`

Las zonas afectadas van a sufrir cambios estructurales que vuelven irrelevante si hoy funcionaban. "Esto hoy anda" no es argumento para protegerlo.

*Por qué:* el plan estaba gastando esfuerzo en conciliar comportamientos que el refactor vuelve obsoletos.

<a id="d3"></a>
### D3 — Los datos guardados son descartables `[Fundamento]`

Regenerar los ETLs desde datos base es preferible, y además sirve para volver a probar el sistema. No pedimos migración de datos ni modo permisivo por compatibilidad histórica.

*Consecuencia:* cae la objeción de "los ETLs viejos dejan de abrir". También cae la conclusión previa de que `parse_cfg` no se puede eliminar nunca — descansaba enteramente en las filas históricas.

*Qué la invalidaría:* que alguien del equipo tenga trabajo apoyado en ETLs guardados. Ver verificaciones pendientes.

<a id="d4"></a>
### D4 — La compatibilidad hacia atrás no es requisito hasta nuevo aviso `[Fundamento]`

Cuando lo sea, se decide explícitamente acá y se revisa todo lo que dependa de esto.

<a id="d5"></a>
### D5 — Ante la duda entre tolerar y fallar, se falla `[Fundamento]`

Preferimos que un cambio rompa fuerte y visible antes que degrade en silencio.

*Por qué:* no es preferencia estilística. Es el mismo principio que motiva la fragmentación —evitar arreglos de KTR que fallen silenciosamente— aplicado al código que los genera.

*Consecuencia:* nada de degradar a valores vacíos dentro de un `except`. Un input inválido produce un error explícito con contexto suficiente para ubicarlo.

<a id="d6"></a>
### D6 — La fragmentación la decide el backend, de forma determinística `[F2]`

El LLM propone el ETL lógico. El backend decide la materialización física en N KTRs más el KJB.

*Por qué:* el refactor existe para reducir errores. Poner la decisión en el LLM le mete no-determinismo justo a la capa que existe para eliminarlo.

**Estado: confirmado, con evidencia en repo (re-verificado en frío, 2026-07-22).** Evidencia:

1. `_build_job_plan()` (`backend/app/services/etl_generator.py:224`) ya construye el `JobPlan` del KJB en Python puro — precedente de orquestación backend-owned.
2. Contracaso instructivo: el flujo `CreateJob` **sí** consulta al LLM, porque ahí los `.ktr` son de autoría externa y el backend no tiene grafo propio. La línea divisoria es *dónde ya vive la información*, no una preferencia general por determinismo.
3. `build_lineage()` (`backend/app/services/lineage_builder.py`) ya computa `in_deg`/`out_deg` y extrae tablas por step — exactamente la señal que necesita un algoritmo de corte.
4. `repair_ktr_steps()` (`backend/app/services/ktr_builder/repair.py:136`), `repair_integrity_gaps()` (`repair.py:230`) y `enforce_dimension_step_policy()` (`backend/app/services/ktr_builder/dimension_step_policy.py:72`) ya son mutaciones determinísticas post-LLM. El pase de fragmentación entra en ese mismo punto del pipeline.

*Qué la invalidaría:* si se diera vuelta, cambia el schema de salida entero, las reglas pasan a ser prompt engineering en vez de código testeable, y hay que revisar D1 y el plan completo. (Ya no es un riesgo abierto — queda documentado por si algo futuro lo pone en duda.)

<a id="d6-bis"></a>
### D6-bis — La fragmentación es un mecanismo de corrección, no de legibilidad `[F2]`

**La fragmentación responde únicamente a corrección estructural: races, fallas silenciosas, conflictos de lectura/escritura sobre la misma tabla. Un KTR largo pero correcto no se parte.**

*Por qué:* el proyecto acelera y busca que funcione. Está orientado a profesionales del área — si el usuario quiere reorganizar el KTR a su gusto, es su terreno y su responsabilidad, no del generador.

*Consecuencia:* **no se introducen umbrales hardcodeados** del tipo "partir si >15 steps". El backend corta por señal estructural o no corta. Esta regla frena el próximo "ya que estamos, partamos esto que es largo".

*Corolario bajo D6+D6-bis juntas:* crear una tabla nueva (ej. `dim_tiempo`), agregar una rama de validación de calidad, o reescribir SQL, nunca pudieron ser "fragmentación" — ningún análisis de grafo produce eso. Si aparecen mezclados con un corte real en algún caso histórico, son cambios que viajaron de polizón, no parte de la regla.

*Pendiente:* el material de fragmentación (`handoff_fragmentacion_y_errores.md`) ya contiene reglas de cuándo fragmentar escritas antes de esta decisión. Hay que releerlas y eliminar las que respondan a legibilidad o tamaño en vez de corrección estructural — ver `03-plan.md`, ítem bloqueante antes de diseñar el corte (Track F2).

<a id="d7"></a>
### D7 — Las reglas de fragmentación se derivan de casos reales de falla `[F2]`

No se diseñan desde una lista abstracta de buenas prácticas de Pentaho. Se derivan de los casos concretos donde forzar dos archivos produjo errores: qué ETL, qué steps, qué falló, cómo se resolvió separando.

*Por qué:* tenemos evidencia empírica. Sin ella, el motor de reglas se diseña contra un problema imaginado y va a partir de más o de menos.

*Consecuencia:* cada caso histórico de falla es también un caso de prueba: debe producir la partición correcta.

<a id="d8"></a>
### D8 — El conocimiento de dominio sobre steps tiene una sola casa `[F1.5]`

Qué tabla toca un step, con qué alias, y si lee o escribe: eso vive en un único lugar. Ningún código nuevo —incluido el motor de fragmentación— reimplementa esa noción por su cuenta.

*Por qué:* hoy está duplicado en al menos cuatro archivos y **ya divergió**. El motor de reglas sería el quinto y el más importante: construirlo sobre una base que diverge es garantizar particiones incorrectas.

*Consecuencia:* centralizamos el dato, no necesariamente la interfaz. Una sola fuente de verdad, y encima funciones separadas y finitas por cada proyección que los consumidores necesiten. No forzamos un accessor único que devuelva todo.

<a id="d9"></a>
### D9 — Criterio de verificación: delta declarado, no diff contra el pasado `[Fundamento]`

El prompt de Fase 5 (auditoría de arquitectura) pedía verificar cada paso "comparando el artefacto generado antes y después". D2 mata esa política de preservar comportamiento, pero no mata la necesidad de un criterio de verificación — solo cambia contra qué se compara.

**Contra qué se compara: contra el delta declarado, no contra el output viejo.** Antes de correr un paso se enumera qué va a cambiar. Después, cada diferencia observada tiene que mapear a un ítem declarado. Criterio de aprobación: **cero deltas sin explicar**. No exige que nada cambie; exige que nada cambie por sorpresa.

*Herramienta:* normalización canónica — aplanar todos los `.ktr` a una secuencia ordenada de steps con su config y hops, ignorando fronteras de archivo. Así se genera la lista de deltas de forma confiable.

*Cuatro clases de cambio, cada una con su línea base propia* (un solo "diff" mezclaba las cuatro, por eso el diff se volvía ilegible):

| Clase | Ejemplo | Se valida contra |
|---|---|---|
| Costura forzada por el corte | 2 `TableInput` para alimentar un `StreamLookup` que antes era 1 | Canónico invariante |
| Funcionalidad nueva | Un step nuevo que antes no existía | Requisito propio, explícito |
| Rediseño (sustitución de tipo de step) | `DimensionLookup` → `InsertUpdate` | Decisión explícita con su costo declarado |
| Corrección / supuesto | Fix de nombre/rename, dialecto SQL asumido | Bug fix vs. supuesto introducido, declarado como tal |

*Consecuencia sobre la Restricción 1 de Fase 5 (`fase-5-plan-remediacion.md`):* se parte en dos lecturas — A) "el artefacto sigue produciendo lo mismo": **eliminada**, es lo que D2 dice que no se protege. B) "el repo queda verde y cada paso es revertible por separado": **se mantiene**, es regla de tamaño de paso, no de preservación de comportamiento.

*Por qué:* sin este criterio, D2 se leía como "no verificamos nada", que no es lo que dice — dice que no usamos "distinto de antes" como señal de bug por sí sola.

<a id="d10"></a>
### D10 — Sin período de convivencia entre parseo viejo y nuevo `[Fundamento]`

Consecuencia directa de D3 verificado (ver Verificaciones pendientes): como nadie tiene trabajo apoyado en datos guardados, el requisito de compatibilidad no existe. El mecanismo de vuelta atrás ante un problema es revertir el commit, no sostener dos caminos en paralelo.

*Consecuencia:* la sección "Compatibilidad durante la transición" del prompt de Fase 5 (`fase-5-plan-remediacion.md`) queda sin motivo — el borde nuevo puede reemplazar el parseo viejo de una vez, sin ventana planeada de convivencia.

*Por qué importa dejarlo explícito acá:* si el resto del prompt de Fase 5 se retoma sin marcar esto, se reabre desde cero una pregunta que ya tiene evidencia (D3).

<a id="d11"></a>
### D11 — `dim_contracts` (commit `149b836`) no choca con el refactor de fragmentación `[dim_contracts]`

Eje distinto: `dim_contracts` decide **qué tipo de step** carga una dimensión (SCD1 vs SCD2); la fragmentación decide **cuántos archivos**. No se pisan.

Más importante: `dim_contracts` ya usa el patrón que D6 pide — el backend deriva determinísticamente, el modelo no rejuzga en cada corrida (`dimension_step_policy.derive_dimension_step_type`). Es **precedente, no obstáculo**. No hay que tocarlo ni revertirlo.

*Consecuencia menor:* toca en chico dos cosas ya documentadas para cambiar bajo D8, ambas dentro del PASO 1 planeado — `dimension_step_policy.py:53` (copia propia de `parse_cfg`, ver H3 en `01-hallazgos.md`) y `dimension_step_policy.py:107` (alias de tabla con `or` inline en vez de `contracts.STEP_CONTRACTS.key_aliases`, ver H4).

<a id="d12"></a>
### D12 — Dialecto SQL: Postgres por defecto, con notificación obligatoria `[F4]`

El SQL generado depende del motor que declara el usuario, y hasta ahora eso no estaba escrito en ningún lado — Postgres fue un supuesto implícito horneado en construcciones específicas de dialecto en el SQL generado (ej. `DISTINCT ON`) en salidas de sesiones anteriores. No hay ocurrencias de ese patrón en el backend actual (`backend/`) — el supuesto vive en el SQL que el LLM genera dentro de `config`, no en código Python.

**Decisión:** por defecto, toda query SQL se genera asumiendo PostgreSQL. Queda escrito como decisión, no como supuesto implícito.

**Punto de notificación obligatorio:** cuando el flujo llegue al momento de generar SQL con dependencia de dialecto, tiene que avisar y dar contexto en vez de asumir en silencio. Es información crítica que se fija antes de generar — cambiarla después implica retocar todo lo ya generado.

*Por qué:* mismo principio que D9 — declarar antes, no explicar después.

*Fuera de alcance de esta decisión:* el soporte real multi-motor (Postgres / SQL Server según la base final elegida) no tiene plan todavía. Requiere sesión y sub-plan propios — ver "Abiertos" más abajo.

**Segunda y tercera ocurrencia confirmada (2026-07-22, `bitacora_etl_ventas.md`):** `DISTINCT ON` (R12, dedup de staging por `DISTINCT ON (clave_negocio) ORDER BY stg_fecha_carga DESC`) y `generate_series` (R10, calendario contiguo de `dim_tiempo`) — ambas construcciones exclusivas de Postgres, ambas usadas y confirmadas en verde en la solución de contraste de la bitácora. Ya no es un patrón hipotético citado de sesiones anteriores — es un caso real, empírico, generado por un LLM sin que el prompt se lo pidiera explícitamente. Refuerza la necesidad del punto de notificación obligatorio que esta decisión ya fija. Ruteo: F4 (contenido generado) — ver `03-plan.md`.

<a id="d13"></a>
### D13 — Definición de terminado, obligatoria para toda fase del plan `[Fundamento]`

Ninguna fase de `03-plan.md` (Track A o Track F) se da por cerrada sin estas tres cosas:

1. **Dos tests:** uno que haga cumplir específicamente lo que esa fase trabajó, y uno que verifique que el contrato que esa fase *expone* se sostiene (lo que la fase siguiente va a consumir) — escrito como contrato expuesto, no como "conexión con la fase siguiente", para no desactualizarse si el orden de fases cambia.
2. **El registro de deltas de esa fase** (D9), emitido como *warnings del propio pase* en el mismo punto del pipeline donde ya viven `repair_ktr_steps`, `repair_integrity_gaps` y `enforce_dimension_step_policy` — automático en cada corrida, no un documento que depende de que alguien lo escriba y lo lea. Tiene que cubrir **las dos fuentes de cambio**: lo que el backend genera determinísticamente y lo que produce una sesión de generación con el LLM. Los tests no lo reemplazan — un test afirma lo que a alguien se le ocurrió afirmar; el registro expone lo que viajó sin que nadie lo pidiera (ver "SCD tipo 2" en `01-hallazgos.md`, H9 — así se perdió esa vez). **Mismo canal que usa D15** para notificar al usuario final cuando el backend emite con un problema marcado en vez de abortar — no es solo un registro interno de la sesión de refactor.
3. **`CLAUDE.md` y un archivo de progreso actualizados:** qué cambió a nivel de convenciones/arquitectura/decisiones vigentes, y qué fase se cerró, qué queda, qué se decidió en el camino. Objetivo: el plan es retomable por cualquiera, no solo por quien lo arrancó.

*Por qué:* sin esto, el tramo "rojo" de la migración no tiene final definido fase por fase — siempre se corre un cambio más antes de reconectar.

<a id="d14"></a>
### D14 — F2/F3 no dependen del borde tipado grande; dependían circularmente de sí mismas `[F1.5/F2.5]`

`03-plan.md` hacía depender F2 de "borde tipado + STEP_CONTRACTS centralizado" en su columna "Depende de", mientras la columna "Hallazgos que toca" de esa misma fila listaba H4 y H11 — los hallazgos que esa centralización requiere resolver. Mismo patrón en F3: "Depende de" pedía H7 resuelto, y "Hallazgos que toca" incluía H7. Las dos fases dependían de algo que ellas mismas producían — sin punto de entrada válido.

**Lo que el motor de corte necesita en concreto, sin preguntas abiertas:**
- H4 — alias de tabla resuelto vía `contracts.STEP_CONTRACTS.key_aliases`, no la copia divergente de `lineage_builder` (ni el `or` inline de `dimension_step_policy.py:107`).
- H11 — `DBLookup` cubierto en la matriz R/W (hoy invisible para el linaje).
- H6 — el parseo de `config` falla fuerte (D5) en vez de degradar a `{}`. Relevante para el corte porque una config rota leída como `{}` produce un corte silenciosamente equivocado.

Los tres tienen dirección ya decidida (D5, D8) y no dependen de ningún spike ni de ninguna pregunta listada en "Deliberadamente no decidido".

**Corrección 2026-07-22 — H6 lo cierra F1.5, no F5 (contradicción encontrada y resuelta entre este archivo y `03-plan.md`).** La redacción original decía que H6 "se resuelve solo cuando F5 deduplica los 4 copies", pero la fila de F1.5 en `03-plan.md` ya listaba a H6 como parte de su propio alcance — dos fases reclamando el mismo fix. Gana F1.5: dedup de `parse_cfg` (H3) y fail-fast (H6) son la misma pieza de trabajo (no tiene sentido arreglar el comportamiento de 4 copias por separado), y F1.5 es la fase que ya está tocando este archivo por H4/H11. F5 pierde ese ítem — ver su fila actualizada en `03-plan.md`. **H4 y H11 ya resueltos** en esta misma sesión (ver `01-hallazgos.md`) — como efecto colateral, la copia de `_parse_cfg` en `dimension_step_policy.py` ya desapareció (importa `contracts.parse_cfg`), así que el dedup restante de H3 pasó de 4 copias a 3 (`validate.py`, `ktr_default_validator.py`, `lineage_builder.py`). **H6 en sí (el fail-fast) sigue sin implementar** — pendiente de la pregunta abierta más abajo sobre si el fallback a `{}` puede llegar a ejecutarse de verdad y con qué severidad, antes de tocar el comportamiento.

**Lo que el motor de corte NO necesita:** el borde tipado grande tal como lo describe `00-objetivo.md` (cambio de schema `string → object`, H2; border único con tipo validado). Esa sigue siendo una pregunta de arquitectura de entrada completa, abierta, sin fecha porque depende de Track A (pospuesto) y de un spike empírico. El corte puede construirse sobre el `dict` que ya devuelve `parse_cfg` hoy, siempre que tenga los tres puntos de arriba resueltos primero.

**Consecuencia — desdoblamiento de fases (ver `03-plan.md`):** H4+H11+H6 pasan a una fase previa chica (F1.5), separada de F2. H7 pasa a una fase previa propia (F2.5), separada de F3. Ninguna fase queda dependiendo de sí misma.

*Por qué:* mismo principio que D8 — el conocimiento de dominio tiene una sola casa, y esa casa se construye antes de que el consumidor (el corte) la dé por hecha, no como parte del mismo paso que la consume.

<a id="d15"></a>
### D15 — Fail-fast en detección, no fail-hard en emisión: el backend emite mejor esfuerzo y notifica `[Fundamento]`

Ajuste de alcance sobre D5, motivado por el modelo de producto: el sistema es un acelerador para profesionales de Spoon, no un generador que garantiza corrección por sí solo. Un `.ktr` emitido con un problema señalado es menos costo para el usuario que un backend que se niega a generar — el costo de la alternativa estricta (tocar backend, regenerar steps, mecanismos de descarga de steps armados solo para mitigar ese costo) ya se pagó una vez.

**D5 se parte en dos mitades — no se revierte, se acota:**

- **Fail-fast en detección/parseo — sigue igual, sin cambios.** Un `except: return {}` que traga un error de parseo (H6) sigue prohibido: un error tragado no se puede notificar después. Esta mitad de D5 no se toca.
- **Fail-hard en emisión — se retira.** El backend ya no se niega a emitir un `.ktr`/`.kjb` porque un chequeo de integridad (V2 — ver corrección abajo sobre qué rol juega cada validador — o cualquier check de `error_catalog_checks.py`) encontró un problema en un input malformado o patológico. Emite el mejor esfuerzo posible y marca el archivo.

**Mecanismo de notificación — reutiliza D13, no uno nuevo.** Todo error detectado se documenta en el registro de deltas de D13 (los `warnings` que ya recorren el pipeline en el mismo punto que `repair_ktr_steps`/`repair_integrity_gaps`/`enforce_dimension_step_policy`, y que ya vuelven al caller como tercer elemento de la tupla de `build_ktr`). D13 ya declaraba ese canal como automático y ligado a la corrida — esta decisión fija que además es el canal que llega al usuario final, no solo un registro para quien audita la sesión de refactor.

**Requisito de forma — accionable, no genérico.** Cada notificación dice: qué archivo, qué se infirió (ej. "orden asumido: STG antes que DWH, no verificado contra grafo de FK"), y qué revisar antes de correr en Spoon. Un warning genérico ("hubo un problema") no cumple esta decisión.

**Consecuencia concreta sobre código ya escrito, no solo sobre diseño futuro:**
- `ktr_xml_validator.py:100-117` (`validate_ktr_xml`, `raise KtrXmlValidationError`) está wireado siempre en `build.py:401` y hoy aborta la emisión — es exactamente el comportamiento que esta decisión retira. Pasa a alcance de **F3** (que ya toca este archivo, ver `03-plan.md`): convertir el `raise` en un finding anotado + notificación accionable por el canal de D13.
- `error_catalog_checks.py` (V4-V13) verificado sin callers en el backend — no está wireado a nada todavía, no hereda el problema, pero cuando se conecte nace directo con el patrón "anota, no aborta".
- `00-objetivo.md` describía los validadores V1/V2/V3 como gate que "aborta... nunca emite un artefacto incoherente" — corregido en ese archivo para reflejar esta decisión.

**H5 (linaje acoplado por orden de ejecución, `01-hallazgos.md`) — resuelto bajo esta decisión.** Opción elegida: riesgo documentado y notificado, no prerrequisito bloqueante. F1.5 mantiene su alcance original (H4 + H11 + H6, sin H5). F2 diseña el corte apoyándose en `build_lineage()` tal como está — con el acoplamiento R10 (`arquitectura-objetivo.md`) todavía presente — siempre que emita el aviso accionable cuando no pueda garantizar el orden inferido.

**Corrección (2026-07-22) — el corte no es una compuerta que falla, es separación constructiva.** La redacción original de este punto preguntaba "qué hace F2 cuando el corte no puede satisfacer V1/V2/V3 limpio" — presuponía un estado de fallo que un ETL válido no produce. Un ETL válido es un DAG; separarlo en KTR ordenados por un KJB, siguiendo la señal estructural, produce un resultado válido por construcción. No existe "no se pudo cortar" para un input válido.

Consecuencia sobre el rol de cada validador — **V1 y V3 no son gates, son las reglas que guían dónde separar:**
- **V1** (ninguna tabla W y R en el mismo KTR) y **V3** (un solo escritor por tabla por KTR) son señal estructural de corte (consistente con C.2 y D6-bis): tabla escrita y leída por steps distintos, o doble escritor, marcan frontera. Separar exactamente ahí satisface V1/V3 por construcción — no se validan después, se usan para decidir el corte.
- **V2** (todo lookup tiene productor en el job) es distinto: no dice dónde separar, dice si el ETL está completo. Un lookup sin productor es un dato faltante — error a notificar bajo esta misma D15, no una señal de fragmentación.

Lo que sí sigue bajo D15 (generar-y-notificar, no bloquear): el caso genuinamente patológico — ciclo real en el grafo, `config` malformado que ni H6 pudo salvar, lookup sin productor (V2). Ninguno de esos es una rama del algoritmo de corte; son el mismo mejor-esfuerzo que D15 ya cubre para cualquier otro fallo de generación. F2 no diseña un plan B para el corte — diseña la separación constructiva. Detalle de las reglas concretas en `03-plan.md`, fila de F2.

*Por qué separado de D5 en vez de reescribirla:* mismo criterio que D6/D6-bis — D5 sigue siendo la doctrina general (ante la duda, fallar visible). D15 fija dónde se traza la línea entre "fallar" (detección, sigue firme) y "bloquear" (emisión, se retira), que D5 dejaba ambigua y que `00-objetivo.md` había resuelto para el lado que esta decisión ahora corrige.

<a id="d16"></a>
### D16 — El corte tiene una dependencia externa real (eje `dim_contracts`), no una que Track F resuelva `[F3]`

Disparada por el análisis de `bitacora_etl_ventas.md`/`extracto_corte_F2.md` (2026-07-22): el `extracto` preguntó si C1-bis (doble escritor sobre `dim_producto` en `err1.ktr`/`err2.ktr`, H21) era un **fantasma** — un artefacto de que el step estaba mal elegido, no un problema estructural real. Verificado contra el código (no contra memoria):

- `enforce_dimension_step_policy` (`dimension_step_policy.py:41-50`, `derive_dimension_step_type`) **sí** corre antes del punto de inserción del corte (H20) — orden confirmado: `repair_ktr_steps → repair_integrity_gaps → enforce_dimension_step_policy → [corte] → build_ktr` (`etl_generator.py:800-818`). El orden no es el problema.
- Pero su vocabulario de salida es binario y no cubre el caso real: deriva únicamente `DimensionLookup` (scd_type==2) o `CombinationLookup` (cualquier otro caso) — **nunca** `Insert/Update`, `Table Output` ni `StreamLookup`. La bitácora (R1, confirmado por log en `L2-E01`/`L3-E01`) prueba que para una dimensión simple (sin `version`/fechas) el step correcto es `Insert/Update` (o el patrón `Table Output` insert-new-only), no `CombinationLookup` — combinación nunca ejercitada ni por la bitácora ni por el repo.
- Más grave: **ninguno de los dos tipos derivables hoy es de solo lectura.** `DimensionLookup` y `CombinationLookup` son R+W siempre (H19: el builder hardcodea `update=Y` / la semántica del step no tiene modo solo-lectura). `enforce_dimension_step_policy` tampoco distingue "este step carga la dimensión" de "este step solo busca la FK para el hecho" — corrige el *tipo* de cualquier step que matchee una tabla de `dim_contracts`, sin importar su rol. Consecuencia: aunque el tipo derivado sea "correcto" según SCD, el step usado como lookup del lado del hecho sigue siendo R+W por construcción — exactamente el patrón que dispara C1/C1-bis en `err1.ktr`/`err2.ktr` (H21) y que la bitácora reprodujo de forma independiente en `dim_producto` (L1-G1/L2-E01).

**Conclusión: C1-bis no es un fantasma — es una señal real que se va a seguir disparando sobre ETLs legítimos** hasta que exista un tipo de step genuinamente de solo lectura para el lookup del lado del hecho. La bitácora ya lo resolvió empíricamente dos veces por caminos independientes: R2 (lookup de dimensión en el hecho siempre de solo lectura) + R9, refinado por log (`DBLookup` falla la introspección de metadata contra el pooler de Supabase — `getTableFields`, ver H23 en `01-hallazgos.md`; el sustituto que funcionó es `StreamLookup`, que además no toca tabla en la matriz R/W — H19 — así que un lookup de hecho implementado como `StreamLookup` nunca dispara el corte, por diseño, no por parche).

**Ubicación de la corrección — eje `dim_contracts`, NO el motor de corte (D6-bis, D11):** esto no es fragmentación — es selección de step por forma de tabla/rol, mismo eje que ya decide SCD1 vs SCD2 (`dimension_step_policy.py`, serie `dim_contracts`, D11). Track F no lo implementa; Track F **depende** de que se implemente. Es la misma relación de dependencia externa que D14 ya nombró para el borde tipado grande (H2) — con una diferencia importante: el borde tipado grande **no** bloqueaba a Track F (D14). Esto **sí** lo hace, aunque viva en otro eje.

**Consecuencia sobre el plan:** F3 (implementación del corte) tiene un prerrequisito externo a Track F, no solo F1.5/F2.5 (D14). Dos caminos, a decidir por el usuario antes de F3, no algo que esta sesión resuelva unilateralmente:
1. Ampliar el vocabulario de `derive_dimension_step_type` (agregar `Insert/Update`/`Table Output` para el loader cuando la forma de la tabla lo pide, y forzar `StreamLookup` — no `DimensionLookup`/`CombinationLookup`/`DBLookup` — para cualquier step que solo busca la FK del lado del hecho) **antes** de que F3 arranque.
2. F3 arranca igual, con el riesgo documentado y notificado (D15): el corte puede sobre-disparar C1-bis sobre ETLs donde el "doble escritor" es en realidad un lookup mal tipado, no un conflicto real — y el usuario revisa esos casos a mano hasta que el camino 1 se resuelva.

*Por qué D16 y no una fila más en `03-plan.md`:* cambia qué puede prometer F3 sin trabajo externo, igual que D14 — nivel de decisión de scope, no de tarea.

**Resuelto 2026-07-23 — camino 1, elegido por el usuario.** Ampliar `derive_dimension_step_type`/`enforce_dimension_step_policy` (`dimension_step_policy.py`) antes de que F3 arranque. **No implementado todavía — y no es un cambio chico de enum:**

- Hoy `DIMENSION_STEP_TYPES = {"DimensionLookup", "CombinationLookup"}` (`dimension_step_policy.py:39`) y `derive_dimension_step_type` (`:42-51`) no tienen ningún concepto de **rol** — `enforce_dimension_step_policy` corrige el tipo de *cualquier* step que toque una tabla de `dim_contracts`, sea el step que carga la dimensión o el que solo busca la FK del lado del hecho (exactamente el gap que documenta H22). Agregar `Insert/Update`/`Table Output` al vocabulario del loader no alcanza solo: hace falta **detectar el rol** (loader vs. lookup-de-hecho) antes de poder aplicar una regla distinta a cada uno.
- Señal disponible para esa detección: R2/R9 de la bitácora ya validan que el lookup del lado del hecho es siempre de solo lectura — un candidato es reusar el rol que `lineage_builder._classify_layer` ya deriva por step (in_deg/out_deg + tabla), o el mismo insumo de H19 (matriz R/W) que F2 construye para el corte. Confirmar cuál antes de escribir código — esto es una mini-decisión de diseño propia, del mismo tamaño que la que F2 necesitó, no una edición de una línea.
- Una vez detectado el rol: loader puede derivar `DimensionLookup`/`CombinationLookup`/`Insert-Update` según `scd_type` + forma de tabla; lookup-de-hecho se fuerza a `StreamLookup` (nunca `DimensionLookup`/`CombinationLookup`/`DBLookup` — `DBLookup` además falla contra el pooler de Supabase, H23/R9).

Sigue bloqueando F3 hasta que esto esté en código, no solo decidido.

**Código aplicado 2026-07-24 (parcial, ver residual abajo).** `dimension_step_policy.py`:
- `role_of_dimension_step(step_name, table, ktr_data, step_type_aliases)` — BFS hacia adelante sobre los hops habilitados, ancla el predicado "escritor" en `_UNAMBIGUOUS_WRITER_TYPES = {TableOutput, InsertUpdate, Update, Delete}` (nunca en DimensionLookup/CombinationLookup, cuyo status de escritura es exactamente lo que se está resolviendo para la misma tabla — evita el chicken-and-egg). Si alcanza un escritor de tabla DISTINTA de `table` → `"fact_lookup"`; si no (termina en la propia tabla, o en sinks sin tabla como WriteToLog/checkpoints) → `"loader"`.
- `enforce_dimension_step_policy` (Paso 4): rol `fact_lookup` con `scd_type==2` → fuerza `DimensionLookup` + `cfg["update"]="N"` (warning). Respeta `OVERRIDE_STEP_PREFIX` igual que el resto de la función.
- `lookups.py::_step_DimensionLookup` (Paso 5): dejó de hardcodear `<update>Y</update>` — ahora lee `cfg.get("update", "Y")`.

**Residual `scd_type` 0/1 (dimensión sin versionar) — cerrado 2026-07-24, camino prompt, no auto-repair.** El contrato deriva `CombinationLookup`, que no tiene modo de solo-lectura (a diferencia de `DimensionLookup`, no expone flag `update`). Forzar `DimensionLookup+update=N` sin `date_from`/`date_to` conocidas seguía descartado por el mismo riesgo de siempre (referenciar columnas de vigencia que la tabla no declara).

Antes de cerrar se evaluó — y se descartó — la opción obvia: `DatabaseLookup` puro para "clave natural sin necesidad de generar surrogate". Dos motivos, no uno:
1. **Ya excluido por H23/R9** — `DBLookup` falla la introspección de metadata contra el pooler de Supabase en este entorno, motivo por el que D16 (arriba) ya lo excluye explícito del rol `fact_lookup` junto con `DimensionLookup`/`CombinationLookup` con escritura.
2. **Estructural, no solo de entorno:** una vez que `compute_cut()` separa el loader de la dimensión en su propio `.ktr` (F2/F3), el step de lookup del lado del hecho vive en OTRO archivo — no hay stream en memoria que compartir entre archivos Kettle. `StreamLookup` (el sustituto que sí funciona, H23) necesita su propio `TableInput` que relea la dimensión ya cargada, DENTRO del mismo archivo que el lookup — no puede apuntar a un step de un `.ktr` distinto.

Sintetizar ese `TableInput`+hop nuevos automáticamente en `enforce_dimension_step_policy()` se evaluó y se descartó — sería la primera vez que esa función muta topología (steps/hops) en vez de solo config de un step existente, sin precedente en el archivo y con más superficie de bug que beneficio. **Camino elegido: mismo patrón que cerró H23/R9 (D22) — guía de generación, no reparación automática:**
- `system_etl.txt` — nueva sección "LOOKUP DE FK DEL LADO DEL HECHO — CUÁNDO ESTE STEP NO PUEDE VOLVER A ESCRIBIR [D16]" (junto a "STEP DE DIMENSIONES") instruye al LLM: `scd_type==2` → `DimensionLookup` solo-lectura (sin cambios); `scd_type` 0/1 → `TableInput` (relee la dimensión ya cargada) + `StreamLookup` (match por clave natural), nunca `CombinationLookup`/`DimensionLookup` con escritura ni `DBLookup`. Checklist ítem 24 nuevo.
- `dimension_step_policy.py` (`enforce_dimension_step_policy`, Paso 4) sigue "reporta, no repara" para este caso — sin cambio de comportamiento — pero el mensaje de error ahora apunta al fix concreto (TableInput+StreamLookup, referencia a `system_etl.txt` y a esta decisión) en vez de "revisar a mano (D16, residual)" genérico.

No bloquea F3 (nunca bloqueó, D15). Cierre completo: la ambigüedad de "no hay mecanismo seguro" quedó resuelta — el mecanismo existe (TableInput+StreamLookup), vive en la capa de generación, con el backend como red de seguridad si el LLM no lo sigue.

Tests: `tests/test_dimension_step_policy.py` (6 casos de la sesión original, incluida la reproducción de `err1.ktr`/`err2.ktr`, + 2 asserts nuevos sobre el contenido del mensaje de error del caso scd 0/1).

<a id="d17"></a>
### D17 — F2 (diseño del corte) aprobado por el usuario `[F2]`

**Aprobado 2026-07-23.** El diseño de F2 (`03-plan.md`, reporte del 2026-07-22: matriz R/W, disparadores C1/C1-bis, componentes conexos, excepción self-lookup, orden topológico, validado contra `err1.ktr`/`err2.ktr`) queda aprobado tal como está documentado. Desbloquea uno de los tres prerrequisitos de F3 (los otros dos: F2.5 en código, D16 camino 1 en código — ninguno de los dos escrito todavía).

<a id="d18"></a>
### D18 — H2 (config `string`→`object`) propuesto para adelantarse como fix de raíz de H6, no decidido — requiere spike antes de tocar `ETL_OUTPUT_SCHEMA` `[F1.5]`

**Contexto (2026-07-23):** en vez de parchear H6 (fail-fast en `parse_cfg`) como venía planeado en F1.5, se propuso ir a la raíz — cambiar `config` de string a object en `ETL_OUTPUT_SCHEMA` para que el parseo deje de existir (no hay JSON que fallar al parsear si nunca fue string). Coherente con D2 (no protegemos el string actual porque "hoy funciona").

**Por qué no se implementa todavía, aunque D2 lo permita en principio:**
- `ETL_OUTPUT_SCHEMA` (`etl_output.py:1-13`) ya documenta por qué se descartó: un `config` object abierto sin `oneOf` por tipo de step "would either require a massive oneOf discriminator or would reject valid configs".
- Verificado en código, no en teoría: `AnthropicLLM._sanitize_for_anthropic`/`_enforce_adp` (`anthropic_llm.py:36-57`) fuerza `additionalProperties:false` + `properties:{}` en cualquier nodo `object` sin properties declaradas — un `config` object abierto ya colapsa a `{}` siempre para Anthropic, hoy. No es un riesgo, es un hecho ya reproducible en el código tal como está.
- Arreglarlo bien (no solo evitar el colapso) exige un `oneOf`/`anyOf` discriminado por los ~35 tipos de step que documenta `system_etl.txt:170-414`, cada uno con su propio schema cerrado. Si Gemini (`response_json_schema`) y Anthropic (`input_schema` de tool-use) soportan de forma confiable un discriminador de ese tamaño **no está verificado** — es exactamente el "spike empírico contra Gemini y Anthropic" que este mismo archivo ya tenía anotado en "Deliberadamente no decidido" para H2, antes de esta sesión.
- Si el spike falla para alguno de los dos proveedores, el fallback existente es modo texto + `extract_first_json` (regex) — estrictamente peor que el string tipado actual, no mejor. Cambiar la raíz sin confirmar primero puede empeorar la confiabilidad de generación en producción, no solo fallar en desarrollo.

**Estado: no decidido.** Camino recomendado, no ejecutado todavía: spike acotado (1-2 tipos de step, ej. `TableOutput`) contra Gemini y Anthropic reales antes de tocar el schema completo — confirmar que un object cerrado con properties explícitas no colapsa y valida bien, antes de escribir las ~35 variantes. Mientras el spike no corra, **F1.5 mantiene su alcance original**: fail-fast simple en `parse_cfg` + dedup de las 3 copias (H6), no bloqueado por esta propuesta.

*Por qué D18 y no una edición directa de H2:* cambia si H2 se adelanta o se mantiene pospuesto — decisión de scope y de secuencia, no un dato nuevo sobre el hallazgo en sí.

<a id="d19"></a>
### D19 — F3 punto 1-3 (wiring del corte) cerrado a nivel de servicio; el flujo HTTP en vivo se queda en modo notificación hasta extender `ETLGenerateResponse` `[F3]`

**Contexto (2026-07-24):** al arrancar F3 punto 1 (wiring de `compute_cut()` a `etl_generator.py`, ver `03-plan.md`), apareció un hueco no listado en la sección "Archivos a tocar" del reporte F2: `ETLGenerateResponse` (`backend/app/schemas/etl_schemas.py:119-136`) y el ZIP del frontend (commit `338bff2`) están cableados a exactamente 1 KTR por etapa + 1 `.kjb` (2 archivos + 1 job). Si `compute_cut()` devuelve `groups>1` en una etapa real — exactamente el patrón de `err1.ktr`/`err2.ktr` (H21), el caso que motivó todo el refactor — no hay dónde poner los archivos extra en la respuesta HTTP.

**Decisión (confirmada por el usuario, alcance de sesión):** separar "capacidad de servicio" de "entrega por HTTP". Esta sesión implementó y probó a nivel de servicio (`etl_generator.py`/`lineage_builder.py`) la partición real: `split_ktr_by_cut()`, `_build_ktr_stage()` (llama `build_ktr()` una vez por grupo), `_build_job_plan()` generalizado a N por etapa (jerarquía de 3 niveles, F2.5/H7), `stitch_lineage_many()` generalizado a M archivos. Todo esto es código-listo y probado (`test_fragmentation_wiring.py`, 13 tests) pero el flujo HTTP en vivo (`_build_response_from_two_ktr_data`/`_build_response_from_data`) **no** invoca `_build_ktr_stage()` para partir de verdad — solo llama `compute_cut()` para sus notificaciones. Si detecta `groups>1`, entrega el `.ktr` sin partir + un `Validacion(tipo="error")` explícito señalando la tabla y los steps en conflicto, en vez de fallar en silencio o dropear archivos.

**Por qué no se resolvió el hueco de `ETLGenerateResponse`/frontend en la misma sesión:** es un cambio de contrato público (schema de respuesta + consumidor del ZIP en el frontend), de otro orden de magnitud que "llamar `build_ktr()` una vez por grupo" — amerita su propio diseño (¿lista de KTRs? ¿mantener los 2 slots históricos + un array de "extras"?) y su propia sesión, no una decisión de paso mientras se wireaba el corte.

**Efecto inmediato, sin esperar la extensión del schema:** todo pipeline de generación real ahora corre `compute_cut()` (antes no corría en absoluto) — un ETL que hoy dispara C1/C1-bis (carrera/doble-escritor, el bug de origen del refactor) sale con un `Validacion(tipo="error")` explícito en vez de silencioso. Es una mejora de diagnóstico entregada ya, independiente de cuándo se resuelva el hueco.

**Estado: F3 sigue "EN CURSO"**, no cierra hasta que el hueco de arriba se resuelva (ver "NO hecho" en el estado de F3, `03-plan.md`) y corra un test de integración end-to-end contra el pipeline HTTP completo con un caso que dispare un corte real.

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

**Consecuencia sobre D19 y `03-plan.md`:** el hueco que D19 dejaba abierto (qué forma tiene la respuesta) queda **diseñado, no implementado**. F3 sigue "EN CURSO" — no cierra hasta que la implementación backend del punto 5 esté en código y probada end-to-end (ver "NO hecho" en `03-plan.md`; esos puntos no cambian de contenido, solo se resuelve la pregunta de diseño que bloqueaba empezarlos).

*Por qué D20 y no una edición directa de D19:* D19 documentó el hueco cuando apareció, a mitad de sesión, sin la información para cerrarlo. D20 es la sesión siguiente cerrando esa pregunta con datos del usuario — mismo patrón que D16→"resuelto 2026-07-23", se separa para que quede trazable qué se sabía en cada momento.

**Backend implementado 2026-07-24 (sesión 3).** `ETLGenerateResponse` (`etl_schemas.py`) reemplazó `ktr_xml`/`ktr_filename`/`ktr2_xml`/`ktr2_filename`/`kjb_xml`/`kjb_filename` por `etapas: list[EtapaOutput]` (`ArchivoKtr{xml,filename}`, `EtapaOutput{tipo:"ktr"|"kjb", archivo?, kjb?, archivos[]}`) + `kjb_master: ArchivoKtr|None`, exactamente como quedó diseñado arriba. `_build_response_from_two_ktr_data`/`_build_response_from_data` (`etl_generator.py`) dejaron de llamar `build_ktr()` directo y ahora pasan por `_build_ktr_stage()` → cuando `compute_cut()` detecta `groups>1` en una etapa, esa etapa sale como `tipo="kjb"` con sus N archivos reales, no como un `.ktr` sin partir con una advertencia (el hueco que D19 dejaba). Sin período de convivencia (D4/D20-punto2): el shape viejo desapareció del todo — **el frontend actual no puede leer una respuesta nueva hasta su propia sesión** (D20-punto5, no tocado acá).

Dos bugs reales encontrados y corregidos al conectar el corte de verdad (invisibles mientras `compute_cut()` solo generaba notificaciones, D19):
1. **`build_ktr()` prioriza `ktr_data["name"]` por sobre el nombre pasado por parámetro** (`build.py:188`). `split_ktr_by_cut()` copia `{**ktr_data, "steps":..., "hops":...}` preservando `"name"` sin cambios en cada sub-dict — sin fix, los N archivos de un corte real comparten el mismo `<name>` interno y el mismo filename (el modelo siempre manda `ktr.name`, `ETL_OUTPUT_SCHEMA` lo exige). Fix en `_build_ktr_stage()` (`etl_generator.py`): pisa `sub["name"]` con el nombre por-grupo antes de llamar a `build_ktr()`, solo cuando hay más de 1 grupo.
2. **`compute_cut()` separaba en archivos distintos cualquier par de componentes de hop desconectados, incluso sin ninguna señal estructural entre ellos** — contradecía la doctrina que el propio docstring del módulo ya declaraba (D6-bis: "componentes sin tabla-disparadora se agrupan todos juntos"), pero el código no lo implementaba: cada componente conexo se devolvía como su propio grupo sin condición. Invisible mientras el corte no se aplicaba de verdad. Caso real que lo dispara: 2 tablas de origen independientes cargando 2 tablas de staging independientes (sin ningún hop entre las dos ramas) — el caso más común de un ETL con más de una tabla de origen. Fix en `compute_cut()` (`fragmentation.py`): los componentes sin ninguna `trigger_edge` se fusionan en un único grupo adicional; solo los componentes conectados por una relación de tabla real (C1/C1-bis) se ordenan y separan.

Tests: `test_etl_generate_response_shape.py` (nuevo, 5 casos — split real en `_build_response_from_two_ktr_data`/`_build_response_from_data`, round-trip JSON del contrato, rechazo de `tipo` inválido, end-to-end HTTP contra `/api/v1/etl/generate-from-inference` con un caso que dispara corte real) + 2 casos nuevos en `test_fragmentation.py`/`test_fragmentation_wiring.py` cubriendo el bug de componentes desconectados sin señal. Suite completa corrida en frío: mismos 45 fallos preexistentes de antes de esta sesión (2 bugs no relacionados en `test_ktr_xml_validator.py`/`test_structured_outputs.py`, 6 en `test_ktr_build_job_api.py` por un bug preexistente y no relacionado de `ConnectionsMapRequest`/`InlineConnection` — el test manda un `connection_id` string donde el schema espera un objeto `InlineConnection`, sin tocar en esta sesión —, y 37 en `test_api.py` por apuntar a un servidor real en `localhost:8000` que no corre en CI), cero fallos nuevos.

**F3 sigue "EN CURSO"** — falta D20-punto5 (frontend: consumir el nuevo shape + ZIP con carpetas), sesión aparte.

<a id="d21"></a>
### D21 — C.6 resuelta: política ante FK no resuelta = miembro inferido, implementado sin reabrir D16 `[F4]`

**Contexto (2026-07-24):** el usuario trajo la práctica estándar de Kimball para este caso (`fact_venta.fk_producto` NOT NULL, `id_producto` de la venta ausente del maestro en el momento de la carga) — tres políticas posibles, con criterio explícito de cuándo usar cada una.

**Decisión — miembro inferido (inferred member) como política de negocio para R5-b/R11/C.6:**
- El lookup nunca devuelve NULL. Si `id_producto` no matchea, se crea al vuelo una fila placeholder en `dim_producto`: `sk_producto` nuevo, la clave natural real (`id_producto`, ya conocida desde el hecho), atributos con default ("Pendiente"/"Desconocido"), flag `inferred_member='Y'`. El hecho inserta con esa FK válida — sin pérdida de fila, NOT NULL satisfecho.
- Cuando el producto real llega en un batch futuro, overwrite tipo 1 sobre esa misma fila: el `sk` no cambia, los hechos ya cargados quedan enlazados retroactivamente sin reproceso.
- Criterio de cuándo aplica cada política (de negocio, no técnico): **miembro inferido** es el default para hechos que deben reportarse aunque la dimensión no exista todavía (caso normal de ventas). **Miembro desconocido único** (`sk=-1`/`sk=0`) se reserva para claves genuinamente nulas/inválidas en el origen, no para "todavía no llegó" — pierde la clave natural, no se puede reconectar después. **Rechazo/cuarentena** (R11, ya validado en la bitácora vía Sol02) solo si la política de negocio prohíbe explícitamente hechos con dimensión incompleta.

**Choque encontrado con D16 (cerrada, código ya shippeado) — resuelto sin reabrirla:** la implementación nativa de Pentaho para este patrón (step único `Dimension Lookup/Update` en modo `update=Y`, directo en el stream del hecho) es exactamente el step/rol que D16 prohíbe:
- `dimension_step_policy.py:190-227` fuerza cualquier step en rol `fact_lookup` a `DimensionLookup` + `update="N"` — lo reescribiría de vuelta a solo-lectura, neutralizando el placeholder en silencio.
- `fragmentation.py:46-47` clasifica `DimensionLookup` con `update="Y"` como `"RW"` — combinado con el loader dedicado de `dim_producto` (otro step, otro writer), dispara C1-bis (doble escritor), la señal que el propio refactor existe para eliminar.

**Camino de implementación — corregido en la misma sesión (steps separados descartado, ver abajo por qué).** Primer intento (`StreamLookup` → `FilterRows sk IS NULL` → Insert dedicado en el lado del hecho → merge) quedó descartado tras revisar `compute_cut` en detalle: el Insert dedicado es un **segundo writer real** de `dim_producto` (el loader ya es el primero). `compute_cut` (`fragmentation.py:149-188`) sí detecta esto como C1-bis, pero:
- Si loader e Insert-dedicado caen en componentes de hop distintos (caso esperado, igual que `err1.ktr`/`err2.ktr`), el edge de orden entre ambos (`fragmentation.py:183-188`) se arma en el orden de `enumerate(writers)` — orden de aparición en la lista `ktr_data["steps"]` del JSON, **no** el orden de ejecución real (eso lo da `hops`). Nada garantiza que el loader aparezca antes que el Insert-dedicado ahí — si el LLM los emite al revés, el topo-sort fuerza fact-antes-que-loader en silencio, exactamente al revés de lo que necesita miembro inferido.
- Si por algún motivo caen en el mismo componente, la excepción self-lookup (`fragmentation.py:158-174`) tampoco lo cubre: exige que el lector (`Lookup Dim Producto`) tenga camino dirigido hacia **todo** writer, y no lo tiene hacia el loader dedicado (rama distinta) — cae a "revisar a mano", bloqueando el corte automático.

Ninguna rama de `compute_cut` deja esta versión blindada — relocaliza C1-bis en vez de resolverlo, tal como se identificó al revisar la decisión.

**Camino corregido — pasada previa, un único writer de `dim_producto`:** antes del loader, un step de anti-join contra `dim_producto` (SQL directo — `TableInput`/`ExecSQL` sin `table` propia en `cfg`, ya excluido de la matriz R/W por diseño, mismo trato que cualquier SQL arbitrario, D15) obtiene las claves naturales de `staging_ventas` que todavía no están en la dimensión. Esas filas (clave natural real + atributos default/"Pendiente" + `inferred_member='Y'`) se unen (`Union`) al stream real de `staging_productos`, y **ambos alimentan el mismo step único "Cargar Dim Producto"**. Resultado:
- `dim_producto` tiene exactamente un writer en todo el KTR — `len(writers)==1`, C1-bis no puede disparar para esa tabla, sin depender de ningún orden incidental.
- Solo dispara C1 (loader W, `Lookup Dim Producto` R) — el mismo split de siempre, ya validado contra `err1.ktr`/`err2.ktr`: loader antes que el hecho.
- El lookup del lado del hecho (`StreamLookup`) queda R puro — D16 satisfecho sin excepciones ni casos de borde. Como el loader ya garantiza (por construcción, antes de que el hecho corra) que toda clave natural de la venta está en `dim_producto`, ese lookup nunca debería fallar por match — no hace falta ningún patrón de filtro/insert del lado del hecho.

**Detección implementada 2026-07-24 (F4/D22) — la parte que el backend puede resolver determinísticamente.** `etl_generator.py`: `_dims_with_inferred_member(dwh_ddl, dim_contracts)` reusa `ddl_adapter.parse_ddl()` (mismo parser que `_dim_contracts_anomaly_warning`, cero parsing nuevo) para cruzar columnas `is_foreign_key AND constraints.required AND references` de `dwh_ddl` contra `dim_contracts[].table` — sin código de detección propio de FK que escribir, ya vivía en `CanonicalField`. Resultado inyectado en el prompt STG→DWH (`_build_prompt_from_inference`, único punto de armado, sin duplicación) como sección nueva `## DIMENSIONES CON MIEMBRO INFERIDO OBLIGATORIO`, hermana de `## CONTRATOS DE DIMENSION` — vacía y sin efecto en el caso común (ninguna FK NOT NULL hacia una dimensión del contrato). `_inferred_member_notifications()` agrega un warning accionable por dimensión afectada al registro de deltas (D13/D15), en los dos call sites (`generate_etl_from_inference`, `generate_etl_async`).

**Emisión del step (anti-join + Union) — resuelta como regla de prompt, no código backend.** Criterio de F4/D22 (ver esa decisión): sintetizar en Python un `TableInput` con SQL de anti-join + un `Union rows` + rewiring de hops es una síntesis de grafo desde cero — más riesgoso que lo que `enforce_dimension_step_policy` hace hoy (que solo corrige tipo/flags de un step YA existente, nunca inventa steps nuevos). El LLM ya arma el resto del grafo del KTR; describirle el patrón exacto (`system_etl.txt`, bloque "PATRÓN MIEMBRO INFERIDO" — anti-join `NOT EXISTS`/`LEFT JOIN`, atributos default + `inferred_member='Y'`, `Union` hacia el ÚNICO loader, checklist ítem 23) es consistente con cómo se resuelve todo el resto del contenido SQL/config (D12). **Red de seguridad sin trabajo nuevo:** si el LLM arma mal el patrón y deja un segundo writer real sobre la dimensión, `compute_cut()`/C1-bis (F2/F3, ya en producción) lo detecta igual que cualquier doble-escritor — separa en 2 KTR+KJB o emite `Validacion(tipo="error")` (D19/D20). No se escribió un validador nuevo para este caso: la fragmentación ya es el backstop.

Tests: `tests/test_inferred_member.py` (13 casos — detección con FK NOT NULL/nullable/fuera de contrato/dim_contracts vacío/DDL vacío/DDL inválido; formato de sección y notificaciones vacío-vs-poblado; contrato expuesto hacia el prompt en los 3 modos, incluida ausencia en `origen_stg`).

**Sigue sin cubrir, fuera de alcance de esta detección:**
- Confirmar que el loader dedicado de la dimensión (SCD1/upsert por clave natural) sobrescribe correctamente la fila placeholder cuando el producto real llega — depende de que ese loader sea upsert, no insert-only; verificar contra `scd_type` de cada dimensión en `dim_contracts`. Sin código nuevo identificado — a confirmar con una corrida real.
- No cubre dimensiones sin FK NOT NULL del lado del hecho (ej. `dim_tiempo`, ya tratada por V2/D15 como caso de integridad distinto, no de política de default).

*Por qué D21 y no una edición directa de C.6:* mismo patrón que D16→"resuelto"/D19→D20 — la pregunta se registró en `Abiertos` cuando apareció sin la información para cerrarla; esta sesión la cierra con datos concretos (la práctica de Kimball que trajo el usuario + la verificación contra el código ya shippeado). Se separa para que quede trazable qué se sabía en cada momento.

<a id="d22"></a>
### D22 — F4 arranca: "estrategia de fix" no es una elección única, se resuelve por ítem; triage completo, 3 gaps reales cerrados por prompt `[F4]`

**Contexto (2026-07-24):** F4 (`03-plan.md`) tenía como parte de su propio objetivo "decidir estrategia de fix (derivación determinista desde `dim_contracts` vs. parche de prompt)" — a diferencia de F2/F3/D16/D21, esa pregunta nunca se cerró con una regla. Arrancar F4 sin cerrarla primero significaba tocar código a ciegas en 8 frentes con naturaleza distinta (contenido SQL, código backend nuevo, verificación pendiente de ejecución, alcance sin definir).

**Resuelto — no es una sola estrategia, es un criterio de ruteo por ítem, ya implícito en cómo se resolvió todo lo anterior (D6 vs. D12):**
- Si el fix depende de información que YA vive determinística en el backend (`dim_contracts`, DDL parseado, grafo de hops) y previene un error estructural (race, doble escritor, violación de `NOT NULL`) → código backend, mismo patrón que D16/D21.
- Si el fix es contenido SQL/config que hoy arma el LLM dentro de lo que el catálogo permite (dialecto, patrón de dedup, elección de step por comportamiento de entorno) → prompt (`system_etl.txt`), reforzado por el checklist de verificación que ya existe ahí.

**Triage de los 8 ítems de intake de F4 (R4/R6/R8/R10/R12/H23/R5-b/R11) + los 6 puntos originales del handoff, contra el prompt real (no contra memoria):**

| Ítem | Resultado | Evidencia |
|---|---|---|
| R4 — default de `COALESCE` tipado igual que la columna | **Ya cubierto, cerrado sin cambio.** | `system_etl.txt` K17/checklist-20 ya exige literal del mismo tipo (string/numérico) al envolver en `COALESCE` — la regla ya existía antes de que F4 arrancara. |
| R6 — alinear tipos de clave en lookups contra el DDL | **Ya cubierto, cerrado sin cambio.** | `system_etl.txt` regla (e) + checklist-16 ya exigen `SelectValues.cast` explícito antes de cualquier `keys`/`stream_field` con tipo distinto entre capas. |
| R10 — `dim_tiempo` como calendario contiguo vía `generate_series` | **Ya cubierto, cerrado sin cambio.** | `system_etl.txt` K18 ya instruye el patrón completo (no cargar automáticamente, warning con `generate_series`, fila "unknown" sk=0, default en el `DBLookup`). |
| R8 — clave natural también como `value` (`update=N`) en `InsertUpdate` de dimensión | **Gap real, cerrado esta sesión (prompt).** Extiende H16. | Regla B16 + ejemplo + checklist-21 agregados a `system_etl.txt` (bloque `InsertUpdate`). |
| R12 — dedup de staging vía `DISTINCT ON (...) ORDER BY ... DESC` | **Gap real, cerrado esta sesión (prompt).** | K19 + checklist-22 agregados a `system_etl.txt`. |
| H23 — `DBLookup` falla introspección contra pooler de Supabase, preferir `StreamLookup` | **Gap real, cerrado esta sesión (prompt).** | Nota agregada junto al bloque `DBLookup` de `system_etl.txt`: preferir `StreamLookup` para la FK de una dimensión cargada por el mismo `ktr`; reservar `DBLookup` para tablas que este `ktr` no carga. |
| D12 (dialecto) — punto de notificación obligatorio | **Gap encontrado y cerrado de paso.** D12 exige notificar cuando se emite SQL dialecto-dependiente desde 2026-07-22, pero `system_etl.txt` no tenía ninguna regla pidiéndolo — verificado por grep, cero ocurrencias de "dialecto"/"Postgres" en el prompt antes de esta sesión. | K19 (nueva) fija Postgres como default, cross-referencia R4/R10 (ya cubiertos) + R12 (nuevo), y exige `validaciones` tipo `"info"` declarando la construcción dialecto-específica. |
| R5-b/R11 (D21) — anti-join + `Union` hacia el loader único (miembro inferido) | **No implementado — el ítem grande de F4.** Diseño ya cerrado por D21, pero es código backend nuevo (detectar FK NOT NULL de un hecho contra una dimensión desde `dwh_ddl`, emitir 3 steps + rewire), no una corrección de prompt ni de una línea. Requiere su propia sesión de diseño de implementación antes de tocar código — mismo criterio que exigió F2 antes de F3. | Sin código todavía — ver D21. |
| E3 (mapeo invertido `sk_producto`/`sk_tiempo`), key vacía en `CombinationLookup`, E14 (`Number` vs `BigNumber`) | **Desbloqueado y verificado 2026-07-25.** E3 no era bug de contenido del LLM — causa raíz real en `output.py` (`_step_InsertUpdate`/`_step_Update`, `<value><name>`/`<rename>` invertidos vs. formato real de Kettle), **corregida en código** + test de regresión, sin depender de ninguna corrida puntual. Key vacía — no reproducida en corrida fresca. E14 — **confirmado vivo**, queda como gap de prompt (contenido del LLM, no backend), mismo criterio de ruteo de esta decisión. | Ver H9, `01-hallazgos.md` (sección actualizada 2026-07-25). Test: `backend/tests_manual_llm/test_h9_h10_live_scenario.py` (manual, fuera de `tests/`, consume API — no correr en CI). |
| E1/E2 (SelectValues solo-cast no ejercitado, SCD2 declarado no ejercitado) | **Desbloqueado y verificado 2026-07-25.** Ambos ejercitados en corrida fresca (forzando `dim_producto` a `scd_type=2` sobre `categoria`) sin encontrar defecto asociado. | Ver H10, `01-hallazgos.md` (sección actualizada 2026-07-25). Mismo test que la fila de arriba. |
| Validador de contrato staging→DWH | **Alcance cerrado 2026-07-25 — ver D23.** No implementado todavía. | — |

**Consecuencia sobre el plan:** F4 pasa a "EN CURSO" — 3 gaps reales cerrados (R8, R12, H23) + 1 gap transversal cerrado (D12/K19), 3 ítems confirmados ya resueltos antes de esta sesión (R4, R6, R10) sin necesidad de tocarlos. **Actualizado 2026-07-25:** E3/key-vacía/E1/E2 verificados con corrida fresca — E3 tenía causa raíz real de código (`output.py`), ya corregida; key vacía no reprodujo; E1/E2 quedaron ejercitados sin defecto. E14 recibió regla de prompt (B17, `system_etl.txt` — checklist ítem 25) + `MONEY_FIELD_HINTS` extendido en `error_catalog_checks.py` para que el checker automático alcance el mismo vocabulario que la regla — **queda en debe: la regla NO se re-verificó con una corrida real todavía** (la corrida que confirmó E14 vivo fue ANTES de agregar B17). Validador de contrato con alcance cerrado mas no implementado (D23). Queda abierto, bloqueado por diseño pendiente: R5-b/R11 (necesita sesión de diseño de implementación, sin cambios esta sesión).

**B17 no implica retrabajo de fases anteriores:** es contenido de prompt puro (mismo ruteo que R8/R12/H23 arriba — "contenido SQL/config que arma el LLM dentro de lo que el catálogo permite → prompt"), no toca fragmentación (F1-F3), `compute_cut()`, derivación de `dim_contracts` ni ninguna estructura de backend. El fix de E3 (`output.py`) y la extensión de `MONEY_FIELD_HINTS` tampoco — son correcciones de builder/checker aisladas, sin relación con las fases de corte.

**Deuda técnica nueva registrada por el cierre de E14 — H27/H28 (`01-hallazgos.md`):** B17 asume, sin verificar contra código/documentación real de Kettle, que (a) los operandos de un `Calculator`/`Formula` deben ser todos `BigNumber` para que el resultado sea confiable (H27 — inferencia de punto flotante general, no confirmada contra el motor real), y (b) que `FIELD_TYPE_SOURCES` (`error_catalog_checks.py`) es el catálogo completo y correcto de steps que declaran `type`/`value_type` por campo (H28 — ya se encontró un hueco concreto: `Constant` no está incluido pese a tener el mismo shape que steps que sí lo están). Ninguno de los dos bloquea B17 tal como quedó escrito (la regla es conservadora, no genera falsos negativos conocidos) — quedan como investigación pendiente, no como fix urgente.

*Por qué D22 y no una fila más en `03-plan.md`:* fija el criterio de ruteo que la fila de F4 dejaba como pregunta abierta ("decidir estrategia de fix") — nivel de decisión de scope, mismo motivo que D14/D16/D20.

<a id="d23"></a>
### D23 — Alcance del validador de contrato entre KTR (writer→reader); cierra el ítem "sin definir" de D22 `[F4]`

**Contexto:** D22 (fila "Validador de contrato staging→DWH") dejó el ítem sin `archivo:línea` ni alcance propio — la frase venía del objetivo original de F4 en `03-plan.md`, sin que ninguna sesión anterior precisara qué compara exactamente. Esta sesión lo cierra.

**Resuelto (2026-07-25):**

1. **Qué compara.** No usa `stg_definition`/`dwh_model` (lo que el usuario declaró) como tercera fuente de verdad. Compara las dos salidas reales del LLM entre sí: lo que el KTR escritor realmente produce sobre una tabla vs. lo que el KTR lector realmente espera leer de esa misma tabla. Corre por cada relación escritor→lector real entre los `.ktr` generados — si hubo fragmentación (F2/F3), no queda atado al par legacy KTR_1/KTR_2: se adapta a N archivos, una comparación por cada arista escritor→lector del grafo de corte.

2. **Qué necesita cada lado — no simétrico.** El KTR productor (ej. Origen→STG) no necesita el DDL del lado que no escribe (DWH) para su parte de la validación; el KTR consumidor (ej. STG→DWH) sí necesita el DDL del lado que lee, además de lo que el productor realmente escribió. Extiende — no reemplaza — K15/checklist-3c (`fields_validate.py`) y V1-V6 (`ddl_validation.py`/`prompt_validacion_src.txt`): esas validaciones existentes se adaptan para correr por-KTR-generado, reusando su lógica en vez de reimplementarla.

3. **Qué valida, mínimo.** Columnas + nombres + tipos entre lo que un KTR escribe y lo que el siguiente lee. NO valida que las reglas de negocio (`business_rules`) se hayan aplicado — hoy nada en el pipeline valida eso: `business_rules` solo entra como texto libre al prompt de `structure_inferrer.py` (líneas 81/135) para dar forma a `stg_ddl`/`dwh_ddl`/`dim_contracts` en el momento de inferir; ningún validador post-generación comprueba que un step implemente efectivamente una regla de negocio. Gap real, distinto, no cerrado por esta decisión.

   **Punto de enganche creado 2026-07-25** (sin implementación real todavía): `validate_business_rules()` (`backend/app/services/validate_business_rules.py`) — stub deliberado, pase libre siempre (lista vacía). Wireado en `etl_generator.py::generate_etl_from_inference`, una llamada por etapa (KTR_1 contra `stg_definition`, KTR_2 contra `dwh_ddl`), ambas contra `reglasNegocio` y los steps ya generados de esa etapa. El enganche existe para que la lógica real se sume después sin tener que volver a decidir dónde ni con qué firma se llama — implementarla sigue siendo trabajo futuro, no de esta sesión.

4. **Severidad — D15 uniforme, sin caso especial.** Todo mismatch detectado (desde un campo puntual con tipo distinto hasta una tabla STG completa sin productor real) se anota como `Validacion` tipo="error"/severidad máxima, mismo canal que V1/V2/K15 ya usan. El `.ktr`/`.kjb` se emite siempre — nunca se bloquea la emisión por esto, tampoco en el caso de corte totalmente descosido. Elegido explícitamente por el usuario en vez de abrir una categoría de bloqueo nueva: consistente con el patrón ya establecido, sin precedente de excepción en el código hoy.

**Consecuencia sobre el plan:** cierra el ítem pendiente de la fila "Validador de contrato staging→DWH" en D22. Diseño de alcance cerrado — implementación no escrita todavía, queda como trabajo de F4.

*Por qué D23 y no una fila más en `03-plan.md`:* mismo criterio que D14/D16/D20/D22 — fija scope que una sesión anterior dejó abierto, antes de tocar código.

<a id="deliberadamente-no-decidido"></a>
## Deliberadamente no decidido

Distinguir esto de lo cerrado evita que alguien lo dé por resuelto:

- **Si el borde tipado de entrada *grande* (H2, schema `string → object`, tipo validado por construcción) va, y en qué fase.** Lo resuelve arquitectura. La pregunta concreta: ¿es habilitador de la fragmentación o una optimización paralela? **Parcialmente resuelto por D14:** para el alcance chico que el corte necesita (H4, H11, H6), no es habilitador — ya está separado en F1.5/F2.5 y no bloquea. Para el alcance grande (H2), la pregunta sigue abierta.
- **El cambio `string → object` en el schema del LLM.** Depende de un spike empírico contra Gemini y Anthropic, no de un criterio.
- **Qué hace el producto ante un raw incompleto en `build-from-raw`.** Hoy el repair loop está desconectado a propósito, con discusión pendiente. Bloquea cuán estricto puede ser ese punto de entrada.
- **El alcance exacto de las reglas de fragmentación.** Depende de D7: primero los casos, después las reglas. D7 ya confirma que los casos existen (ver Verificaciones pendientes) — falta la entrega concreta de su ubicación antes de poder escribir las reglas.
- **El plan de soporte multi-motor SQL.** D12 fija Postgres como default y exige notificación, pero no dice dónde vive la decisión de dialecto, qué construcciones son dependientes de motor más allá de `DISTINCT ON`, ni qué pasa si el usuario cambia de motor después de generar. Requiere sesión propia.

---

<a id="verificaciones-pendientes"></a>
## Verificaciones pendientes

1. ~~Confirmar que nadie del equipo tenga trabajo apoyado en ETLs guardados.~~ **Verificado 2026-07-22: nadie tiene trabajo apoyado en ETLs guardados.** D3 queda confirmado sin condición, desbloquea D10.
2. ~~Re-verificar D6 en frío.~~ **Hecho 2026-07-22** — ver evidencia bajo D6 y D6-bis arriba.
3. ~~Recolectar los casos donde forzar dos archivos falló (D7).~~ **Ubicación entregada 2026-07-22:** `C:\Users\05147\OneDrive\Escritorio\Test_Asistente_ETL\Simplificado\Sol\02\Errores\` — `err1.ktr`, `err2.ktr`. Coincide con el "corpus de regresión" que ya mencionaba el handoff de Fragmentación. Ambos archivos referencian `InsertUpdate`, `DimensionLookup` y `sk_producto` (confirmado por búsqueda de texto, no analizado en profundidad — el análisis de contenido es trabajo de Track F1/F4, no de esta sesión). D7 queda desbloqueado para F2/F3.

---

<a id="abiertos-no-bloquean-el-arranque-del-refactor-sí-bloquean-ítems-puntuales"></a>
## Abiertos (no bloquean el arranque del refactor, sí bloquean ítems puntuales)

<a id="c1"></a>
### C.1 — Plan de variabilidad de dialecto SQL `[F4]`

Postgres queda como default decidido (D12), pero el soporte multi-motor no tiene plan: dónde vive la decisión de dialecto, qué construcciones dependen de motor más allá de `DISTINCT ON`, qué pasa si el usuario cambia de motor después de generar, dónde exactamente se notifica. Requiere sesión y plan propios — información crítica que se fija antes de generar.

<a id="c2"></a>
### C.2 — Contrastar las reglas de fragmentación existentes contra D6-bis `[F2]`

**Resuelto 2026-07-22.** Releídas las reglas de "cuándo fragmentar" en `handoff_fragmentacion_y_errores.md` (sección Fase 2 del prompt, líneas 51-62): C1 (toda tabla que aparece W y R en la misma etapa marca corte), la agrupación en componentes conexos, el ordenamiento por grafo de FK, y los validadores V1/V2/V3 (ninguna tabla W+R en el mismo ktr / todo lookup tiene productor / un solo escritor por tabla). Las cuatro son señal estructural — ninguna depende de cantidad de steps, longitud de archivo, ni legibilidad. **No hay ningún umbral tipo "partir si >N steps" en el material** — no se encontró nada que eliminar.

*Conclusión:* el handoff ya cumplía D6-bis antes de que D6-bis se escribiera formalmente — coincidencia, no verificación previa (el handoff es anterior). Track F2 puede diseñar sobre el criterio C1 + V1/V2/V3 tal como están, sin depurar nada primero. Desbloquea Track F2 en este eje — F2 sigue sin arrancar sin aprobación explícita (ver `03-plan.md`).

<a id="c3"></a>
### C.3 — Verificaciones contra la base real (independiente del dialecto) `[F1/F4]`

```sql
-- ¿existen las columnas que el WHERE/ORDER BY asumen?
SELECT table_name, column_name
FROM information_schema.columns
WHERE column_name IN ('stg_estado', 'stg_fecha_carga');

-- ¿la BD genera el sk ahora que el step ya no lo hace?
SELECT column_name, column_default, is_identity
FROM information_schema.columns
WHERE table_name = 'dim_producto' AND column_name = 'sk_producto';
```

**Resultado (2026-07-22):** la base sí genera `sk_producto` sola —
```json
{"column_name": "sk_producto", "column_default": "nextval('dim_producto_sk_producto_seq'::regclass)", "is_identity": "NO"}
```
Secuencia vía `DEFAULT`, no `IDENTITY`. **Esto solo protege si el `INSERT` omite la columna por completo.** Verificado contra el generador: `_step_InsertUpdate` (`backend/app/services/ktr_builder/steps/output.py:43-63`) arma la lista de `<value>` directamente desde `cfg["fields"]`, sin ningún filtro que excluya una clave técnica/surrogate — si el step que carga `dim_producto` emite un mapeo hacia `sk_producto` (aunque sea con un valor vacío), ese `INSERT` incluye la columna explícita y pisa el `DEFAULT`. La pregunta real no es "¿la base genera el sk?" (sí) sino "¿el step generado por el LLM alguna vez mapea algo a esa columna?" — eso depende del contenido de cada corrida, no es verificable en abstracto. `err1.ktr`/`err2.ktr` (ver D7, arriba) referencian `InsertUpdate` y `sk_producto` — candidatos para revisar esto en concreto cuando Track F1/F4 los analice. No es más "rotura esperando genérica"; es un caso puntual a confirmar contra esos dos archivos.

<a id="c5"></a>
### C.5 — ¿El backend recomienda/emite constraints DDL? (R7, `bitacora_etl_ventas.md`) `[F4]`

L2-E05 (bitácora): `dim_producto` sin `UNIQUE(id_producto)` — el upsert por clave natural funciona igual, pero sin índice único admite duplicados en reprocesos concurrentes. Regla propuesta como R7: "emitir constraints de integridad que el upsert por clave natural asume."

**No es una decisión que esta sesión pueda tomar sola — es superficie de producto nueva.** Hoy el backend **no emite DDL en ningún punto**: `dwh_ddl` es un input (el usuario lo provee), nunca un output. Antes de rutear R7 a cualquier track hay que decidir: ¿el backend alguna vez sugiere/emite `ALTER TABLE`, o se limita a advertir en el canal que ya existe? Camino barato disponible sin abrir superficie nueva: usar el canal de `advertencias_buenas_practicas` (ya existe, ya es advisory-only, D15 ya lo trata como "notifica, no bloquea") para señalar el constraint recomendado como texto, sin que el backend emita SQL DDL real. No aplicado — queda abierto hasta que el usuario confirme el camino.

<a id="c6"></a>
### C.6 — Política de default ante FK no resuelta (R5-b/R11, `bitacora_etl_ventas.md`) `[F4]` — resuelta por D21

L2-E06 (bitácora, marcado ahí mismo como "a decidir"): una venta con `id_producto` ausente del maestro deja `fk_producto` NULL, y `fact_venta.fk_producto` es NOT NULL — el INSERT rompe.

**Resuelto 2026-07-24 — ver D21.** Política = miembro inferido (Kimball): el lookup nunca devuelve NULL, crea placeholder en la dimensión con la clave natural real y se auto-corrige (overwrite tipo 1) cuando el producto llega de verdad. Implementación: anti-join previo (SQL directo, fuera de la matriz R/W) + `Union` hacia el loader único de la dimensión — `dim_producto` conserva exactamente un writer, evita el choque con D16 sin reabrirla y sin depender de ningún orden incidental entre steps. No implementado en código todavía — trabajo de F4.

<a id="c4"></a>
### C.4 — Auditoría retroactiva de cambios no declarados `[Fundamento]`

El material de fragmentación es un **autorreporte de sesión**, no evidencia independiente: describe la división de KTR, pero la pérdida de SCD2 real y tres clases de cambio no declaradas (ver tabla de D9) no salieron a la luz hasta comparar los XML generados, varias sesiones después. Si el documento las hubiera declarado, no habrían sido un hallazgo — eso es justamente lo que D9 (registro de deltas) busca prevenir hacia adelante.

Falta hacerlo hacia atrás: por cada commit que tocó generación de KTR, comparar el mensaje del commit y lo declarado en la documentación contra el diff canónico (mismo método de D9, aplicado retroactivamente, mecánico). **Falta acotar el alcance** — hasta qué commit hacia atrás tiene sentido ir.

*Evidencia de que hace falta un chequeo así:* ya apareció un caso de afirmación no verificada en el material acumulado — se documentó que `_TABLE_FIELD_KEYS` vivía "suelto en `dimension_step_policy.py`"; verificado contra el repo, vive en `ktr_default_validator.py:54` (ver H4 en `01-hallazgos.md`).
