# Contrato DDL — hallazgos y correcciones pendientes

**Índice mutable, cuerpo append-only** — mismo criterio que `01-hallazgos.md`: una entrada `DDL-N` se escribe una vez, no se reescribe; una actualización nueva se agrega como párrafo con fecha dentro de la misma entrada. El estado vive en el índice de acá abajo.

**Por qué existe aparte de `01-hallazgos.md`/`02-decisiones.md`:** durante la investigación de vocabulario de dimensión (`03c-investigacion-vocabulario-dimension-kettle.md`) apareció un primer punto de contrato DDL (C.12 → D47) que no era sobre vocabulario de step sino sobre qué exige `prompt_validacion_src.txt` en el DDL generado — y el patrón parecía que iba a repetirse: puntos donde el DDL que el sistema exige/genera diverge de lo que Kettle necesita o de lo que el fabricante recomienda. Este archivo es el punto de acopio de esos puntos, para no diluirlos uno por uno dentro de la investigación de dimensiones ni perderlos sueltos en el chat. **Las decisiones que se tomen sobre estos puntos se escriben en `02-decisiones.md` como siempre (D-numeradas)** — este archivo indexa y da contexto, no reemplaza la fuente de verdad de decisiones.

**Alcance:** cualquier divergencia entre (a) lo que `prompt_validacion_src.txt` (I2-I9/V1-V6, "Parte 3" del DDL — corregido 2026-08-03, decía "V1-V13"; ver `referencia/contrato-ddl.md` para el mapa completo invariante↔dueño) exige generar, (b) lo que Kettle/PDI necesita en runtime para que los steps que este sistema emite no rompan, y (c) lo que el DDL generado por el propio Pentaho (botón *SQL* del step) o su documentación oficial recomienda. No es un catálogo de bugs de `ddl_adapter.py` (eso es H38/D43, `01-hallazgos.md`/`02-decisiones.md`) — es específicamente sobre el **contrato de salida** (qué DDL se le exige/sugiere producir al usuario), no sobre el parseo de DDL de entrada.

---

## Índice

| # | Qué es | Estado | Decisión/hallazgo asociado |
|---|---|---|---|
| DDL-1 | `date_from TIMESTAMP NOT NULL` sin DEFAULT (V1/V3) choca con `checkDimZero` de `Dimension Lookup/Update` — el INSERT de la fila "unknown" (2 columnas) viola el NOT NULL y aborta la transformación en la primera fila | Ejecutado (2026-07-30) | H47 (`01-hallazgos.md`), D47 (`02-decisiones.md`), `investigacion-pentaho-C10-C11-C12.md` §C.12 |
| DDL-2 | Centinelas de rango (`date_from`/`date_to`/`version`) en una dimensión de calendario pre-poblada externamente (K18) — sin los valores exactos de Kettle, el lookup de FK del lado del hecho (`Dimension lookup/update`, `update=N`) no matchea nunca y devuelve la clave "desconocido" para toda fecha, sin error visible | Cerrado (guía de prompt) — D51 | D51 (`02-decisiones.md`), `03c-investigacion-vocabulario-dimension-kettle.md` |

---

## DDL-1 — `date_from`/`date_to` NOT NULL sin DEFAULT vs. `checkDimZero`

**Síntoma:** `prompt_validacion_src.txt:24-26` (V1/V3) exige `date_from TIMESTAMP NOT NULL` (sin DEFAULT) en toda dimensión de `dim_contracts`, sin excepción por `scd_type`. `DimensionLookup.checkDimZero()` (Kettle) inserta la fila técnica "unknown" nombrando solo 2 columnas (`tk`, `version`) — cualquier otra columna `NOT NULL` sin DEFAULT hace fallar ese INSERT y aborta el step en la primera fila, no como warning.

**Por qué era invisible:** solo dispara contra una dimensión con tabla vacía, y hasta D44 la rama `scd_type` 0/1 usaba `CombinationLookup` (que no llama `checkDimZero`) — el radio real de exposición era menor de lo que D44 (vocabulario uniforme, `DimensionLookup` para todo `scd_type`) deja.

