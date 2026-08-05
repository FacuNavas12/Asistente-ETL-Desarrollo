# Investigación Kettle — respuestas a R-K1...R-K6 (bloqueantes de la Fase 2)

> **Alcance:** investigación pura contra el fuente de Pentaho Kettle. No propone código ni edita el plan.
> **Fuente primaria:** `pentaho/pentaho-kettle`, rama `master`, consultada el 2026-07-30.
> **Sobre las citas de línea:** son de `master` al día de consulta y pueden desplazarse. El anclaje estable es **nombre de clase + nombre de método + el SQL literal citado**, que es lo que se transcribe abajo. Cuando hay una cita textual, es textual.
> **Nivel de evidencia por respuesta:** `[FUENTE]` = leído en el fuente de Kettle. `[DOC]` = documentación oficial de Pentaho/Hop. `[INFERENCIA]` = deducción a partir de fuente, marcada como tal.

---

## 0. Resumen ejecutivo — veredictos

| Id | Veredicto | Efecto sobre el plan |
|---|---|---|
| **R-K2** | **La premisa de la pregunta es falsa, y por eso la respuesta útil es "sí".** El SQL del lookup exige `date_to > fecha_ref`, así que `date_to IS NULL` **nunca matchea** y devuelve la clave técnica de "desconocido" en silencio — exactamente el modo de falla que se temía. **Pero `DimensionLookup(update=Y)` nunca escribe `NULL` en `date_to`:** escribe su propio centinela `2199-12-31 23:59:59.999`. El rango degenerado que el plan describe no es el que produce el loader que el plan propone. | **Fase 2 es viable.** No hace falta Plan B por R-K2. Pero el supuesto "`date_to` NULL para siempre" tiene que salir del plan: es incorrecto y llevaría a un diseño equivocado. |
| **R-K2 (corolario)** | Aparece un **bloqueante nuevo, distinto y duro**: `checkDimZero` inserta la fila desconocida con `insert into t(tk, version) values (0, 1)` — solo dos columnas. Con `date_from TIMESTAMP NOT NULL` sin DEFAULT (V1/V3 de `prompt_validacion_src.txt`), ese INSERT **viola NOT NULL y aborta el step**. | La Fase 2 tal como está diseñada **falla en runtime** contra el DDL que V1/V3 obliga hoy. Hay que reconciliar contrato de DDL y contrato de step. Ver §2.3. |
| **R-K1** | Entrada nueva: `version=1`, `date_from=1900-01-01 00:00:00.000`, `date_to=2199-12-31 23:59:59.999` (configurables por `min_year`/`max_year`). | Determinado. |
| **R-K1b** | `Update` y `Punch through` **no** son intercambiables, y la diferencia no es la que dice el plan. `Update` reescribe la versión que el lookup resolvió (por `tk`); `Punch through` reescribe **todas** las versiones (por clave natural) **además** de que la versión vigente igual se reescribe por la vía de `Update`. Para una dimensión que solo tendrá una fila por clave, son **indistinguibles en efecto**. | El contrato tiene que elegir explícito por atributo, como el plan dice. Para SCD1 puro, `Update`. `Punch through` es para atributos corregibles retroactivamente **dentro de** una dimensión SCD2. |
| **R-K3** | Confirmado: `Combination lookup/update` **mantiene solo la clave**. Es la conducta documentada y deliberada del step; el caso de uso declarado es junk dimension y, con un update posterior por `tk`, Tipo 1. | A-2 es real y sistémico. El pivote del cambio de contrato se sostiene. |
| **R-K3b** | **No existe ningún modo de atributo con semántica SCD0** en `Dimension lookup/update`. Los siete modos son `Insert`, `Update`, `Punch through`, `DateInsertedOrUpdated`, `DateInserted`, `DateUpdated`, `LastVersion`; los tres primeros son los únicos que llevan valor de stream y los tres escriben. Un atributo que no está en la lista tampoco se escribe **en el INSERT**, así que "no tocar si existe" es inalcanzable con este step. **Sí es alcanzable con `InsertUpdate`:** el INSERT escribe todos los `<value>` sin mirar el flag, y el UPDATE solo incluye los que tienen `<update>Y</update>`. | La hipótesis de R-K3b sobre `InsertUpdate` es correcta. Con una trampa dura: ver §4.2. |
| **R-K4** | La fila desconocida la crea **solo** el loader (`update=Y`), en `init` de la copia 0, con `tk=0` y `version=1` y **todo lo demás NULL**. En modo `update=N` el step retorna `0` como fallback pero **no crea nada**. Para PostgreSQL, `getNotFoundTK` devuelve `0` tanto en la rama autoinc como en la normal. | `IfNull → 0` es correcto, no casual — **condicionado** a que el loader con `update=Y` corra antes y a que el INSERT de dos columnas sea legal contra el DDL (§2.3). D21 queda mayormente gratis salvo por los atributos de la fila desconocida, que salen NULL, no `'DESCONOCIDO'`. |
| **R-K5** | `<unique_connections>` **es** `TransMeta.usingUniqueConnections`, el flag real, no un proxy. Y hace tres cosas medibles: (1) difiere todo commit al final de la transformación; (2) **desactiva silenciosamente `use_batch`** en `Table output`; (3) convierte el `truncate` de `Table output` en **`DELETE FROM`**, es decir transaccional y reversible. | `v8` **está invertida**, no aproximada, y C-3 está mal formulada: el caso riesgoso es `unique_connections=N` + truncate, no el que los dos sets tienen. Confirma la decisión de no cablearla con severidad `error`. |
| **R-K6** | Confirmado textualmente en `InsertUpdateMeta.getXML()`. El emisor de este repo y V6 están bien. | Cierra R-K6 sin cambios. |

