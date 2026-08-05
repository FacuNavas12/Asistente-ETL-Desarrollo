# Investigación — vocabulario de dimensión uniforme y corte visible

**Investigación cerrada, citada desde comentarios de código — no es un plan vigente.** Fase 1 (Kettle, R-K1-R-K6) y las preguntas de Fase 3 (C.10-C.12) están **cerradas y disueltas**: D44-D49 en `decisiones.md`, H41-H47 en `hallazgos.md`. El resultado ejecutado (comportamiento actual) vive en `../referencia/fragmentacion.md`, `../referencia/scd.md` y `../referencia/kettle-comportamiento.md` — este archivo es el registro de cómo se llegó ahí.

---

## Estado de la investigación (marcar acá, no en otro lado)

- [x] R-K1 — `DimensionLookup(update=Y)` con atributos en modo sobrescritura: **upsert puro confirmado.** `version=1`, `date_from`/`date_to` = `min_date`/`max_date` (`1900-01-01`/`2199-12-31 23:59:59.999`, configurable por `min_year`/`max_year`, default `Const.MIN_YEAR`/`MAX_YEAR`) en la entrada nueva; sin nueva versión para atributos `Update`/`Punch through`.
- [x] R-K1b (Q-4) — **`Update` para SCD1.** `Update` y `Punch through` no son intercambiables en general (`Punch through` reescribe TODAS las versiones por clave natural, `Update` solo la vigente por `tk`), pero con una sola versión por clave son indistinguibles en efecto — se elige `Update` porque describe la intención.
- [x] **R-K2 — bloqueante principal, resuelto POSITIVO.** El matching por rango `[date_from, date_to)` resuelve bien el caso degenerado — pero no como D16 asumía: Kettle **nunca** deja `date_to` NULL en el loader (escribe `max_date` = `2199-12-31 23:59:59.999`). El supuesto "`date_to` NULL para siempre" era incorrecto sobre el mecanismo, no solo obsoleto. **Corolario bloqueante nuevo, distinto de la pregunta original:** `checkDimZero` inserta la fila "unknown" con solo 2 columnas (`tk`, `version`) — choca con `date_from TIMESTAMP NOT NULL` sin DEFAULT que exige `prompt_validacion_src.txt:24-26`. Ver H47/C.12.
- [x] R-K3 — `CombinationLookup`: **confirmado, no mantiene atributos no-clave** (documentación oficial Pentaho, explícita). Correcto solo para junk/technical dimension.
- [x] R-K3b (Q-3) — **no existe SCD0 en `Dimension lookup/update`** (los 3 modos con valor versionan o sobrescriben, nunca "no tocar"). Sí existe en `InsertUpdate` (todos los `<value>` no-clave en `update=N`) — con trampa: si TODOS quedan en `update=N` y `update_bypassed` sigue en `N`, el SQL `UPDATE ... SET WHERE` queda vacío y revienta en runtime. Los dos flags se mueven juntos.
- [x] R-K4 (Q-2) — fila "unknown": `tk=0` (estable en 0 solo para Postgres — `BaseDatabaseMeta.getNotFoundTK`, no sobreescrito por `PostgreSQLDatabaseMeta`), **todo lo demás NULL** (no `'DESCONOCIDO'`), se crea **solo** con `update=Y` (nunca con `update=N`).
- [x] R-K5 (Q-1) — **`<unique_connections>` ES el flag real** (`TransMeta.usingUniqueConnections`), no un proxy. Difiere commits, desactiva `use_batch` en silencio, convierte `truncate` en `DELETE FROM` transaccional. `v8_truncate_sin_transaccional` está **invertido**, no aproximado — el caso peligroso es `unique_connections=N`, no `=Y`.
- [x] R-K6 (Q-5) — confirmado textualmente contra `InsertUpdateMeta.getXML()`. Emisor de este repo y V6 alineados, sin acción.

**Las 8 (R-K1, R-K1b, R-K2, R-K3, R-K3b, R-K4, R-K5, R-K6) están resueltas.** Fase 2 puede escribirse — cierro D44/D45/D46 y H41-H47 abajo. R-K2 salió positivo: no hace falta Plan B, la Fase 3 sigue siendo "robustece", no "es el fix". Pero el corolario de R-K2 (`checkDimZero` vs `date_from NOT NULL` sin DEFAULT) es un bloqueante nuevo que ninguna pregunta del checklist original cubría — no cierra con esta sesión, queda como **C.12** en `02-decisiones.md` §Abiertos, con **H47** como su evidencia. D44 se escribe con esta salvedad explícita: el vocabulario uniforme es correcto en diseño, pero **no ejecuta limpio contra el DDL actual en una dimensión vacía** hasta que C.12 se resuelva.

---

## Context

Dos corridas del mismo caso (catálogo de productos) produjeron soluciones estructuralmente distintas: Set B fragmentó la etapa STG→DWH y quedó libre de carreras; Set A no fragmentó y quedó con una condición de carrera silenciosa sobre `dim_categoria` (lectura concurrente con la escritura → `sk_categoria` nula → FK en 0, sin error). El análisis original atribuyó la divergencia a que el vocabulario de steps es libre, y por lo tanto la robustez de cada corrida es "una lotería sobre el estilo del modelo".

**No es lo que pasó, y el diagnóstico real es peor.** Verificado en código:

El tipo de step de dimensión está contratado desde D11/D37 — `derive_dimension_step_type(scd_type)` (`backend/app/domain/scd.py:318`), forzado por `enforce_dimension_step_policy`, y el prompt recibe `step_requerido` ya resuelto en Python (`etl_generator.py:216-249`). Los dos sets divergieron porque **`scd_type` divergió aguas arriba**:

| | scd_type | loader derivado | lookup FK prescrito | visible al corte |
|---|---|---|---|---|
| Set B | 2 | `DimensionLookup(update=Y)` | `DimensionLookup(update=N)` (forzado por policy) | sí → C1 dispara → **corta** |
| Set A | 0 o 1 | `CombinationLookup` | `TableInput`+`StreamLookup` (prescrito por D16, `system_etl.txt:488`) | no → **no corta** |

Set A siguió el contrato al pie de la letra. No es lotería de modelo: **es una rama de nuestro propio contrato que es estructuralmente insegura**, con dos defectos independientes:

