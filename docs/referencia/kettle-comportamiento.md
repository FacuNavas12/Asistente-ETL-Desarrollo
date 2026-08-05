# Kettle — comportamiento real vs. lo que el emisor escribe

**Referencia, no investigación.** Destila `investigacion-tags-validos-por-step.md` (sesión T, cerrada/append-only — 47 steps auditados contra `readData()`/`getXML()` real de `pentaho-kettle`, clase+línea citada) + R-K5/R-K6 de `investigacion-kettle-RK1-RK6.md` (mecánica general de KTR; R-K1-R-K4/R-K7, específicos de SCD, ya están en `referencia/scd.md`, no repetidos acá).

**Diferencia con la fuente:** T es el inventario tag-por-tag, completo y congelado en el tiempo — sigue siendo la autoridad para el detalle exacto de cada `cfg[...]` y cada tag XML. Este archivo es el estado **actual**: de los 9 bugs con impacto real que T encontró, 8 ya se arreglaron — repetirlos como "abiertos" acá sería doc-vs-código desfasado. Verificado contra código 2026-08-03 (2 fixes spot-checkeados directo en `steps/transform.py` y `steps/lookups.py`, el resto confirmado por commit presente en `git log` de esta rama).

## Autoridad sobre comportamiento de Kettle

Cuando hay ambigüedad sobre qué hace Kettle, el orden de autoridad es:

1. **`readData()` / `loadXML()` / `getXML()` del `Meta` correspondiente en `pentaho/pentaho-kettle`**, citando clase y línea. Única autoridad normativa.
2. **Fixtures de artefactos reales** del repo — contraste, no autoridad. Si difieren de (1), se registra la diferencia; no se elige una.
3. Wiki, Apache Hop, blogs — **no son fuente**. Hop tiene el formato divergido en varios steps.

Sin cita de clase y línea, una afirmación sobre Kettle queda marcada NO VERIFICADA. No se completa por analogía con otro step.

Dos límites de esta regla, no obvios:

- **Kettle es mudo donde no valida.** Acepta cualquier string como nombre de columna; el error aparece recién en runtime contra la base. Para legitimidad de nombres la autoridad es el DDL real, no el `Meta`. Son dos autoridades distintas.
- **Kettle resuelve ambigüedades con silencio.** Un valor no reconocido cae a un default sin aviso (ver "Vocabularios condicionados" abajo) — a veces ese default coincide con un valor legítimo explícito, un centinela que colisiona con un valor real. Copiar ese comportamiento en el emisor sería propagar el mismo riesgo. La regla operativa del proyecto: **leer como Kettle, fallar distinto que Kettle.** Se replica su semántica de lectura para predecir qué va a hacer; el emisor reporta fuerte donde Kettle degradaría callado.

## Bugs con impacto real — 8 de 9 resueltos

| Step | Estado | Qué fallaba |
|---|---|---|
| `CombinationLookup` | **Resuelto** — E-09, commit `7b0a78f` | `<fields><return>` no se emitía: SK sin nombre real, autoincrement forzado a `true`. Verificado en código: `steps/lookups.py:166-169` emite el bloque completo |
| `DataValidator` | **Resuelto** — E-10, commit `9a15593` | `name`/`fieldname` invertidos — Kettle buscaba en el stream la ETIQUETA de la regla, no el campo real |
| `StringOperations` | **Resuelto** — E-04, commit `d0a79b9` | `trim_type`/`lower_upper` como índices numéricos (`"0".."3"`) donde Kettle exige palabras literales — el step nunca hacía nada. Verificado en código: `steps/transform.py:219-227`, `trim_map`/`case_map` con las palabras reales |
| `SplitFieldToRows` | **Resuelto** — E-11, commit `e53387e` | Alias sin el "3" no es plugin id registrado — Spoon marcaba el step "missing" |
| `Unique` | **Resuelto** — E-05, commit `3194463` | Tag real `case_insensitive`, el emisor escribía `case_sensitive` (inexistente, polaridad invertida) |
| `ExcelInput` | **Resuelto** — E-06, commit `58d4e89` | Sin `spreadsheet_type`, Kettle caía al motor legado JXL, que no lee `.xlsx` |
| `JsonInput` | **Resuelto** — E-07, commit `1462d85` | Sin `includeNulls`, comportamiento ante `null` dependía de `kettle.properties` de cada máquina |
| `TextFileOutput` | **Resuelto** — E-08, commit `37e792d` | `create_parent_folder` anidado en `<file>`; Kettle lo lee como hijo directo de `<step>` |
| `GroupBy` clásico | **Congelado** — E-12, sin fix | `all_rows="N"` fijo exige input pre-ordenado por los campos de agrupación; sin esa garantía en el grafo de steps previos, el agregado puede salir silenciosamente incorrecto. No es bug de tag — es precondición del step no garantizada por el grafo. Parked, no bloquea nada hoy |