---

## 1. R-K2 — el algoritmo de resolución de la fila vigente

### 1.1 El SQL, literal

`DimensionLookup.setDimLookup(RowMetaInterface)` construye el prepared statement del lookup. El comentario del propio método documenta las dos formas (—`DimensionLookup.java:828-838`):

```
 * DEFAULT, SYSDATE, START_TRANS, COLUMN_VALUE :
 *
 * SELECT <tk>, <version>, ... , FROM <table> WHERE key1=keys[1] AND key2=keys[2] ... AND <datefrom> <= <datefield>
 * AND <dateto> > <datefield> ;
 *
 * NULL :
 *
 * SELECT <tk>, <version>, ... , FROM <table> WHERE key1=keys[1] AND key2=keys[2] ... AND ( <datefrom> is null OR
 * <datefrom> <= <datefield> ) AND <dateto> >= <datefield>
```

Y el código que lo emite (—`:877-898`):

```java
String dateFromField = databaseMeta.quoteField( meta.getDateFrom() );
String dateToField   = databaseMeta.quoteField( meta.getDateTo() );

if ( meta.isUsingStartDateAlternative()
  && ( meta.getStartDateAlternative() == START_DATE_ALTERNATIVE_NULL )
  || ( meta.getStartDateAlternative() == START_DATE_ALTERNATIVE_COLUMN_VALUE ) ) {
  // Null as a start date is possible...
  sql += " AND ( " + dateFromField + " IS NULL OR " + dateFromField + " <= ? )";
  sql += " AND " + dateToField + " > ?";
} else {
  // Null as a start date is NOT possible
  sql += " AND ? >= " + dateFromField;
  sql += " AND ? < " + dateToField;
}
```

**Respuestas directas a las siete preguntas del checklist:**

1. **(Algoritmo)** Es una comparación SQL directa contra un intervalo semiabierto `[date_from, date_to)`. No hay lógica de "elegir entre candidatas": el prepared statement lleva `setMaxRows(1)` con el comentario `// alywas get only 1 line back!` (—`:900`). Si el intervalo devuelve dos filas, se toma una arbitraria sin aviso.
2. **(`date_to = NULL`)** **No se soporta en ninguna de las dos ramas.** Las dos exigen `date_to > ?` / `? < date_to`. Con `date_to` NULL el predicado evalúa a NULL, la fila no entra al resultset, `returnRow == null`, y `lookupValues` toma la rama de no-encontrado: `returnRow[0] = data.notFoundTk` (—`:451-458`). **Sin error, sin log de nivel normal.** Nótese la asimetría deliberada: `date_from` NULL **sí** está previsto (y solo en la rama `START_DATE_ALTERNATIVE_NULL`/`COLUMN_VALUE`); `date_to` NULL nunca.
3. **(Una sola versión por clave)** Sin problema. El matching no asume multiplicidad; con una fila cuyo rango sea `[1900, 2199)` cualquier fecha de referencia razonable cae dentro.
4. **(Fecha de referencia por defecto)** `determineDimensionUpdatedDate(Object[] row)` (—`:240-259`): `if (data.datefieldnr < 0) return getTrans().getCurrentDate();` — la fecha de arranque de la transformación. **El `<date><name>` vacío es la configuración normal y soportada**, no un borde. La falla está en el caso contrario: si **sí** se configura un `date_field` y una fila trae NULL ahí, se lanza `KettleStepException` (`DimensionLookup.Exception.NullDimensionUpdatedDate`) y el step aborta.
5. **(Consistencia loader—lookup entre `.ktr` distintos)** Segura, con ejecución secuencial del `.kjb`. El diferimiento de commit es **por transformación**: `Database.commit(boolean force)` retorna sin hacer nada solo mientras `connectionGroup` no esté vacío (—`Database.java:1106-1108`), y `connectionGroup` se puebla desde el flag de conexiones únicas de *esa* transformación. `DimensionLookup.dispose` commitea explícitamente si no hay errores (—`:1717-1725`). Dos `.ktr` distintos no comparten grupo de conexión, así que el segundo abre conexión nueva y ve lo comiteado por el primero. **El riesgo real no es de snapshot: es de orden de entries en el `.kjb`.**
6. **(`timestamp` vs `timestamptz`)** No hay bifurcación de comportamiento en Kettle: el parámetro se bindea como `java.util.Date` vía `ValueMetaDate` y la comparación la hace Postgres. `PostgreSQLDatabaseMeta.getFieldDefinition` mapea `TYPE_DATE` y `TYPE_TIMESTAMP` los dos a `TIMESTAMP` sin zona. Con un rango `[1900, 2199)` no hay riesgo de borde por desplazamiento de zona. **Sí lo habría** con `date_from` = fecha de la primera carga y una fecha de referencia cercana.
7. **(Prueba empírica)** Ya no hace falta para decidir la Fase 2. Lo que sí conviene verificar en corrida es el corolario de §2.3, que es lo que puede romper.

### 1.2 Los tres modos de falla del plan, evaluados uno por uno

**Modo 1 — "el matching puede requerir un centinela real en vez de NULL".** Correcto en cuanto al mecanismo, **inaplicable al diseño propuesto**, porque el centinela lo pone Kettle. En `lookupValues`, cuando el loader (`update=Y`) inserta una entrada nueva (—`:487-500`):

```java
// Date range: ]-oo,+oo[
if ( data.startDateChoice == START_DATE_ALTERNATIVE_SYSDATE ) {
  valueDateFrom = valueDate;   // fecha de inicio de ejecución del step
} else {
  valueDateFrom = data.min_date;
}
valueDateTo = data.max_date;
valueVersion = new Long( 1L );
```