1. **`CombinationLookup` no mantiene atributos.** `_step_CombinationLookup` (`ktr_builder/steps/lookups.py:121-135`) emite únicamente `<key>` desde `cfg["keys"]`, `lastUpdateField` vacío. Consecuencia sistémica: **toda dimensión con `scd_type` 0 o 1 que este sistema genera hoy sale como tabla de claves sin descripciones**, inutilizable para reporting.
2. **La rama es matemáticamente incortable.** `CombinationLookup ∈ _ALWAYS_RW` y C1 exige `any(r not in writers)` (`fragmentation.py:152`) → una tabla cuyo único step visible es RW es su propio lector y escritor, inmune a C1; con un solo writer, inmune a C1-bis. Sumado a que `TableInput` no aporta tabla (vive en `cfg["sql"]`, y no está en `TABLE_BEARING_STEPS`) y `StreamLookup` no está en ninguna lista de `_step_rw`, no existe input que haga cortar esa rama.

**El fix de (1) elimina la razón de (2).** D16 rechazó `DimensionLookup(update=N)` para `scd_type` 0/1 porque "sin `date_from`/`date_to` reales para esa dimensión, referenciarlas rompe en runtime". Ese argumento quedó obsoleto por trabajo posterior: `backend/prompts/prompt_validacion_src.txt:24-26` (validación de DDL, "Parte 3") **agrega** `version_field INTEGER NOT NULL DEFAULT 1`, `date_from TIMESTAMP NOT NULL`, `date_to TIMESTAMP NULL` a toda dimensión de `dim_contracts`, y su V3 dice literalmente "obligatorio para TODA dimension listada en dim_contracts, sea scd_type 0, 1 o 2 — no hay excepcion por tipo". Las columnas existen. El motivo del bloqueo desapareció sin que nadie lo notara — pero nadie verificó todavía que el step realmente resuelva bien contra esas columnas cuando son degeneradas. Esa es la pregunta bloqueante (R-K2).

Resultado buscado: vocabulario **uniforme por rol**, donde loader y lookup son los dos `DimensionLookup` (difieren en `update=Y|N`), los dos declaran `table`, los dos entran a la matriz R/W, y C1 dispara siempre que hay una carrera real — sin depender de qué `scd_type` infirió la fase anterior ni de qué modelo corrió.

### Segunda ronda de evidencia — el diagnóstico se confirma y aparece un riesgo nuevo

Un diff entre Set B **pre-fix** (salida cruda del backend) y post-fix devuelve **solo** el bloque `<connection>` y la condición del `FilterRows`. Los dos `DimensionLookup` de carga, los modos `Punch through`/`Insert` por atributo, el `update=N` del lookup, el corte en dos archivos y el `.kjb` intermedio son idénticos byte a byte. **La rama segura la produjo el sistema**, no una corrección humana.

Eso convierte en hecho medido lo que era conjetura: **el mismo caso, mismo backend, sin mano humana, produjo `scd_type` 0/1 en una corrida y 2 en otra** (H44). La semántica de historización del DWH resultante es no determinista respecto del modelo que corre.

**Y de ahí sale el riesgo que este plan abre y tiene que cerrar (S-15).** Hoy la misinferencia de `scd_type` se nota porque la rama 0/1 produce una dimensión sin atributos, visiblemente rota. Unificado el vocabulario, **las dos ramas producen artefactos impecables, bien cortados, con findings limpios y con semántica distinta**: una dimensión que debía ser SCD2 y sale SCD1 pierde historia sin rastro; una SCD1 que sale SCD2 duplica filas por versión y rompe todo conteo que no filtre por vigencia. A-2 era el síntoma que hacía visible la misinferencia — al sacarlo, hay que reponer la visibilidad por otro lado. Fase 2-bis, más abajo.

**Discriminador salida-cruda vs. round-trip de Spoon** (herramienta permanente, no un hallazgo puntual): Spoon al guardar borra los comentarios XML, expande bloques por defecto y cifra el password. `grep -c '<!--'` (1 = crudo, 0 = Spoon) + presencia de `key_for_session_key`/`size_rowset`/`trans-log-table` (Spoon) deciden si un artefacto que llega de un usuario sirve como evidencia sobre el generador.

### Correcciones al material previo (verificadas en código — no citarlo sin esta tabla)

| Afirmación | Realidad |
|---|---|
| §5.2 "`TableInput` sin `table` depende de `recover_table_key`"; "si hubiera resuelto, A habría cortado igual" | `recover_table_key` nunca ve un `TableInput` — no está en `TABLE_BEARING_STEPS` (`contracts.py:296`). No hubo heurística cerca de acertar; el hueco es que `build_rw_matrix` lee solo `cfg["table"]` |
| B-2 path absoluto de Windows = bug de `_build_job_plan` | El backend no puede emitirlo: `build_kjb_xml` hardcodea `${Internal.Job.Filename.Directory}/` en las dos ramas de entry (`job_analyzer.py:374`, `:412`) |
| B-3 password `Encrypted` embebido | El backend nunca emite un password real (`${LAYER}_DB_PASSWORD`, D34). Round-trip de Spoon — confirmado independientemente por el discriminador de arriba |
| §7.12 "no hay validación post-serialización" | `ktr_builder/error_catalog_checks.py` (451 líneas, V4–V13 sobre el XML emitido, con tests) **existe y no está cableada a ningún path de runtime**. V13 es exactamente A-1 |
| §7.9 sobre severidad | `Finding.severity` está estructuralmente muerto: los dos call sites lo aplanan a `str` (`etl_generator.py:213`, `build.py:159`) y `_split_integrity_warnings` promueve **por prefijo de mensaje**. Ni `[Clave de tabla] ` ni las notificaciones de `compute_cut` están en el set → un race detectado llega a la UI como advertencia de buenas prácticas |
| ~~"V6 es exactamente B-1 (mapeo cruzado de `InsertUpdate`)"~~ | **Se retira.** B-1 no era un defecto: en `InsertUpdate` las convenciones están invertidas entre sí (`<key><name>`=stream, `<key><field>`=columna; `<value><name>`=columna, `<value><rename>`=stream), y el mapeo de Set B era correcto. Verificado en este repo: el emisor ya la tiene bien y documenta que **antes iba al revés** (`steps/output.py:61-68`), y V6 la documenta igual (`error_catalog_checks.py:179-184`). El riesgo de un checker invertido (marcaría inválido **todo** output válido, agravado por promover severidad) **no existe acá** — pero es el motivo por el que S-1 pasa a ser gate duro de la Fase 0 |
| A-10 "XML que no pasó por Spoon" como defecto de calidad | Se retira: el XML compacto sin bloques por defecto **es** la salida normal del backend y Kettle rellena defaults |
| "Set B fue editado a mano, su higiene no es atribuible al backend" | Se acota: la mano tocó **solo** `<connection>` y la condición del `FilterRows`. Todo lo demás de Set B es backend |
| §7.8 "untouched_comps a un archivo por componente" | Lo prohíbe D6-bis (corrección, no legibilidad; sin umbrales). Se registra, no se hace |

