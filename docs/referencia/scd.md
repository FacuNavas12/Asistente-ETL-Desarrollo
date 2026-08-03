# SCD — qué es, cuándo se aplica, qué implica para el step y el DDL

**Referencia, no investigación.** Fusiona `docs/SCD/{criterios,SCD1,SCD2}.md` (hoy 3 archivos separados, contenido movido acá) + los hallazgos Kettle de `docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md` (R-K1-R-K6, investigación cerrada) + lectura directa de `backend/app/domain/scd.py`. Motivo por el que existía disuelto en 3 lugares: `docs/refactor/30-decision-python-llm.md`.

Verificado contra código 2026-08-03 — todo símbolo citado abajo existe en `domain/scd.py` en la línea indicada (`classify_scd_candidates:172`, `is_calendar_dimension:151`, `derive_dimension_loader_step:359`, `derive_fact_lookup_step:370`, `derive_attribute_update_mode:427`, `detect_history_intent:135`, `ATTRIBUTE_UPDATE_TYPE_CODES:387`). Cuando este archivo y el código diverjan, gana el código (Regla A, `docs/README.md`).

## Dos decisiones distintas, no una (D37)

**A) `scd_type` (0/1/2) por dimensión** — decisión de negocio ("¿un reporte del pasado debe mostrar el atributo como era ENTONCES?"), no derivable solo de los datos. La resuelve el LLM, acotado por un pre-check determinista. `classify_scd_candidates()`.

**B) Qué step de Pentaho carga la dimensión** — 100% derivado de A, nunca juicio del modelo en cada corrida. `derive_dimension_loader_step`, `derive_fact_lookup_step`, `derive_attribute_update_mode`, aplicado por `enforce_dimension_step_policy` (`ktr_builder/dimension_step_policy.py`).

Antes de D37/D11/D44/D51 estas dos preguntas se resolvían por separado y podían discrepar — el síntoma aparecía en runtime (Kettle), no al guardar el `.ktr`. Fijar B como función pura de A cerró esa clase de bug.

## A — el pre-check determinista (`classify_scd_candidates`)

Precedencia, de mayor a menor (razonada completa en D37):

| # | Condición | Veredicto | `forced_scd_type` | Vinculante |
|---|---|---|---|---|
| 0 | Sin clave natural durable **confirmada** (`key_columns_trusted=True` y `key_columns=[]`) | `NO_HISTORY_POSSIBLE` | 1 | Sí, incluso sobre `declared_intent` |
| 1 | Ningún atributo mutable (todo lo no-clave es la propia clave) | `NO_HISTORY_POSSIBLE` | 1 | Sí |
| 2 | Dimensión de calendario (`is_calendar_dimension`) | `NO_HISTORY_POSSIBLE` | 0 | Sí (angosto a propósito) |
| 3 | `declared_intent == "2"` (usuario ya lo declaró) | `HISTORY_DECLARED` | — | Por debajo de 0-2 |
| 3-bis | Origen trae columnas tipo `valid_from`/`current_flag`/`version`/etc. | `HISTORY_DECLARED` | — | D6: la info ya vive en el origen |
| 5 | Resto | `UNDECIDED` | — | Juicio del modelo, techo = `scd2_candidates` |

`key_columns_trusted` distingue "confirmado que no hay clave" (BD/DDL) de "no se sabe" (Formulario/CSV/Excel) — sin esa distinción la regla 0 degradaba a SCD1 casi cualquier ETL armado a mano con origen sin metadata estructural.

`detect_history_intent()` es una señal de **alcance proyecto** (`business_rules` + `process_goal`), no por entidad — a qué dimensión aplica queda como juicio del modelo, nunca automático. Las frases de `_COMPLIANCE_PHRASES` (cierre contable, auditoría, regulatorio...) **prohíben** SCD1 — único caso donde SCD1 no es preferencia sino veto (Kimball 2008).

Entra al prompt de inferencia como bloque `## PRE-CHECK SCD` (`structure_inferrer._build_scd_precheck_block`); `system_inference.txt` § `## SCD: CUANDO 1 Y CUANDO 2` lo declara vinculante para el modelo.