Y `min_date`/`max_date` vienen de `init` (—`:1691-1692`) — `DimensionLookupMeta.getMinDate()`/`getMaxDate()` (—`DimensionLookupMeta.java:1085-1106`), que construyen `minYear-01-01 00:00:00.000` y `maxYear-12-31 23:59:59.999` con `minYear = Const.MIN_YEAR` y `maxYear = Const.MAX_YEAR` por defecto (—`DimensionLookupMeta.java:724-725`), y en `Const.java`:

```java
/** The default minimum year in a dimension date range */
public static final int MIN_YEAR = 1900;
/** The default maximum year in a dimension date range */
public static final int MAX_YEAR = 2199;
```

Se serializan en el XML como `<min_year>` / `<max_year>` (—`DimensionLookupMeta.java:868-869`). Es decir: **el rango degenerado real de una dimensión SCD0/SCD1 cargada con `DimensionLookup(update=Y)` es `[1900-01-01, 2199-12-31 23:59:59.999)`, no `[fecha_carga, NULL)`.** El lookup con `update=N` lo resuelve sin ambigüedad. El argumento de D16 no solo quedó obsoleto por V1/V3: era incorrecto sobre el mecanismo, porque presuponía que las columnas las llenaba otro.

Corolario operativo: la columna `date_to` **puede** ser `NULL`-able en el DDL sin consecuencia — el loader nunca la deja NULL. Lo que sí importa es que el tipo aguante el año 2199 y que nadie más escriba en esa tabla con otro convenio de centinela. Si en algún momento otro step (un `Table output`, un `ExecSQL` de sembrado, un `InsertUpdate`) inserta filas en una dimensión con `date_to` NULL, esas filas quedan **invisibles al lookup** y el hecho las resuelve a 0.

**Modo 2 — "la configuración de cache puede comportarse distinto con cardinalidad 1:1".** Hay que separar dos caches, porque **no coinciden en el tratamiento de NULL** y eso es un hallazgo por sí mismo.

- **Cache interno del step (`cache_size >= 0`, siempre disponible).** `getFromCache` (—`:1602-1631`) compara en memoria con el mismo intervalo semiabierto: `if (time >= from && time < to)`. Consistente con el SQL. Pero deserializa `date_to` sin chequear nulos: `long to = ((Date) row[row.length-1]).getTime();` — con `date_to` NULL en la fila cacheada sería NPE. En la práctica no se alcanza, porque una fila con `date_to` NULL nunca entra al cache: entra solo desde el resultset del SQL, que ya la excluyó.
- **Preload cache (`preload_cache=Y`, disponible solo con `update=N`; ver `:171` y `:345`).** Es otro código: `DimensionCache.lookupRow`, y **ahí `toDate == null` sí se trata como +infinito, explícitamente**:

  ```java
  } else if ( fromDate != null && toDate == null ) {
    // This is the case where the toDate is null and the fromDate is not.
    // This is a special case where null as an end date means +Infinity
    if ( fromDate.compareTo( lookupDate ) <= 0 ) {
      return insertionPoint; // found the key!!
    }
  ```

  **Es decir: con `preload_cache=N` el `date_to` NULL no matchea; con `preload_cache=Y` sí.** Los dos caminos del mismo step discrepan. Esto es una trampa para cualquier prueba empírica: una corrida con preload activado "confirmaría" que NULL funciona y la conclusión no trasladaría al camino por defecto.

  Dos motivos independientes para **no** usar `preload_cache=Y` como mitigación:
  1. **Off-by-one en el matching.** `if (insertionPoint < rowCache.size() - 1)` — la última fila del cache ordenado nunca puede ser el punto de inserción aceptado. Con pocas filas por dimensión (5 categorías, 7 productos), perder la última fila es un porcentaje enorme, y falla como "no encontrado" — FK a 0.
  2. **La fila desconocida rompe el comparador.** `DimensionCache.compare` maneja `fromDate == null` y `toDate == null` por separado, pero si **los dos** son NULL cae al `else` final y ejecuta `fromDate.compareTo(lookupDate)` — NPE. Y la fila desconocida que crea `checkDimZero` tiene exactamente los dos en NULL (§2.3). Es decir, `preload_cache=Y` sobre una dimensión que contenga la fila desconocida de Kettle puede tirar NPE durante `sortRows()`.

**Modo 3 — "loader y lookup en `.ktr` distintos, snapshot previo al commit".** Descartado como mecanismo, por §1.1 punto 5. El riesgo residual es de **secuenciación del `.kjb`**, no de aislamiento de transacción, y ese es un riesgo que la Fase 3 ya direcciona (chequeo a nivel etapa, S-13). Vale la pena registrar que el diagnóstico correcto es distinto del que el plan escribió: no hay que probar visibilidad de commit, hay que probar que el orden del job coincide con el topológico del corte.

### 1.3 Sobre la afirmación "ninguno de los checkers planeados lo detecta"

Sigue siendo cierta y sigue siendo el punto más importante de la sección R-K2 del plan, pero se aplica a un objeto distinto. El invariante que ningún checker de forma de XML puede ver, y que sí es verificable estáticamente sobre el XML emitido, es: **para cada tabla de dimensión, todos los steps que la escriben tienen que compartir el convenio de centinela de `date_from`/`date_to` con todos los steps que la leen.** Un `DimensionLookup(update=N)` leyendo una tabla que otro step llena con `date_to` NULL es un finding estructural, no semántico, y es exactamente el hueco que queda abierto si la dimensión se puebla parcialmente por fuera del loader (sembrado de la fila `DESCONOCIDO` por DDL o `ExecSQL`, por ejemplo — que es justo lo que D21 contempla).