### Decisiones tomadas
- **Alcance: raíz completa** — se cambia el contrato de dominio, el prompt y la política.
- **D15 se ejecuta, no se supersede** — el `.ktr` sigue saliendo; el finding llega como `Validacion(tipo="error")` en vez de advertencia cosmética. Mismo patrón que D34 para conexiones.
- **Corrida real end-to-end incluida** — `04-verificacion.md:11` está en su tope de 3 reglas de prompt sin verificar; este trabajo toca `system_etl.txt`.

---

## Fase 0 — Red de seguridad (independiente, cero riesgo de contrato)

**Gate duro previo (S-1), antes de promover cualquier severidad:** los artefactos post-fix de la corrida contra `Base_01` (los `.ktr`/`.kjb` que **ejecutaron** con conteos verificados, `fixes_flujo_completo_stg_dwh.md` + `validacion_stg_dwh_catalogo_productos.sql`) tienen que producir **cero** findings de V4–V13. Un checker de XML de Kettle que nunca corrió contra un artefacto que efectivamente ejecutó no es una red de seguridad; con severidad de error, es un bloqueo del propio pipeline. Cualquier V-función que dé falso positivo contra ese golden **no se cablea con severidad `error`** hasta corregirse. Esos artefactos quedan como fixtures permanentes (S-3): negativo de todos los checkers y línea base estructural (cantidad de grupos, tipo de step por rol).

1. **Cablear `error_catalog_checks.py`** al final de `build_ktr` (`ktr_builder/build.py`, después de `validate_ktr_xml` en `:430`): `parse_ktr(ktr_xml)` → V4/V5/V6/V7/V8/V11/V13 → convertir cada `Finding` propio (`rule`/`error`/`step`/`table`/`message`) al canal con severidad. Nace "anota, no aborta", como su docstring anticipa (`:1-9`). V5/V6 necesitan columnas reales por tabla — reusar `required_columns_by_table`, que `build_ktr` ya recibe.
   - **Justificación corregida:** el caso que lo motiva es **A-1** (clave de dimensión vacía), no B-1. Mecanismo exacto: `CombinationLookup` **sí** declara `required_keys=(("keys", ...))` (`contracts.py:354`), así que A-1 no pasó por falta de la clave — pasó con `keys` **presente y entradas de contenido vacío** (`<key><name/><lookup/></key>` con `<returnfield>` poblado). `missing_required_keys` valida presencia, no contenido. V13 (`v13_lookup_key_incompleta`) es exactamente ese hueco.
   - **`v8_truncate_sin_transaccional` queda fuera del cableado con severidad** hasta resolver Q-1/R-K5: usa `<unique_connections>` como proxy declarado, y si resulta ser **el** flag transaccional el checker está invertido, no aproximado — los dos sets lo tienen en `Y`.
2. **Revivir `Finding.severity`.** `_recover_table_keys` (`etl_generator.py:206-213`) y `build.py:152-159` dejan de aplanar a `str` y devuelven los `Finding`; el caller promueve por `severity == "error"`. `_split_integrity_warnings` (`etl_generator.py:49-73`) promueve por severidad cuando la hay, y por prefijo solo para los canales legacy (`FIELD_INTEGRITY_PREFIX`, `CONTRACT_PREFIX`).
   - **Beneficio inmediato ya escrito:** `flag_dead_computed_fields` (H40/D41) ya está en `PRE_EMIT_PASSES` y detecta estáticamente el campo generado y nunca consumido — que es B-5, encontrado en la corrida **comparando métricas después de ejecutar**. Solo le falta que la severidad no muera. Es el argumento de costo/beneficio de esta fase, sin escribir código nuevo.
3. **Notificaciones de corte con severidad.** `compute_cut` devuelve hoy `notifications: list[str]`; pasa a `list[Finding]` (el dataclass de `validators/base.py`) para que "revisar a mano", "ciclo detectado" y V2 lleguen tipados. `_build_ktr_stage` (`etl_generator.py:351-389`) y `split_ktr_by_cut` propagan.
4. **Superficie de usuario (S-14).** Un finding `error` que vive en un panel mientras el `.ktr` se descarga igual que siempre sigue siendo cosmético. Mínimo: los `Validacion(tipo="error")` se muestran distinguidos del canal de buenas prácticas y la descarga exige un reconocimiento explícito. **No** se bloquea la descarga — eso sería revertir D15. Toca `frontend/src/pages/EtlDetail/EtlDetail.jsx`.
5. **Borrar el marker de debug** `logger.warning("### DIMLOOKUP_MARKER — cfg recibido: %s ###", cfg)` (`steps/lookups.py:35`) — loguea el config completo de cada step de dimensión a WARNING en producción.

Archivos: `ktr_builder/build.py`, `error_catalog_checks.py`, `fragmentation.py`, `validators/base.py`, `services/etl_generator.py`, `steps/lookups.py`, `frontend/.../EtlDetail.jsx`.

---

## Fase 1 — Investigación de Kettle (bloquea la Fase 2, no las otras)

El swap de loader no se mergea sobre inferencia. Fuentes válidas: fuente de Kettle o corrida real — el estándar que D36 usó para cerrar H27/H28.