`DimensionLookup` — los 2 fantasmas que motivaron la investigación anterior a T (stray `<type>` bajo `<field>`, `min_year`/`max_year` ausentes) ya estaban arreglados antes de esta serie; confirmado en T. El vocabulario `<field><update>` condicionado por modo Y/N está en `referencia/scd.md`, no acá.

## Divergencias inocuas — caen a un default equivalente, no tocar

`TableOutput` (9 tags de partición/tablename-dinámico/return-keys, confirmado por fixture real), `Update` (`skip_lookup`, `ignore_flag_field`), `TextFileInput` (filtros de línea, `date_format_locale`, 8 campos adicionales), `Calculator` (`failIfNoFile`, 4 símbolos de formato), `SortRows` (`collator_enabled/strength`, `presorted`), `Constant` (`currency`/`decimal`/`group` — solo importaría para campos Number/Currency/BigNumber, no usados hoy), `FieldSplitter` (`idrem`/`currency`), `ConcatFields` (6 sub-tags de formato heredados, irrelevantes para concatenar strings), `IfNull` (función "reemplazar todos" completa), `ReplaceString` (`replace_field_by_string`, `is_unicode`), `WriteToLog` (`limitRows`), `TableInput` (`cached_row_meta_active`/`row-meta`, Spoon los agrega al guardar), `RowGenerator` (4 tags de "never ending"), `MemoryGroupBy` (6 tags heredados del cuerpo de `GroupBy` que su Meta real nunca lee), `ExcelInput`/`ExcelOutput` (campos de nombre de archivo, `password`).

**Sin ninguna divergencia confirmada** (27 de 47, tag-por-tag y nesting exacto contra fuente real): `DBLookup`, `MergeJoin`, `StreamLookup`, `MergeRows`, `JoinRows`, `InsertUpdate`, `Delete`, `ExcelOutput`, `RowGenerator`, `ValueMapper`, `NumberRange`, `Denormaliser`, `RegexEval`, `AddSequence`, `Formula`, `FilterRows`, `GetSystemInfo`, `GetVariable`, `SetVariable`, `ExecSQL`, `ScriptValueMod`, `Abort`, `BlockingStep`, `Dummy`.

## Sin resolver — riesgo real u observación abierta

- **`JsonOutput.operation_type`** — riesgo latente, no bug confirmado. 3 valores válidos (`outputvalue`/`writetofile`/`both`); `getOperationTypeByCode()` cae al índice 0 (`outputvalue`) ante código no reconocido, **no** al default que el emisor pretende (`writetofile`). Si `cfg["operation_type"]` recibe un typo del LLM, el JSON deja de escribirse a archivo, sin error visible. Sin validación de whitelist antes de emitir.
- **`SelectValues`** — nesting confirmado correcto. Nombres exactos dentro de `<meta>` (`dec_symbol`/`group_symbol` vs. posible `decimal_symbol`/`grouping_symbol` por analogía con `Calculator`) **NO VERIFICADO** — `SelectValuesMeta` resuelve por indirección de reflection, no se encontró la tabla estática legible.
- **`AnalyticQuery`** — lista completa de códigos que acepta `getType(desc)` para `LEAD`/`LAG` **NO VERIFICADA**. El emisor ya fuerza `.upper()` con default `"LEAD"`, sin impacto confirmado.
- **`CsvInput`** — mapeo de claves consistente por convención, pero **NO VERIFICADO** contra el string literal en fuente (resuelve por `getXmlCode()`/reflection, igual que `SelectValues`).