---

## 2. Detalle de R-K1, R-K1b y el corolario bloqueante

### 2.1 R-K1 — qué escribe el loader en `version`/`date_from`/`date_to`

`DimensionLookup.dimInsert(...)` es el único emisor de filas nuevas. Tres escenarios:

**Entrada nueva (clave natural que no existe).** `version = 1`; `date_from` según `data.startDateChoice` (—`:1108-1133`): con `START_DATE_ALTERNATIVE_NONE` (el default, cuando `use_start_date_alternative=N`) se escribe el `dateFrom` que le pasó el caller, que es `data.min_date` = `1900-01-01 00:00:00.000`; con `SYSDATE`, la fecha de inicio de ejecución del step; con `NULL`, literalmente `null` (esta es la única forma de que Kettle escriba NULL en `date_from`, y es opt-in explícito); con `START_OF_TRANS`, `getTrans().getStartDate()`; con `COLUMN_VALUE`, la columna de stream indicada. `date_to = data.max_date` = `2199-12-31 23:59:59.999` **en todos los casos**.

**Cambio en un atributo marcado `Insert` (nueva versión).** —`:710-711`: `valueDateFrom = valueDate` (fecha de referencia, típicamente arranque de la transformación), `valueDateTo = max_date`, `version = version + 1`. Y en el mismo `dimInsert`, la rama `if (!newEntry)` cierra la versión anterior (—`:1187-1238`), documentada como:

```
 * UPDATE d_customer SET dateto = val_datfrom , last_updated = <now> , last_version = false WHERE keylookup[] =
 * keynrs[] AND versionfield = val_version - 1 ;
```

**Cambio en un atributo marcado `Update` o `Punch through` (sin nueva versión).** `date_from`, `date_to` y `version` **no se tocan**. Ni `dimUpdate` ni `dimPunchThrough` incluyen esas columnas en su `SET`.

Consecuencia para el caso SCD1 puro: una dimensión cargada así tiene, para siempre, una fila por clave natural con `version = 1`, `date_from = 1900-01-01`, `date_to = 2199-12-31`. Es upsert puro. **Sí, `DimensionLookup(update=Y)` con todos los atributos en modo de sobrescritura se comporta como el loader SCD1 correcto.**

### 2.2 R-K1b — `Update` vs `Punch through`

Los dos son SQL distintos con `WHERE` distinto:

- `dimUpdate(rowMeta, row, dimkey, valueDate)` (—`:1271-1362`) — `UPDATE <tabla> SET <cada campo no-clave con argumento de stream> = ?, <fechas técnicas> = ? WHERE <technical_key> = ?`. Afecta **una fila**: la que el lookup resolvió como vigente.
- `dimPunchThrough(rowMeta, row)` (—`:1366-1452`) — `UPDATE <tabla> SET <solo los campos marcados Punch through> = ?, <fechas técnicas> = ? WHERE <clave natural 1> = ? AND <clave natural 2> = ? ...`. Afecta **todas las versiones**.

La descripción del plan es correcta pero incompleta en un punto que importa. El bloque de decisión (—`:647-703`) computa tres booleanos comparando cada campo con lo que hay en la BD: `identical`, `insert` (algún campo marcado `Insert` cambió) y `punch` (algún campo marcado `Punch through` cambió). Y después:

```java
if ( !insert ) {          // Just an update of row at key = valueKey
  if ( !identical ) {
    dimUpdate( rowMeta, row, technicalKey, valueDate );
    ...
  } else { incrementLinesSkipped(); }
} else {
  ... dimInsert( ... nueva versión ... )
}
if ( punch ) {            // On of the fields we have to punch through has changed!
  dimPunchThrough( rowMeta, row );
}
```

Dos consecuencias no obvias:

1. **`Punch through` no excluye a `Update`.** Si cambia un campo `Punch through` y no cambia ninguno `Insert`, entonces `identical=false` e `insert=false`, así que corre `dimUpdate` — que reescribe **todos** los campos con argumento, incluidos los `Insert` y los `Punch through` — y **además** corre `dimPunchThrough`. El campo punch se escribe dos veces (misma versión y todas las versiones). Consistente, pero significa que `dimUpdate` no es "solo los campos marcados Update": es **todos** los campos.
2. **Con una sola versión por clave, `Update` y `Punch through` producen el mismo estado final.** La diferencia solo se manifiesta si hay historia acumulada. Por eso, para SCD1 puro, la elección es semántica y no observable: `Update` es la que describe la intención. `Punch through` es la que hace falta cuando la dimensión **es** SCD2 y ese atributo concreto debe corregirse retroactivamente — el caso `nombre_producto` de Set B, que está bien resuelto.

**Sobre el default del emisor.** Los códigos que van al XML son (—`DimensionLookupMeta.java:92-93`):

```java
public static final String[] typeCodes = { // for saving to the repository
  "Insert", "Update", "Punch through", "DateInsertedOrUpdated", "DateInserted", "DateUpdated", "LastVersion", };
```

Y al parsear un tipo desconocido o vacío, Kettle devuelve `TYPE_UPDATE_DIM_INSERT` con el comentario `// INSERT is the default: don't lose information.` (—`:610-619`). O sea: el `f.get("type", "Insert")` del emisor **coincide con el default de Kettle**, y por eso un atributo sin `type` se versiona sin que nadie lo diga — el comportamiento no es un bug del emisor, es el default de Kettle heredado en silencio. El argumento de S-8 para volverlo error de validación se refuerza: no hay ningún lugar donde el default sea visible.