| Id | Pregunta | Por qué bloquea | Si sale negativo |
|---|---|---|---|
| **R-K1** | `Dimension lookup/update` con `update=Y` y atributos en modo de sobrescritura: ¿se comporta como upsert puro (una fila por clave natural, sin versionar)? ¿Qué escribe en `version`/`date_from`/`date_to`? | Es el reemplazo de `CombinationLookup` como loader SCD1 | Se busca el modo correcto — el vocabulario sigue uniforme, cambia cuál |
| **R-K1b** (Q-4) | Para SCD1, ¿`Update` o `Punch through`? Difieren en si se reescribe solo la versión vigente o **todas** las versiones históricas | Cambia el resultado en una dimensión con historia ya acumulada. No es intercambiable | El contrato elige explícito y lo documenta por dimensión |
| **R-K2** | `DimensionLookup` con `update=N` sobre una dimensión de rango degenerado (`date_from` epoch fijo, `date_to` NULL en todas las filas): ¿resuelve la versión vigente o no matchea? | Es el supuesto que D16 dio por roto sin verificar. Habilita el lookup uniforme | **Plan B:** el loader igual cambia (cierra A-2), el lookup de scd 0/1 sigue `TableInput`+`StreamLookup`, y **la Fase 3 pasa de "robustece" a "es el fix"** |
| **R-K3** | ¿`Combination lookup/update` realmente no mantiene atributos no-clave? ¿Para qué caso sí es correcto (junk/technical dimension)? | Pivote del cambio de contrato | Si los mantiene, A-2 desaparece y el alcance se reduce a la Fase 3 |
| **R-K3b** (Q-3, S-9) | ¿Existe algún modo de atributo que signifique "no tocar el valor existente"? `Insert` versiona, `Update` sobrescribe la vigente, `Punch through` sobrescribe todas — **ninguno es SCD0**. Si no existe: ¿es `InsertUpdate` con todos los values no-clave en `update=N` el loader SCD0 correcto, con la SK del DDL? | Mapear 0 y 1 al mismo modo le da a SCD0 semántica de sobrescritura. La rama vieja, con toda su miseria, era insert-only — que es SCD0 correcto | Si el sistema no soporta SCD0, colapsar 0→1 **explícito en el contrato**, nunca en el emisor |
| **R-K4** (Q-2) | La fila "unknown" que crea `Dimension lookup/update`: ¿qué clave técnica recibe, es estable en 0, y se crea también con `update=N`? | La corrida reporta `dim_categoria`=6 (5+`DESCONOCIDO`) y `dim_producto`=7 — el step la crea solo. De eso depende que prescribir `IfNull → 0` sea correcto o casual, **y cuánto de D21 (miembro inferido, "diseño cerrado, código pendiente") queda gratis** | `IfNull → 0` sigue necesitando el miembro sembrado por DDL |
| **R-K5** (Q-1) | ¿`<unique_connections>` **es** el flag "Make the transformation database transactional" (`TransMeta.usingUniqueConnections`) o un proxy? ¿Qué garantiza respecto del `truncate` de `Table output` y de `commit=1000`/`use_batch=Y`? | Si es el flag, los dos sets lo tienen en `Y`, C-3 está mal formulado y **`v8` está invertido, no aproximado** | `v8` queda como advertencia explícitamente aproximada, sin severidad `error` |
| **R-K6** (Q-5) | Confirmar contra `InsertUpdateMeta.getXML()` que `<key><name>`=`keyStream`, `<key><field>`=`keyLookup`, `<value><name>`=`updateLookup`, `<value><rename>`=`updateStream` | **Bajo costo, no bloquea**: el emisor y V6 de este repo ya la tienen así y lo documentan. Es confirmación en fuente de algo ya alineado en dos lugares independientes | — |

`Blocking step` / `Block this step until steps finish` **sale del alcance**: la Fase 3 corta en vez de ordenar dentro de la transformación.

Entregable: entrada H con la evidencia citada (archivo:línea de Kettle, o log de corrida).

### R-K2 en detalle — por qué es la pregunta central y qué pasa si sale mal

**La pregunta:** ¿`DimensionLookup` con `update=N` (modo solo lectura, usado para buscar el FK del lado del hecho) resuelve correctamente la fila vigente cuando el rango de vigencia de esa dimensión es degenerado — `date_from` fijo, `date_to` siempre `NULL`, porque la dimensión nunca versiona de verdad (SCD0/SCD1)?

Es el argumento con el que D16 **rechazó** usar `DimensionLookup(update=N)` para dimensiones sin historial ("sin `date_from`/`date_to` reales... rompe en runtime"), y ese rechazo es lo único que sostiene hoy el patrón `TableInput`+`StreamLookup` que hace invisible la carrera de Set A. Si la respuesta es "sí, resuelve bien", la Fase 2 es directa: un solo tipo de step para todo `scd_type`. Si es "no" o "depende", la Fase 2 no se puede hacer como está diseñada y la Fase 3 pasa a ser el único camino (Plan B).

**El flujo completo hacia el error, si se ignora esta pregunta:**

1. **Por qué existen columnas `date_from`/`date_to` incluso en dimensiones sin historial.** `prompt_validacion_src.txt:24-26` (V1/V3) obliga a que toda dimensión de `dim_contracts` tenga `technical_key`/`version_field`/`date_from`/`date_to` como columnas físicas, "sea scd_type 0, 1 o 2, no hay excepción por tipo" — agregado **después** de que D16 tomara su decisión.
2. **Qué contienen esas columnas cuando la dimensión no versiona de verdad.** Para `scd_type` 0/1 cada clave natural tiene y va a tener siempre una sola fila. El loader (`DimensionLookup update=Y`, atributos en modo sobrescribir) pisa la misma fila — nunca genera versiones nuevas. `date_from` queda fijo (fecha de la primera carga) y `date_to` queda `NULL` para siempre, en todas las filas. Es un rango degenerado: la columna existe, pero no expresa vigencia real.
3. **Qué hace `DimensionLookup(update=N)` internamente.** Está diseñado alrededor de semántica SCD2: recibe clave natural + fecha de referencia (columna de stream, o fecha de sistema si no hay ninguna), y busca **entre potencialmente varias filas** de esa clave cuál está vigente en esa fecha, comparando contra `date_from`/`date_to`. Ese matching nunca se ejerció contra "una sola fila, rango degenerado, `date_to` NULL".
4. **Los tres modos de falla, todos silenciosos:**
   - El matching puede requerir un centinela real de "sin fin" (ej. `9999-12-31`) en vez de `NULL`, no reconocer la fila como vigente, no encontrar match, y devolver la clave técnica de "desconocido" en vez de la real — **sin error visible**.
   - La configuración de cache (`preload_cache`, `cache_size`) está pensada para volúmenes con muchas versiones por clave; puede comportarse distinto con cardinalidad real 1:1.
   - Si loader y lookup quedan en `.ktr` distintos (exactamente lo que la Fase 3 hace a propósito), el lookup puede leer un snapshot de conexión abierto antes de que el loader haya comiteado la fila nueva de esa misma corrida — el mismo tipo de problema de timing que el refactor entero busca eliminar, ahora dentro del step "seguro".