## B — derivación determinista del step (post D44/D51/R-K7)

`derive_dimension_loader_step(scd_type)` y `derive_fact_lookup_step(scd_type)` devuelven **siempre** `"DimensionLookup"`, para todo `scd_type` (0, 1 o 2) — Kettle no tiene Type 0 real (R-K7), y `scd_type==0` colapsa a 1 (mismo step, mismo modo `Update`).

Lo que sí cambia es el modo por atributo: `derive_attribute_update_mode()` devuelve `"Insert"` si el atributo está en `attributes_scd2` (abre versión nueva), `"Update"` en cualquier otro caso — S-8: el modo es propiedad del ATRIBUTO, no de la dimensión.

Del lado del hecho (rol `fact_lookup`, D16): siempre `update="N"` — nunca escribe la dimensión desde el lado del fact, evita doble escritor sobre la misma tabla.

`enforce_dimension_step_policy()` compara esto contra lo que el `.ktr` realmente trae y corrige o reporta la discrepancia.

## Semántica real de Kettle — R-K1 a R-K6 (verificado contra `pentaho-kettle`, detalle completo en `investigacion-kettle-RK1-RK6.md`)

- **R-K1 — upsert puro confirmado.** `DimensionLookup(update=Y)`: `version=1`, `date_from`/`date_to` = `min_date`/`max_date` (`1900-01-01`/`2199-12-31 23:59:59.999`, `Const.MIN_YEAR`/`MAX_YEAR` por default, configurable por `min_year`/`max_year`) en la entrada nueva; sin nueva versión para atributos `Update`/`Punch through`.
- **R-K1b — por qué `Update` y no `Punch through` para SCD1.** No son intercambiables en general (`Punch through` reescribe TODAS las versiones por clave natural, `Update` solo la vigente por `tk`), pero con una sola versión por clave son indistinguibles en efecto — se elige `Update` porque describe mejor la intención.
- **R-K2 — bloqueante resuelto POSITIVO, con corolario.** El matching por rango `[date_from, date_to)` resuelve bien el caso degenerado (SCD1, una sola versión) — pero Kettle **nunca** deja `date_to` NULL en el loader, siempre escribe `max_date`. Corolario: `checkDimZero` inserta la fila "unknown" nombrando solo 2 columnas (`tk`, `version`) — choca con `date_from NOT NULL` sin DEFAULT. Resuelto por D47/DDL-1 (sembrado completo en el DDL) — ver `referencia/contrato-ddl.md` I6/I8.
- **R-K3 — `CombinationLookup` confirmado: no mantiene atributos no-clave** (doc oficial Pentaho, explícita). Correcto solo para junk/technical dimension — por eso sale de la derivación por defecto en B (D44) y solo aparece vía override registrado (`OVERRIDE_STEP_PREFIX`).
- **R-K3b — no existe SCD0 real en `Dimension lookup/update`** (los 3 modos con valor versionan o sobrescriben, nunca "no tocar"). Sí existe en `InsertUpdate` (todos los `<value>` no-clave en `update=N`) — **con trampa**: si TODOS quedan en `update=N` y `update_bypassed` sigue en `N`, el SQL `UPDATE ... SET WHERE` queda vacío y revienta en runtime. Los dos flags se mueven juntos (`<update_bypassed>`, agregado al emisor de `InsertUpdate` — antes no se emitía nunca).
- **R-K4 — fila "unknown".** `tk=0` (estable en 0 **solo para Postgres** — `BaseDatabaseMeta.getNotFoundTK`, no sobreescrito por `PostgreSQLDatabaseMeta`; otro dialecto podría diferir), **todo lo demás NULL** (no `'DESCONOCIDO'`), se crea **solo** con `update=Y` (nunca con `update=N` — el lado `fact_lookup` jamás la siembra).

R-K5 (`<unique_connections>`) y R-K6 (`InsertUpdateMeta.getXML()`) son mecánica general de KTR, no específica de SCD — quedan para `kettle-comportamiento.md`, no repetidos acá.