### 2.3 Corolario bloqueante — `checkDimZero` contra `date_from NOT NULL`

Esto no estaba en las preguntas y es lo más accionable de la investigación.

`DimensionLookup.processRow` llama, en la primera fila y solo para la copia 0 (—`:205-207`):

```java
if ( getCopy() == 0 ) {
  checkDimZero();
}
```

Y `checkDimZero()` (—`:1633-1682`):

```java
public void checkDimZero() throws KettleException {
  // Don't insert anything when running in lookup mode.
  if ( !meta.isUpdate() ) {
    return;
  }
  ...
  int start_tk = databaseMeta.getNotFoundTK( isAutoIncrement() );
  ...
  if ( count.longValue() == 0 ) {
    if ( !databaseMeta.supportsAutoinc() || !isAutoIncrement() ) {
      isql = "insert into " + data.schemaTable + "(" + keyField + ", " + versionField + ") values (0, 1)";
    } else {
      isql = databaseMeta.getSQLInsertAutoIncUnknownDimensionRow( schemaTable, keyField, versionField );
    }
    data.db.execStatement( ... );
  } catch ( KettleException e ) {
    throw new KettleDatabaseException( "Error inserting 'unknown' row in dimension [" + data.schemaTable + "] : " + isql, e );
  }
}
```

La rama autoinc no cambia nada relevante: `BaseDatabaseMeta.getSQLInsertAutoIncUnknownDimensionRow` (—`:1773-1775`) devuelve `"insert into <t>(<tk>, <version>) values (0, 1)"`, y `PostgreSQLDatabaseMeta` no la sobreescribe.

**El INSERT nombra exactamente dos columnas.** Todas las demás quedan en su DEFAULT o en NULL. Por lo tanto:

- Cualquier columna `NOT NULL` **sin DEFAULT** en la dimensión hace fallar ese INSERT — `KettleDatabaseException` — `setErrors(1)` y `stopAll()` en el catch de `processRow`. **No es un warning: es la transformación abortada en la primera fila.**
- V1/V3 de `prompt_validacion_src.txt:24-26` obliga hoy a `date_from TIMESTAMP NOT NULL`. Eso colisiona de frente. Con `version_field INTEGER NOT NULL DEFAULT 1` no hay problema (se escribe explícito, y además tiene default); con `date_to TIMESTAMP NULL` tampoco.
- La colisión se extiende a **cualquier** otra columna `NOT NULL` sin default de la dimensión: la clave natural, las descripciones, los códigos. Hoy el problema no se ve porque la rama que corre para `scd_type` 0/1 es `CombinationLookup`, que no llama a `checkDimZero`.

Esto es información que la Fase 2 necesita **antes** de mergear, y es un buen ejemplo de por qué el gate de corrida real de la Fase 4 debe incluir una dimensión que se cargue desde cero contra la tabla vacía: el fallo solo aparece la primera vez que se crea la fila 0.

Nota adicional para R-K4 y D21: la fila desconocida que crea Kettle tiene `tk=0`, `version=1` y **todos los atributos descriptivos en NULL** — no `'DESCONOCIDO'`. Si el reporting espera una etiqueta legible en el miembro desconocido, eso no lo aporta el step, y ese es el pedazo de D21 que **no** queda gratis.

---

## 3. R-K3 — `Combination lookup/update` y atributos no-clave

`[DOC]` La documentación oficial de Pentaho es explícita y no ambigua:

> "The Combination lookup/update step will maintain the key information only. You must update the non-key information in the dimension table, for example by putting an update step (based on technical key) after the combination update/lookup step."

Y sobre el caso de uso correcto:

> "The Combination Lookup-Update step allows you to store information in a junk-dimension table, and can possibly also be used to maintain Kimball pure Type 1 dimensions."

Lecturas para el plan:

- **A-2 es real y sistémico.** No hay modo de configuración que lo evite; es el contrato del step. La descripción del emisor de este repo (`lookups.py:121-135`, solo `<key>` y `lastUpdateField` vacío) es fiel al step, no una implementación incompleta.
- **"Tipo 1" en esa frase es Tipo 1 *con un update posterior por `tk`*, no Tipo 1 a secas.** El patrón canónico de Pentaho para SCD1 con `CombinationLookup` es dos steps: `CombinationLookup` para obtener/crear la SK y después un `Update` (o `Table output`/`InsertUpdate`) por `tk` para los atributos. Eso es relevante para el plan por dos razones: (a) explica por qué el step existe y por qué D16 lo eligió sin que fuera un error grosero; (b) ese segundo step es **otro escritor sobre la misma tabla**, lo cual convertiría la rama en cortable — o sea, el patrón completo nunca se emitió, y el defecto es que se emitió la mitad.
- **El caso en que `CombinationLookup` sí es correcto** es la junk/technical dimension: una tabla cuya única razón de existir es asignar una SK a una combinación de atributos que *son todos* clave. Ahí no hay atributos no-clave que mantener, y el step es exactamente la herramienta. Es un caso legítimo para el mecanismo de override registrado, no para la derivación por defecto.

## 4. R-K3b — ¿existe SCD0?

### 4.1 En `Dimension lookup/update`: no

Los siete modos, del fuente (—`DimensionLookupMeta.java:75-81`):

```java
public static final int TYPE_UPDATE_DIM_INSERT       = 0;
public static final int TYPE_UPDATE_DIM_UPDATE       = 1;
public static final int TYPE_UPDATE_DIM_PUNCHTHROUGH = 2;
public static final int TYPE_UPDATE_DATE_INSUP       = 3;
public static final int TYPE_UPDATE_DATE_INSERTED    = 4;
public static final int TYPE_UPDATE_DATE_UPDATED     = 5;
public static final int TYPE_UPDATE_LAST_VERSION     = 6;
```