5. **Por qué nada de lo que ya planeamos lo detecta.** Los checkers que se cablean en la Fase 0 (`error_catalog_checks.py`, V4–V13) validan **forma del XML** — que la `<key>` no esté vacía, que el mapeo no esté invertido. Ninguno valida **semántica de ejecución** de Kettle. Un `.ktr` con esta falla sale con XML válido, bien cortado por `compute_cut` (ahora sí visible a la matriz R/W), sin ningún finding — y el FK resuelto queda mal en runtime. Si se ignora R-K2, se cambia "carrera silenciosa, detectable con más trabajo" por "step limpio, bien formado, semánticamente incorrecto, indetectable con lo ya planeado" — peor que el problema original, no mejor.

### Checklist de investigación (Fase 1, consolidado)

Contra el fuente de Kettle (`org.pentaho.di.trans.steps.dimensionlookup`, clases `DimensionLookup.java`/`DimensionLookupData.java`/`DimensionLookupMeta.java`) o corrida real en Spoon/Kitchen. De más a menos determinante:

1. **(R-K2)** Método de resolución de la fila vigente en modo `update=N`: ¿qué algoritmo decide cuál fila es "la vigente" dada clave natural + fecha de referencia? ¿Comparación `date_from <= fecha_ref AND (date_to > fecha_ref OR date_to IS NULL)`, o exige `date_to` no nulo?
2. **(R-K2)** Tratamiento de `date_to = NULL`: ¿rango abierto ("vigente indefinidamente"), o necesita centinela explícito (`2999-12-31`) para reconocer la fila como actual?
3. **(R-K2)** Caso de una sola versión por clave, para siempre: ¿matching sin ambigüedad, o la lógica asume múltiples candidatas y se comporta distinto con exactamente una?
4. **(R-K2)** Fecha de referencia por defecto: con `use_start_date_alternative=N` y sin `date_field` (lo que emite hoy nuestro `steps/lookups.py:76`, `<date><name>` vacío) — ¿usa fecha de sistema de forma confiable, o falla/cambia de comportamiento con el campo vacío?
5. **(R-K2)** Consistencia loader→lookup entre archivos separados: si el loader corre en un `.ktr` y el lookup en otro `.ktr` posterior del mismo `.kjb`, ¿el lookup ve de forma confiable lo que el loader recién comiteó, asumiendo ejecución secuencial no paralela?
6. **(R-K2)** Sensibilidad al tipo de columna: ¿cambia con `timestamp` vs `timestamp with time zone` en Postgres para `date_from`/`date_to`?
7. **(R-K2, prueba empírica si el fuente no alcanza)** En Spoon: dimensión real, una fila por clave natural, `date_from` fijo y `date_to = NULL`, cargada con `Dimension lookup/update` (`update=Y`, atributos "Punch through"). En **otra** transformación, `Dimension lookup/update` (`update=N`) buscando esa clave — confirmar SK correcto tanto para clave ya existente como para clave que el loader acaba de insertar en esa misma corrida del job.
8. **(R-K1/R-K1b)** Loader de dimensión SCD1: ¿modo `Update` (reescribe solo la versión vigente) o `Punch through` (reescribe todas las versiones históricas)? Distinto resultado si ya hay historia acumulada.
9. **(R-K3/R-K3b)** ¿Existe algún modo de atributo que signifique "no tocar el valor si ya existe" — SCD0 real? `Insert`/`Update`/`Punch through` no calzan con esa semántica. Si no existe: ¿`InsertUpdate` con todos los values no-clave en `update=N` y SK del DDL es el loader SCD0 correcto?
10. **(R-K4, Q-2)** La fila "unknown" que `Dimension lookup/update` crea sola: ¿qué clave técnica recibe, es estable en 0, se crea también en modo `update=N`?
11. **(R-K5, Q-1)** ¿`<unique_connections>` es el flag real "Make the transformation database transactional" (`TransMeta.usingUniqueConnections`), o un proxy? ¿Qué garantiza sobre `truncate` de `Table output` y sobre `commit=1000`/`use_batch=Y`?
12. **(R-K6, Q-5 — no bloquea, confirmación de bajo costo)** `InsertUpdateMeta.getXML()`: confirmar que `<key><name>`=`keyStream`, `<key><field>`=`keyLookup`, `<value><name>`=`updateLookup`, `<value><rename>`=`updateStream`.

---

## Fase 2 — Vocabulario contratado por rol (la raíz)

Depende de R-K1/R-K1b/R-K2/R-K3/R-K3b.

1. **`backend/app/domain/scd.py`** — `derive_dimension_step_type(scd_type)` se parte por rol, que es lo que D16 dijo que hacía falta y nunca se escribió del lado del vocabulario:
   - `derive_dimension_loader_step(scd_type) -> str` — `DimensionLookup` para 0, 1 y 2.
   - `derive_fact_lookup_step(scd_type) -> str` — `DimensionLookup` con `update="N"`, para todo `scd_type`.
   - `CombinationLookup` sale de la derivación. El emisor se conserva; solo aparece vía override registrado (`OVERRIDE_STEP_PREFIX`), el mecanismo que ya existe para el caso excepcional.
2. **El modo de actualización es propiedad del atributo, no de la dimensión (S-8).** Una dimensión `scd_type == 2` tiene **las dos** listas: `dim_producto` de Set B es el caso normal, no el borde — `nombre_producto` en `Punch through` y precios en `Insert`. Por lo tanto:
   - la derivación es `(dimensión, atributo) → modo`, no `dimensión → modo`: `attributes_scd2` → `Insert`; `attributes_scd1` → el modo que fije R-K1b;
   - **todo** atributo del contrato sale con `type` explícito;
   - el default del emisor `f.get("type", "Insert")` (`steps/lookups.py:70`) pasa a **error de validación**, no a default silencioso. Hoy un atributo sin `type` se versiona sin que nadie lo diga. Mismo cuidado con `date_from` (default `"fecha_desde"` vs. `fecha_inicio` que emite el DDL, `system_inference.txt:67`).
3. **`ktr_builder/dimension_step_policy.py`** — la rama de reparación se invierte. Hoy el único auto-fix seguro es `DimensionLookup → CombinationLookup` "porque el config es un subconjunto". Ahora es al revés y **no es un recorte**: hay que sintetizar `fields` (desde `attributes_scd1`/`attributes_scd2`), `date_from`/`date_to`/`version_field` — todos en `DimContract`. Sigue siendo config de un step existente, nunca topología (no cruza la línea que D16 puso ahí). `role_of_dimension_step` no cambia.
4. **`backend/prompts/system_etl.txt`** — tres ediciones:
   - `:435-455` "STEP DE DIMENSIONES": la derivación en prosa (`2 → DimensionLookup; 0 o 1 → CombinationLookup`) pasa a la nueva, con el modo por atributo.
   - `:479-498` "LOOKUP DE FK DEL LADO DEL HECHO": se borra la rama `scd_type` 0/1 → `TableInput`+`StreamLookup`. Una sola regla para todo `scd_type`. **Se conserva la exclusión de `DBLookup`** — H23/R9 (falla la introspección contra el pooler de Supabase) es evidencia de log, sigue vigente.
   - Checklist ítem 24 (`:619`) se invierte.