## Vocabularios condicionados — dónde están los centinelas que colisionan con valores válidos

Patrón repetido: una función Kettle resuelve nombre→id, y el id 0 (o el string `"-"`) es **a la vez** un valor legítimo explícito y el fallback de "no reconocido". Un typo del LLM y una elección explícita del usuario quedan indistinguibles del lado de Kettle.

- **`ValueMetaFactory.getIdForValueMeta(nombre)`** — string no reconocido cae silenciosamente a `TYPE_NONE`/id 0, mismo id que `"-"` explícito. Afecta a todo step que declara tipo de valor por nombre: `Calculator`/`GroupBy`/`DataValidator`/`GetVariable` (`value_type`/`data_type`/`type`). Único step de este lote con allow-list propio del lado del emisor: `GetSystemInfo`.
- **`GroupBy.<fields><field><type>`** (aggregate) — `typeGroupCode`: índice 0=`"-"` es tanto "sin agregación" explícito como el fallback de código no reconocido. Un typo del LLM (`"AVG"` en vez de `"AVERAGE"`) cae silenciosamente a "sin agregación" — sin error.
- **`JsonOutput.operation_type`** — ver arriba, índice 0 = `outputvalue`, no el default pretendido.
- **`DimensionLookup.<field><update>` / `ATTRIBUTE_UPDATE_TYPE_CODES`** — ver `referencia/scd.md`. Mismo patrón: string no reconocido cae a modo Insert, no a error.

**Regla operativa del proyecto ante este patrón** (ver "Autoridad sobre comportamiento de Kettle" arriba): *leer como Kettle, fallar distinto que Kettle*. Hoy eso existe para `ValueMetaFactory`→`VALUE_META_TYPE_NAMES` y para `DimensionLookup`; **no existe todavía** para `GroupBy.type` ni `JsonOutput.operation_type` — abierto, sin evidencia de haber ocurrido en una corrida real.

## Mismo concepto, dos nombres de clave `cfg` distintos

**`Calculator` vs. `Formula`** — ambos escriben el mismo trío de tags XML (tipo/longitud/precisión de salida), pero Calculator lee `value_type`/`value_length`/`value_precision` (`transform.py:156-158`) y Formula lee `type`/`length`/`precision` (`transform.py:167,186-187`). Deliberado (`system_etl.txt:369`), no un alias que `normalize_config` resuelva — un validador que asuma un solo juego de nombres es un no-op silencioso para la mitad de los steps que cree cubrir. Ya cableado correctamente en `check_monetary_scale` (`_SCALE_KEYS_BY_CANONICAL`, ver `referencia/contrato-ddl.md`). Único par de este tipo detectado en la auditoría de 47 steps.

## Mecánica general de KTR (R-K5, R-K6 — no específica de SCD)

- **R-K5 — `<unique_connections>` ES el flag real** (`TransMeta.usingUniqueConnections`), no un proxy de otra cosa. Difiere commits entre steps, desactiva `use_batch` en silencio, convierte `truncate` en `DELETE FROM` transaccional. El caso peligroso es `unique_connections=N` (no `=Y`, que sería la lectura intuitiva).
- **R-K6 — `InsertUpdateMeta.getXML()`** confirmado textualmente contra el emisor de este repo — sin acción, alineados.

## Fuente de detalle

Tag-por-tag completo, con clase+línea de `pentaho-kettle` para cada uno de los 47 steps: `investigacion-tags-validos-por-step.md`. No se repite acá — este archivo es el índice de estado, no el reemplazo.