Los modos 3 a 6 son columnas de auditoría que el step llena solo, sin argumento de stream — `isUpdateTypeWithoutArgument` los excluye de la lista de campos con valor (—`DimensionLookupMeta.java:675-690`). Los modos con valor son solo `Insert`, `Update`, `Punch through`, y los tres escriben cuando el valor difiere.

Y no sirve omitir el atributo de la lista: `dimInsert` arma la fila desde `data.fieldnrs` (—`:1138-1148`), así que un atributo que no está en la lista **no se escribe ni en el INSERT inicial** — queda NULL para siempre. No hay forma de decir "escribilo la primera vez y después no lo toques".

**Conclusión:** SCD0 por atributo es inalcanzable con `Dimension lookup/update`. Y confirma la observación del plan de que "la rama vieja, con toda su miseria, era insert-only — que es SCD0 correcto": `CombinationLookup` sobre claves era, accidentalmente, la única cosa del sistema con semántica SCD0.

### 4.2 En `InsertUpdate`: sí, con una trampa dura

La hipótesis de R-K3b es correcta. En `InsertUpdate.lookupValues`:

- **Rama INSERT** (clave no encontrada): se escriben **todos** los `<value>`, sin mirar el flag — `insertRow[i] = row[data.valuenrs[i]]` sobre todo `data.valuenrs`, y `data.insertRowMeta` se arma en `processRow` recorriendo `meta.getUpdateFields()` completo, también sin mirar el flag.
- **Rama UPDATE** (clave encontrada): `prepareUpdate` incluye en el `SET` únicamente los campos con `getUpdate() == true`, y la detección de cambio también recorre solo esos. Si ninguno cambió, `incrementLinesSkipped()`.
- **`update_bypassed=Y`** (checkbox "Don't perform any updates"): la rama UPDATE se saltea entera; solo se insertan claves nuevas.

Así que **`InsertUpdate` con todos los `<value>` no-clave en `<update>N</update>` es el loader SCD0 correcto**: inserta la fila la primera vez con todos los atributos, y nunca los reescribe. La SK la aporta el DDL (`BIGSERIAL`/identity) y la columna **no** se lista entre los `<value>`.

**La trampa:** si **ningún** `<value>` tiene `update=Y` y `update_bypassed` sigue en `N`, `processRow` igual llama a `prepareUpdate`, que construye `UPDATE <t>\nSET WHERE ...` — SQL sintácticamente inválido — y el `prepareStatement` tira `KettleDatabaseException` en la primera fila. Es decir: **el par "todos los values en `update=N`" y `update_bypassed=N` es una configuración que aborta en runtime**. Los dos flags tienen que moverse juntos.

Dato colateral relevante para el DDL de Postgres: `PostgreSQLDatabaseMeta.supportsAutoInc()` devuelve `true`, pero el comentario del propio método advierte:

> "Support for the serial field is only fake in PostgreSQL. You can't get back the value after the inserts (getGeneratedKeys) through JDBC calls. Therefor it's wiser to use the built-in sequence support directly, not the auto increment features."

O sea, para dimensiones en Postgres, `creation_method` = sequence (o table max) es la opción que Pentaho recomienda, no `use_autoinc=Y`. Con `use_autoinc=Y`, `dimInsert` intenta `getGeneratedKeys` (—`:1172-1185`) y lanza `"Unable to retrieve value of auto-generated technical key"` si no lo consigue.

## 5. R-K4 — la fila "unknown"

Consolidado de §2.3 y del fuente:

| Pregunta | Respuesta | Evidencia |
|---|---|---|
| ¿Qué clave técnica recibe? | `0`. | `checkDimZero` inserta `values (0, 1)`; `BaseDatabaseMeta.getSQLInsertAutoIncUnknownDimensionRow` también `values (0, 1)`. |
| ¿Es estable en 0? | Para PostgreSQL, sí. `BaseDatabaseMeta.getNotFoundTK(boolean)` devuelve `0` y `PostgreSQLDatabaseMeta` **no** la sobreescribe. **No es universal:** otros dialectos la sobreescriben, así que 0 es una propiedad del par (Kettle, Postgres), no de Kettle. | `BaseDatabaseMeta.java:662-664`; `PostgreSQLDatabaseMeta.java` completo, sin override. |
| ¿Se crea también con `update=N`? | **No.** `checkDimZero` arranca con `if (!meta.isUpdate()) { return; }` y el comentario `// Don't insert anything when running in lookup mode.` El lookup solo **devuelve** `notFoundTk` cuando no matchea; no crea nada. | `DimensionLookup.java:1633-1638`, `:451-458`. |
| ¿Qué contiene la fila? | `tk=0`, `version=1`, **todo lo demás NULL** — incluidos `date_from`, `date_to` y los atributos descriptivos. | El INSERT nombra dos columnas. |
| ¿`IfNull → 0` es correcto o casual? | **Correcto**, no casual — con tres condiciones: (a) el loader corre con `update=Y` antes que el lookup; (b) el DDL permite el INSERT de dos columnas (§2.3); (c) el motor es Postgres. Y la fila que apunta no trae etiqueta legible. | Arriba. |
| ¿Explica los conteos de la corrida? | Consistente: `dim_categoria` = 5 + fila 0 = 6, `dim_producto` = 6 + fila 0 = 7. La fila la crea el step, no el DDL. La corrida reportó `DESCONOCIDO` como etiqueta, lo cual **no** puede venir de `checkDimZero` — vale la pena verificar de dónde salió, porque si vino de un sembrado por DDL o `ExecSQL`, entonces hay un segundo escritor sobre la dimensión y `checkDimZero` encontró `count != 0` y no hizo nada (lo cual, de paso, sortea el problema de §2.3 — pero por accidente). | Requiere verificación en la corrida. |