5. **`prompt_validacion_src.txt`** — sin cambios. V1/V3 ya garantizan las columnas; el plan depende de eso. Verificar en la corrida que se aplican.

### Fase 2-bis — Reponer la visibilidad de la misinferencia de `scd_type` (S-15)

Sin esto, la Fase 2 cambia un artefacto visiblemente roto por uno impecable y silenciosamente equivocado. Cuatro mitigaciones, en orden de costo:

1. **Finding informativo por dimensión, con la consecuencia en una línea** — *"`dim_producto` cargada como SCD2: cada cambio de `precio_lista` genera una versión nueva"*. Convierte una decisión invisible en revisable. Costo mínimo, entra sí o sí.
2. **Regla dura: una columna monetaria o de cantidad no puede estar en `attributes_scd2`.** Cierra B-7 (precios versionados en `dim_producto`), y la señal ya existe — `MONEY_FIELD_HINTS` de `v11_monetario_sin_bignumber` (`error_catalog_checks.py:51-54`, extendida por D36).
3. **Confirmación explícita del usuario** del `scd_type` propuesto y del reparto `attributes_scd1`/`attributes_scd2` por dimensión, antes de generar. Es la decisión de diseño del DWH, no un detalle de implementación. Superficie de frontend nueva — evaluar contra el alcance, pero es la mitigación real.
4. **Medir el determinismo** (se ejecuta en la Fase 4): N corridas de la misma entrada, varianza de `scd_type` por dimensión. Si varía **dentro del mismo modelo**, el prompt no tiene señal suficiente y el dato hay que pedirlo — lo que vuelve la mitigación 3 obligatoria en vez de opcional.

### Fase 2-ter — Los otros dos errores de contrato que la evidencia expuso

Los dos son sistémicos (aparecen en los dos modelos) y deterministas, así que no vuelven la correctitud al prompt:

- **`FilterRows` de saneamiento derivado de los CHECK del DDL (S-4, H45).** Set A validó 1 de 3 columnas; Set B crudo, 1 de 3 distinta. El mismo error de completitud en los dos modelos → nivel contrato, no de modelo. **El dato ya está extraído:** D43 (commit `6bfd018`) saca los CHECK del DDL a `minimum`/`maximum`/`enum` del `CanonicalField`, con los constraints nombrados (`ck_dim_producto_precio_lista`) y el tipo de cada columna del mismo lugar. Sintetizar el filtro es el camino completo; el mínimo aceptable es el checker: por cada CHECK de no-negatividad en tabla destino, tiene que existir condición sobre esa columna aguas arriba **con el tipo correcto de la constante** — que cierra además la mitad de A-5 (constante `String` contra campo numérico) que hoy no tiene cobertura.
- **Guard de capa: ningún step de validación de negocio en una etapa cuyo destino es `stg_*` (S-5, H-5).** Set B crudo filtró precios negativos **en `origen→staging`**: `Leer Productos` 10 → `Cargar stg_tienda_producto` 8. Rompe el contrato "truncate+load = copia completa". D42 (commit `850dcdb`) ya sacó las reglas de negocio del prompt de staging; esto es el **backstop determinista** de esa decisión de prompt — destino y tipo de step son conocidos en build-time. Nota: en separación de capas, la salida cruda de Set A fue **mejor** que la de Set B.

---

## Fase 3 — Corte visible (independiente de la Fase 2; obligatoria si R-K2 sale negativo)

Con vocabulario uniforme las dimensiones dejan de ser invisibles — pero `TableInput` y `ExecSQL` siguen invisibles para todo lo demás, y el agujero de C1 con roles RW sigue abierto.

1. **Resolución de tabla por SQL real, no por coincidencia de contenido.** `Table input` en Pentaho se define por SQL: es el caso normal, no la excepción.
   - **El módulo que hoy hace el workaround ya pidió esto por escrito.** `contract_validate._per_file_table_roles` (`:66-72`) resuelve `TableInput` por regex y documenta que **deliberadamente no toca `build_rw_matrix`** porque "ampliarlo ahí cambiaría esa decisión de fragmentación, fuera de alcance de D23". Esta fase levanta esa restricción autoimpuesta y borra el workaround: un solo resolver para los dos.
   - **Restricción de arquitectura, no negociable:** `test_architecture_layers.py:34` registra `services.ktr_builder.fragmentation` como capa pura y `:74` lista `sqlglot` en `INFRA_LIBS`. Por lo tanto `build_rw_matrix(ktr_data, aliases, resolve_sql_tables=None)` recibe un callable (protocolo en `domain/`) y la implementación con sqlglot vive en infraestructura, junto a `adapters/ddl_adapter.py`. Es el primer port real del repo y aterriza a favor de Track A.
   - Extrae el **conjunto** de tablas de `FROM`/`JOIN` (un `TableInput` puede leer varias) y clasifica `ExecSQL` por `TRUNCATE`/`INSERT`/`UPDATE`/`DELETE`/`CREATE` en vez de dejarlo en `_NOT_CLASSIFIABLE`. Reemplaza el regex `_TABLE_RE` de `lineage_builder.py:34-38`.
   - `StreamLookup` deja de ser invisible: su tabla es la del `TableInput` que lo alimenta (`cfg["step"]`). Aunque la Fase 2 retire el patrón, sigue alcanzable por override.
   - SQL no parseable → `Finding(severity="error")` accionable, **no** abort.
   - **Mismo `parse`, columnas gratis (S-7):** validar las columnas proyectadas del `SELECT` contra el esquema conocido cierra A-6 (`bk_producto` leído de `productos`, que puede no existir → fallo duro en runtime), la única observación del análisis con ese riesgo todavía sin cobertura.