**Resuelto por D47** (`02-decisiones.md`): no se relaja el DDL — la doc oficial de Pentaho prescribe pre-sembrar la fila `tk=0`/`version=1`, no aflojar `NOT NULL`. Mecanismo elegido: el sembrado se embebe en el DDL mismo (INSERT junto a la Parte 3 de `prompt_validacion_src.txt`), no vía `ExecSQL` (evita agregar un segundo escritor a la matriz R/W de la Fase 3).

**Ejecutado 2026-07-30:** `prompt_validacion_src.txt` (I8, V5) ahora exige INSERT completo de la fila 'desconocido' — no solo `technical_key`. Valores fijados: `version_field=1`, `date_from='1900-01-01 00:00:00'`, `date_to='2199-12-31 23:59:59.999'` (mismos centinelas que DDL-2, evita match accidental del lookup de fecha del lado del hecho contra la fila "desconocido"), y cualquier otra columna NOT NULL sin DEFAULT que declare el DDL recibe `'DESCONOCIDO'` (texto) o `0` (numérica). Sin test dedicado — es texto de prompt consumido por un LLM (`ddl_validation.py`), mismo criterio que el resto de `prompt_validacion_src.txt`/`system_etl.txt`: sin assertion de contenido en la suite, gate real es corrida contra el modelo (ver `04-verificacion.md`).

**Pendiente, fuera de esta entrada:** el gate de verificación en runtime (correr contra una dimensión vacía, con y sin sembrado) ya está señalado en D47 (`02-decisiones.md`) — no se agrega fila nueva a `04-verificacion.md`, esa tabla ya está en exceso de tope explícito (ver su nota de cabecera, sesión D44/D51).

---

## DDL-2 — Centinelas de rango en la dimensión de calendario pre-poblada externamente

**Síntoma:** K18 (`system_etl.txt`) dice que una tabla de calendario "sin clave de negocio natural en el origen" (`dim_tiempo` o similar) nunca la carga el ETL generado — se pre-puebla a mano con un script `generate_series`. Con el vocabulario uniforme (D44/D51), el lookup de FK del lado del hecho para CUALQUIER dimensión (incluida esta, si en algún diseño se referencia vía `Dimension lookup/update` en vez de `DBLookup`) resuelve por rango `[date_from, date_to)`. Si el script de sembrado no deja cada fila con los mismos centinelas que Kettle escribiría (`1900-01-01 00:00:00` / `2199-12-31 23:59:59.999` / `version=1`), el predicado del lookup nunca matchea — devuelve la clave "desconocido" para toda fecha, sin error ni warning.

**Por qué no es un checker Python:** el backend nunca ve las filas reales de una tabla pre-poblada externamente (principio de diseño del proyecto — solo estructura llega al LLM, nunca datos). No hay nada en `ktr_data`/DDL que un pass pre-emisión pueda inspeccionar para confirmar que el sembrado real tiene los centinelas correctos — es guía operativa para quien corre el script SQL, no una invariante verificable en build-time.

**Resuelto por D51** (`02-decisiones.md`): `K18` extendido con los valores exactos y la advertencia explícita contra `NOW()`/`CURRENT_TIMESTAMP` (que sellarían `date_from` con la hora de carga, rompiendo el matching para todo hecho con fecha anterior).

**Qué falta para cerrar del todo:** el mecanismo de calendario que K18 prescribe hoy sigue siendo `DBLookup` (exact-match, sin semántica de rango) — el riesgo de esta entrada solo se materializa si un diseño futuro reemplaza ese `DBLookup` por `Dimension lookup/update` para el calendario también, unificando con el resto del vocabulario D44/D51. No decidido en esta sesión (fuera de alcance) — si eso pasa, la guía de K18 ya está lista para esa transición.

---

## Pendiente de agregar

Puntos de contrato DDL notados por el usuario, todavía sin volcar acá con evidencia — agregar como `DDL-2`, `DDL-3`, ... a medida que se investiguen (mismo estándar que R-K1-R-K6/C.10-C.12: fuente Kettle, doc oficial, o corrida real — no solo lectura de `prompt_validacion_src.txt` en abstracto).