## 6. R-K5 — `<unique_connections>`

**¿Es el flag o un proxy? Es el flag.** En `TransMeta`:

```java
/** Whether the transformation is using unique connections. */
protected boolean usingUniqueConnections;
```

y en `getXML()`:

```java
retval.append( "    " ).append( XMLHandler.addTagValue( "unique_connections", usingUniqueConnections ) );
```

`[DOC]` En Spoon es la casilla "Make the transformation database transactional", pestaña Miscellaneous de la configuración de la transformación.

**Qué garantiza, en tres efectos medibles:**

1. **Difiere todo commit al final de la transformación.** `Database.commit(boolean force)`:

   ```java
   // Don't do the commit, wait until the end of the transformation.
   // When the last database copy (opened counter) is about to be closed, we do a commit
   if ( !Utils.isEmpty( connectionGroup ) && !force ) {
     return;
   }
   ```

   Con lo cual **`commit=1000` de cada step queda sin efecto**: los steps llaman `commit()` cada N filas y la llamada retorna sin hacer nada. El commit (o el rollback) es uno, al cierre.

2. **Desactiva `use_batch` en `Table output`, en silencio.** `TableOutput.init`:

   ```java
   // Disable batch mode in case
   // - we use an unlimited commit size
   // - if we need to pick up auto-generated keys
   // - if you are running the transformation as a single database transaction (unique connections)
   // - if we are reverting to save-points
   data.batchMode =
     meta.useBatchUpdate()
       && data.commitSize > 0 && !meta.isReturningGeneratedKeys()
       && !getTransMeta().isUsingUniqueConnections() && !data.useSafePoints;
   ```

   O sea, `<use_batch>Y</use_batch>` en el XML **no significa que haya batch** si `unique_connections=Y`. Cualquier checker que razone sobre `use_batch` tiene que leer el flag de la transformación, no solo el del step.

3. **Convierte el `truncate` en `DELETE FROM`.** `Database.truncateTable` bifurca por `connectionGroup`: si está vacío, obtiene la sentencia de `databaseMeta.getTruncateTableStatement(...)` y la ejecuta; si no está vacío (es decir, bajo conexiones únicas), ejecuta `DELETE FROM <tabla>` en su lugar. `[FUENTE, vía búsqueda de código — el fetch de `Database.java` se cortó antes de ese método, ver §8]`

   Consecuencia: bajo `unique_connections=Y` el "truncate" es transaccional y reversible; bajo `unique_connections=N` es un `TRUNCATE TABLE` que en muchos motores hace commit implícito y es inmediatamente visible a otras conexiones.

**Veredicto sobre C-3 y `v8`:** están al revés. La condición peligrosa es `truncate=Y` **con** `unique_connections=N`, no sin él. Los dos sets tienen `unique_connections=Y`, o sea que su truncate es un DELETE transaccional — que es el caso benigno. Un `v8_truncate_sin_transaccional` cableado con severidad `error` marcaría como error precisamente la configuración segura. La decisión del plan de dejarla fuera del cableado con severidad es correcta, y la corrección es de formulación, no de tolerancia.

**Un cuarto efecto que no se preguntó pero cambia el análisis de carreras.** El truncate de `Table output` **no ocurre en `init`**: ocurre al recibir la primera fila, dentro de `processRow`:

```java
Object[] r = getRow(); // this also waits for a previous step to be finished.
if ( r == null ) { // no more input to be expected...
  // truncate the table if there are no rows at all coming into this step
  if ( first && meta.truncateTable() ) { truncateTable(); }
  return false;
}
if ( first ) {
  first = false;
  if ( meta.truncateTable() ) { truncateTable(); }
  ...
```

Es decir, el truncate se intercala con el flujo de filas, y si no llega ninguna fila se ejecuta igual al cierre del input. Para el análisis de la matriz R/W esto importa: el efecto de borrado de un `Table output` con truncate no es un efecto de inicialización que ocurra antes que todo, es un efecto que ocurre en un momento no determinado del stream — que es justamente el tipo de cosa que hace que `_reaches` (exención por camino dirigido) sea inseguro. Es evidencia independiente a favor del punto 4 de la Fase 3.

## 7. R-K6 — mapeo XML de `InsertUpdate`

Confirmado textualmente. `InsertUpdateMeta.getXML()`:

```java
for ( int i = 0; i < keyFields.length; i++ ) {
  retval.append( "      <key>" );
  retval.append( XMLHandler.addTagValue( "name",      keyFields[ i ].getKeyStream() ) );
  retval.append( XMLHandler.addTagValue( "field",     keyFields[ i ].getKeyLookup() ) );
  retval.append( XMLHandler.addTagValue( "condition", keyFields[ i ].getKeyCondition() ) );
  retval.append( XMLHandler.addTagValue( "name2",     keyFields[ i ].getKeyStream2() ) );
  retval.append( "      </key>" );
}
for ( int i = 0; i < updateFields.length; i++ ) {
  retval.append( "      <value>" );
  retval.append( XMLHandler.addTagValue( "name",   updateFields[ i ].getUpdateLookup() ) );
  retval.append( XMLHandler.addTagValue( "rename", updateFields[ i ].getUpdateStream() ) );
  retval.append( XMLHandler.addTagValue( "update", updateFields[ i ].getUpdate().booleanValue() ) );
  retval.append( "      </value>" );
}
```