2. **Clave de matriz `(connection, table)` normalizada** en vez de `table.lower().strip()` (`fragmentation.py:67`). Cierra C-7 (conexiones lógicas múltiples al mismo destino físico), que es el caso real y valioso, y arregla una asimetría latente: `table_key_recovery._bare()` **quita el schema** al escribir `cfg["table"]` (`:53`) mientras el camino feliz lo deja — dos namespaces en la misma matriz (H43).
   - **`schema` NO entra en la clave todavía (S-10).** En los dos sets `<schema/>` está vacío en todos los steps de BD: la componente sería la cadena vacía para todo y la matriz quedaría igual. Para que sirva hace falta `schema` obligatorio en `dim_contracts` y en el modelo de staging, DDL calificado y el emisor escribiéndolo — alcance propio. Va como **C.11**, no como parte de esta fase.
3. **C1 con RW desdoblado.** Un step `RW` cuenta como entrada en `readers` **y** en `writers` distinguibles, de modo que `any(r not in writers)` deje de ser vacuamente falso. Cierra la inmunidad de toda tabla cuyo único step visible es RW.
4. **Eliminar la exención por camino dirigido.** `_reaches` (`:97-118`) exime el corte cuando toda lectura tiene camino dirigido hacia toda escritura. En Kettle **todos los steps arrancan como hilos concurrentes**; los hops transportan filas, no ordenan efectos de BD. Se elimina, o se restringe a lookups puros que no escriben sobre la tabla leída. Nota: `all()` sobre comprensión vacía es `True`, así que hoy un caso C1-bis-only en un componente pasa exento **y sin notificación**.
   - **Cambio de comportamiento con test que lo afirma:** `test_fragmentation.py:74` `test_compute_cut_self_lookup_insert_new_only_exception_does_not_split` se invierte, documentado como tal.
   - Colateral: `_connected_components` (`:71-94`) ignora `hop["enabled"]` mientras `_reaches` lo respeta — al irse `_reaches`, que los componentes lo respeten.
5. **Hops de datos que cruzan grupos.** `split_ktr_by_cut` (`:275-279`) filtra los hops a los que tienen `from` **y** `to` en el mismo grupo: uno que cruza se descarta y **no se reconecta**. Si es dependencia, correcto; si transporta filas, **se pierden filas sin error**. En Set B no explotó porque los grupos ya estaban desconectados — el camino peligroso está sin probar. Detectar y reportar como error. La materialización (tabla temporal / `Copy rows to result`) va como **C.10**.
6. **Chequeos a nivel etapa, no solo por archivo (S-13).** El entregable de una etapa son N `.ktr` + 1 `.kjb` y nada valida el conjunto: que el orden del job coincida con el topológico del corte, que ningún fragmento lea una tabla que otro fragmento **posterior** escribe, que no se descartó un hop de datos. Es el nivel donde vive la garantía que este refactor promete.
7. **`untouched_comps` se dejan como están** (todos juntos, `:245-247`) — D6-bis explícito. Se agrega un inventario en las notificaciones: qué quedó junto y por qué la matriz no lo vio.

---

## Fase 4 — Corrida real y cierre documental

### Método de verificación: métricas por step, no conteos de tabla (S-11, H-6)

Cita de la corrida: *"El resultado final en el DWH (6 productos válidos) era correcto de casualidad: 2 productos se filtraban en `ktr_1` y los otros 2 en `stg_dwh_2`, sumando los 4 esperados."* **El estado final de la base coincidía con lo esperado con las dos etapas mal.** Lo que destapó el bug fue comparar leídas vs. escritas por step.

Invariantes declaradas, no conteos de tabla:
- `origen→staging`: `filas_leídas == filas_escritas` por tabla — es truncate+load, no admite descarte.
- `staging→DWH`: todo descarte contabilizado y coincidente con el conteo de la rama de rechazo.

### Qué tiene que mostrar la corrida

- `dim_categoria`/`dim_producto` con atributos descriptivos poblados (cierra A-2).
- El corte STG→DWH dispara **con `scd_type` 0/1**, no solo con 2 (cierra A-3 y la divergencia).
- V13 sin claves de dimensión vacías (cierra A-1). Los golden negativos siguen en cero findings.
- `contract_validate` (D38) atrapa A-4 (`stg_fecha_carga` leída por la etapa 2 y nunca escrita por la etapa 1). Si no lo atrapa, ahí hay un hueco real que hoy se da por cubierto.
- Ninguna `Validacion(tipo="error")` inesperada — y las que salgan, visibles como error, no en `advertencias_buenas_practicas`.
- **Correr con el modelo que produjo Set A, no solo con el que produjo B (S-12).** El objetivo declarado es invariancia de modelo; verificarlo con el modelo que ya funcionaba no prueba nada. **Y más de una corrida por modelo** — el output es no determinista y una muestra no distingue "arreglado" de "salió bien esta vez". Esas corridas son también la mitigación 4 de la Fase 2-bis (varianza de `scd_type` por dimensión).
- De paso cierra la fila **B17** de `04-verificacion.md` (ya tiene checker `v11`, solo faltaba una corrida posterior a la regla), liberando presupuesto para la regla nueva.

### Documentación (obligatorio en el mismo turno — CLAUDE.md)

Numeración libre verificada al momento de escribir este documento: **D44–D46**, **H41–H46**, **C.10–C.11**, **T2**. Re-verificar contra `02-decisiones.md`/`01-hallazgos.md` antes de escribir, por si otra sesión ya usó alguno de estos números.