## Caso especial: dimensión de calendario

Kimball la trata como Type 0 (atributos fijos, derivados de la fecha). Kettle no tiene Type 0 real (R-K7) — el colapso a "mismo step, modo Update" solo es seguro acá porque el ETL **nunca carga** la dimensión de calendario (se puebla aparte, ver `K18` en `system_etl.txt`); el guard que lo garantiza vive en `services/etl_generator.py` y reusa `is_calendar_dimension()`.

## Literales válidos de modo (Kettle)

`ATTRIBUTE_UPDATE_TYPE_CODES` (`domain/scd.py:387`): `Insert`, `Update`, `Punch through`, `DateInsertedOrUpdated`, `DateInserted`, `DateUpdated`, `LastVersion`. Cualquier string fuera de esta lista cae **silenciosamente** en modo Insert (`TYPE_UPDATE_DIM_INSERT`) del lado de Kettle — un typo del emisor ("SCD1", "overwrite") produce un `.ktr` válido que versiona en vez de sobrescribir, sin error ni warning visible. Mismo patrón de colisión-de-sentinel que `ValueMetaFactory` (ver `kettle-comportamiento.md`, todavía sin escribir).

## Contrato de DDL — igual para SCD1 y SCD2, difiere solo el índice

Mismas columnas obligatorias en toda dimensión (D4), sea SCD1 o SCD2 — no hay atajo por tipo:

```sql
sk_<entidad>        SERIAL PRIMARY KEY            -- acepta INSERT explícito de 0 (fila desconocido, I2)
version              INTEGER NOT NULL DEFAULT 1     -- el step lo exige aun en SCD1
fecha_inicio         TIMESTAMP NOT NULL
fecha_fin            TIMESTAMP NULL                 -- NULLABLE siempre (I6), aunque Kettle nunca la deje NULL en la práctica
id_<entidad>_origen  ...                            -- clave natural del lookup (I3)
```

Lo que sí cambia es la forma del `UNIQUE`/índice de la clave natural:

- **SCD1/0 — simple:** `CONSTRAINT uq_dim_<entidad>_origen UNIQUE (id_<entidad>_origen)`.
- **SCD2 — compuesto, nombrado, nunca parcial:** `CREATE UNIQUE INDEX uq_dim_<entidad>_origen_fin ON dim_<entidad> (id_<entidad>_origen, fecha_fin)`. Nunca `WHERE es_vigente`/`WHERE fecha_fin IS NULL` — Kettle escribe `2199-12-31 23:59:59.999`, nunca `NULL` (R-K2); un índice parcial sobre esa condición queda vacío en la práctica.

**Gap abierto, sin dueño en código:** ni `system_inference.txt` (D3) ni `prompt_validacion_src.txt` (V2) condicionan la forma del índice a que `dim_contracts[i].scd_type` sea efectivamente el que corresponde — V2 acepta cualquiera de las dos formas siempre. Caso real: dimensión SCD1 salió con índice compuesto de SCD2, sin aviso de ninguna de las dos fases de LLM. Detalle completo, y el fix recomendado (`natural_key_unique_shape(scd_type)` en `domain/scd.py`, no aplicado): `referencia/contrato-ddl.md` Gap 1 — no se repite acá el análisis, solo el resultado.

## Vocabulario de `dim_contracts`

`table`, `scd_type`, `technical_key`, `version_field`, `date_from`, `date_to`, `natural_keys`, `unknown_key_value`, `attributes_scd1`, `attributes_scd2` — mismo vocabulario que consume el contrato DDL, ver `referencia/contrato-ddl.md` § "Vocabulario de `dim_contracts`".

## Nota de consolidación

Este archivo reemplaza el contenido de `docs/SCD/criterios.md`, `docs/SCD/SCD1.md` y `docs/SCD/SCD2.md` (los 3 quedan intactos en disco, no se borraron en esta sesión — decisión de no tocar archivos fuera del alcance puntual de REF sin pedirlo). Cualquier sesión futura que edite SCD debería escribir acá, no reabrir los 3 archivos viejos.