Y `readData` lee simétrico: `keyStream — name`, `keyLookup — field`, `updateLookup — name`, `updateStream — rename`. Los nombres de campo de las clases anidadas lo confirman: `KeyField.keyStream` está anotado `@Injection(name = "KEY_STREAM")` con el javadoc "which field in input stream to compare with?", y `keyLookup` con "field in table"; `UpdateField.updateLookup` es "Field value to update after lookup" (columna) y `updateStream` es "Stream name to update value with".

Por lo tanto: **`<key><name>` = stream, `<key><field>` = columna, `<value><name>` = columna, `<value><rename>` = stream.** El emisor de este repo y V6 están alineados con la fuente. Se cierra R-K6 sin acción.

Dos detalles adicionales del mismo método, por si sirven a un checker:

- `readData` aplica defaults al leer: si falta `<key><condition>` asume `"="`; si falta `<value><rename>` asume el mismo nombre que `<name>`; si falta `<value><update>` asume `TRUE`. Un XML que omita `<update>` **actualiza**.
- Las condiciones válidas de `<key><condition>` son un conjunto cerrado: `"="`, `"= ~NULL"`, `"<>"`, `"<"`, `"<="`, `">"`, `">="`, `"LIKE"`, `"BETWEEN"`, `"IS NULL"`, `"IS NOT NULL"` (constante `COMPARATORS`).

---

## 8. Qué quedó sin verificar y cómo

| Punto | Estado | Cómo cerrarlo |
|---|---|---|
| `Database.truncateTable` — bifurcación `connectionGroup` — `DELETE FROM` | Confirmado por búsqueda de código sobre el mismo archivo, no por lectura directa: el fetch de `Database.java` se cortó antes de ese método. La conclusión es consistente con `Database.commit` y con `TableOutput.init`, que sí se leyeron completos. | Leer `Database.truncateTable(String)` en `core/src/main/java/org/pentaho/di/core/database/Database.java`. |
| `CombinationLookup.java` / `CombinationLookupMeta.java` | No se pudieron descargar (respuesta vacía en dos intentos). R-K3 se responde con documentación oficial, que en este caso es una afirmación normativa explícita del comportamiento, no una descripción vaga. | Leer el fuente si se quiere la cita de línea. No cambia el veredicto. |
| Etiqueta `DESCONOCIDO` observada en la corrida | Inexplicada. `checkDimZero` no la puede producir (inserta solo `tk` y `version`). | Verificar en los artefactos de la corrida si hay un sembrado por DDL o `ExecSQL`. Cambia la lectura de §2.3 y de D21. |
| §2.3 (`checkDimZero` vs `NOT NULL`) | Deducido del fuente con alta confianza, pero **no ejecutado**. | Corrida contra dimensión vacía con el DDL que V1/V3 genera hoy. Es la prueba empírica que vale la pena hacer, en lugar de la que el plan proponía para R-K2. |
| Off-by-one de `DimensionCache.lookupRow` | Leído en el fuente; no reproducido. | Solo importa si se considera `preload_cache=Y`. La recomendación derivada es no considerarlo. |

---

## 9. Fuentes

- [DimensionLookup.java (pentaho-kettle, master)](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/java/org/pentaho/di/trans/steps/dimensionlookup/DimensionLookup.java)
- [DimensionLookupMeta.java](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/java/org/pentaho/di/trans/steps/dimensionlookup/DimensionLookupMeta.java)
- [DimensionCache.java](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/java/org/pentaho/di/trans/steps/dimensionlookup/DimensionCache.java)
- [InsertUpdateMeta.java](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/java/org/pentaho/di/trans/steps/insertupdate/InsertUpdateMeta.java)
- [InsertUpdate.java](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/java/org/pentaho/di/trans/steps/insertupdate/InsertUpdate.java)
- [TableOutput.java](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/java/org/pentaho/di/trans/steps/tableoutput/TableOutput.java)
- [Database.java](https://github.com/pentaho/pentaho-kettle/blob/master/core/src/main/java/org/pentaho/di/core/database/Database.java)
- [BaseDatabaseMeta.java](https://github.com/pentaho/pentaho-kettle/blob/master/core/src/main/java/org/pentaho/di/core/database/BaseDatabaseMeta.java)
- [PostgreSQLDatabaseMeta.java](https://github.com/pentaho/pentaho-kettle/blob/master/core/src/main/java/org/pentaho/di/core/database/PostgreSQLDatabaseMeta.java)
- [Const.java](https://github.com/pentaho/pentaho-kettle/blob/master/core/src/main/java/org/pentaho/di/core/Const.java)
- [TransMeta.java](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/java/org/pentaho/di/trans/TransMeta.java)
- [Combination lookup-update — Pentaho Community Wiki](https://pentaho-community.atlassian.net/wiki/spaces/EAI/pages/371558225/Combination+lookup-update)
- [Combination lookup/update — Apache Hop](https://hop.apache.org/manual/latest/pipeline/transforms/combinationlookup.html)
- [Make a transformation database transactional — Hitachi Vantara / Pentaho docs](https://docs.hitachivantara.com/r/en-us/pentaho-data-integration-and-analytics/9.5.x/mk-95pdia003/data-integration-perspective-in-the-pdi-client/advanced-topics/transactional-databases-and-job-rollback/make-a-transformation-database-transactional)
- [Database transactions in jobs and transformations — Pentaho Community Wiki](https://pentaho-public.atlassian.net/wiki/spaces/EAI/pages/386803253/Database+transactions+in+jobs+and+transformations)