- **D44** — vocabulario de dimensión uniforme por rol + modo por atributo; retira el residual `scd_type` 0/1 de D16 con la evidencia de `prompt_validacion_src.txt:24-26`. **Supersede parcialmente D16**: el criterio de rol y la exclusión de `DBLookup` (H23/R9) se conservan. Marcar D16 en el índice.
- **D45** — corte visible: resolución de tabla por SQL como port inyectado, clave `(connection, table)`, RW desdoblado en C1, exención por camino dirigido eliminada. Cambio de comportamiento del corte con test invertido.
- **D46** — severidad promovida + `error_catalog_checks` cableada + golden negativo como gate: **D15 ejecutada**, no superseded (patrón de D34).
- **H41** — `CombinationLookup` no mantiene atributos no-clave (emisor `lookups.py:121-135` + R-K3). Tag de intake **G-step**, no Track F.
- **H42** — la rama scd 0/1 era matemáticamente incortable. Tag **S**.
- **H43** — asimetría de namespace por `_bare()` (`table_key_recovery.py:53`). Tag **S**.
- **H44** — `scd_type` no determinista sobre la misma entrada, medido por diff entre Set B pre-fix y Set A crudo. Tag **G-step**. Es el hallazgo que justifica la Fase 2-bis.
- **H45** — `FilterRows` de saneamiento incompleto en los dos modelos (1 de 3 columnas, distinta cada uno) → error de contrato, no de modelo. Tag **D-integridad**.
- **H46** — la fila "unknown" la crea `Dimension lookup/update`, `CombinationLookup` no: A-8 (`IfNull → 0` apuntando a una fila que su propia rama nunca creaba) es otro costo de la rama vieja, y hay solape a evaluar con el código pendiente de D21. Tag **D-integridad**.
- **T2** — resolución `step → (connection, table)` con notificación, en una sola casa. Es la abstracción `resolve_step_table()` que T1 pidió y D40 solo adelantó: al centralizarla, los tres `if not table: continue` (`fragmentation.py`, `dimension_step_policy.py`, `fields_validate.py`) se unifican de verdad. **Cierra T1.**
- **C.10** — materialización de hops de datos que cruzan grupos.
- **C.11** — `schema` obligatorio end-to-end (`dim_contracts`, modelo de staging, DDL calificado, emisor) como prerrequisito para que entre a la clave de la matriz y para cerrar el `search_path` no determinista (C-4).
- **`ESTADO.md`** — F4 sigue "en curso" con estos ítems; F3 tiene un cambio de comportamiento posterior a su cierre (citando D45).
- **`03-plan.md`** — tabla Track F, ítems concretos de F4.
- **`04-verificacion.md`** — agregar el método de la Fase 4 (métricas por step, invariantes por etapa) como criterio permanente, y el discriminador Spoon/crudo. Los conteos de tabla final quedan explícitamente descartados como criterio de cierre.
- **Evidencia** — archivar bajo `docs/refactor/` `analisis-fragmentacion-setA-vs-setB.md` y `hallazgos-y-sugerencias-para-code.md`, **con la tabla de correcciones de este documento adosada**.

---

## Qué NO entra (registrado, no hecho)

- **S-6 (validador de contrato entre etapas) — ya existe.** `contract_validate.py` (D38) valida existencia de columna writer→reader entre KTR, y `_per_file_table_roles` ya resuelve `TableInput` por regex. El ítem "sin caso real" de `03-plan.md:102` es sobre **tipos**, no existencia. A-4 debería estar cubierto hoy — se **verifica en la corrida**, no se construye de nuevo. El simétrico (columna escrita que nadie lee) lo cubre `flag_dead_computed_fields` (D41).
- **Enum de tipos de step en `ETL_OUTPUT_SCHEMA`.** El gate ya existe (`build.py:370-374` aborta sin builder) + `test_pdi_step_coherence.py` en CI. Endurecerlo por schema es la sesión de `docs/costo/beneficio de JSON Schemas.md` (D18, requiere spike contra Gemini y Anthropic).
- **Un archivo por componente para `untouched_comps`** — lo prohíbe D6-bis.
- **Nombres de archivo sin timestamp** (`job_analyzer.py:541`) — real, pero es higiene, no corrección, y rompe referencias de jobs ya descargados.
- **Tabla de rechazos y conexión de log inyectadas por plantilla** (C-2/C-5) — superficie de producto nueva, mismo criterio que C.5.
- **Grano temporal en el contrato de hechos** (C-1) — decisión de negocio.
- **`Blocking step` como fallback in-transformación** — se corta en vez de ordenar.

## Impacto sobre el resto del diseño

- **Track A: a favor.** El port de resolución SQL es el primer port real del repo; `domain/scd.py` ya está en la capa correcta, así que la Fase 2 no mueve nada. La Fase 3 cierra T1 con la abstracción que T1 pidió, insumo directo de A2/A3/A4. Ningún archivo cambia de carpeta.
- **`test_architecture_layers.py`** tiene que seguir verde sin relajar el recorte: si la única forma de pasar es agregar `fragmentation` a las excepciones, el diseño del port está mal y se rehace.
- **D6-bis intacto:** ningún umbral nuevo. Todo corte nuevo viene de señal estructural antes invisible.
- **D15 intacto:** ninguna fase agrega un `raise` en el camino de emisión.
- **D42/D43 se apoyan, no se tocan:** la Fase 2-ter es el backstop determinista de D42 y consume lo que D43 ya extrae.
- **Riesgo principal:** si R-K1/R-K2 salen negativos, el vocabulario uniforme no es posible tal como está diseñado y la Fase 3 pasa de "robustece" a "es el fix". Por eso la Fase 1 bloquea solo a la 2.
- **Riesgo que este plan crea:** la Fase 2 saca el síntoma visible de la misinferencia de `scd_type`. Sin la Fase 2-bis, el sistema pasa a producir errores semánticos indetectables en artefactos impecables. **La Fase 2-bis no es opcional respecto de la Fase 2.**

---

## Verificación

**Determinista (suite):**
- `test_fragmentation.py` — tabla con único step RW **sí** dispara C1; `TableInput` por SQL entra a la matriz; `ExecSQL` con `TRUNCATE` clasifica; `test_compute_cut_self_lookup_insert_new_only_exception_does_not_split` invertido con su motivo escrito.
- `test_fragmentation_wiring.py` — hop de datos que cruza grupos produce finding de error; chequeos a nivel etapa (S-13).
- `test_dimension_step_policy.py` — reparación `CombinationLookup → DimensionLookup` con `fields`/fechas sintetizadas del contrato; **`type` explícito por atributo y default del emisor como error de validación** (S-8); override registrado sigue respetado.
- Test nuevo: reproducción del caso Set A (loader `dim_categoria` + lookup FK del hecho, `scd_type` 1) → **debe** producir `groups == 2`. Es el caso de regresión de D7.
- `test_error_catalog_checks.py` — golden negativo: los artefactos verificados de la corrida `Base_01` producen **cero** findings de V4–V13. Gate de la Fase 0.
- `test_architecture_layers.py` y `test_pdi_step_coherence.py` verdes sin relajar límites ni listas congeladas.
- Los 45 fallos preexistentes siguen marcados (D26).

**No determinista (Fase 4):** criterios arriba — métricas por step, dos modelos, N corridas por modelo. Es el único camino para verificar las ediciones de `system_etl.txt`, por definición de `04-verificacion.md`.

**Antes de empezar:** el working tree tiene `frontend/src/pages/CreateETL/CreateETL.jsx` modificado y `frontend/src/pages/CreateETL/utils/tempAutoDownloadRawSteps.js` sin trackear, en la rama `run-pentaho`. Resolver eso primero — la Fase 4 necesita el frontend en estado conocido.
