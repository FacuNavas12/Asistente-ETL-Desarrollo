# Investigación Pentaho — C.10 / C.11 / C.12

> **Alcance:** investigación contra documentación oficial (Pentaho Community Wiki, Apache Hop) y fuente de `pentaho/pentaho-kettle` rama `master`, consultada el 2026-07-30. Complementa `investigacion-kettle-RK1-RK6.md`; no lo contradice en ningún punto (sí lo **extiende** en dos: §C.12.2 y §C.12.4).
> **Niveles de evidencia:** `[DOC]` = documentación oficial del fabricante, cita textual. `[FUENTE]` = leído en el fuente de Kettle. `[INFERENCIA]` = deducción marcada como tal.
> **Anclaje estable:** nombre de clase + método + literal citado. Las líneas son de `master` al día de consulta.

---

## 0. Resumen ejecutivo — qué colapsó y qué sigue siendo decisión

| Pregunta | Estado tras la investigación | Quién decide ahora |
|---|---|---|
| **C.12** | **Colapsa a un solo camino, con evidencia dura.** La doc oficial de Pentaho documenta **explícitamente** el modo de falla (`NOT NULL` — step abortado) **y prescribe el remedio**: pre-sembrar la fila `tk = 0`. El fuente confirma que el pre-sembrado convierte `checkDimZero` en no-op. Además el propio generador de DDL de Pentaho (botón *SQL* del step) emite `date_from`/`date_to` como `TIMESTAMP` **NULLable sin DEFAULT** — o sea el DDL que V1/V3 obliga hoy es más restrictivo que el que el fabricante genera. | **Ya no es elección libre.** Queda decidir el *mecanismo* del sembrado (DDL vs `ExecSQL`), no el *camino*. Ver §C.12.5. |
| **C.12 — 4º camino** | **Existe en Apache Hop, NO en PDI/Kettle.** Hop tiene la casilla *"Do not check or insert the 'unknown' row"*. PDI no la tiene: el bundle i18n completo del step no contiene ninguna etiqueta equivalente y `checkDimZero()` tiene **un solo guard**, `!meta.isUpdate()`. Como este sistema emite `.ktr` de Kettle, el 4º camino **no está disponible**. | Cerrado. No es opción. |
| **C.10** | **El mecanismo queda acotado, no descartado — pero con un límite estructural que no estaba en la mesa.** `Copy rows to result` acumula **todo el stream en heap** sin spill ni tope configurable, y el `.kjb` tiene **un único result rowset global**: no se pueden materializar dos hops cruzados independientes a la vez. Ese límite, no la memoria, es el que decide. | La memoria es riesgo conocido sin número oficial; **el rowset único es un hecho duro** que descarta el mecanismo para >1 hop cruzado. |
| **C.11** | **Confirmado: depende 100 % del `search_path`.** `DatabaseMeta.getQuotedSchemaTableCombination` con `<schema/>` vacío devuelve el nombre de tabla **pelado**, sin ninguna calificación, y `PostgreSQLDatabaseMeta` no interviene. El riesgo es real, no hipotético. **Aparece un lever nuevo:** `PREFERRED_SCHEMA_NAME`, atributo de la `<connection>`, que califica cuando el step no trae schema. | Sigue siendo tuya, pero el lever nuevo abarata mucho la decisión. Ver §C.11.3. |

---

## C.12 — `checkDimZero` vs `date_from NOT NULL` sin DEFAULT

### C.12.1 La doc oficial dice explícitamente qué constraints rompen — y qué hacer

`[DOC]` **Pentaho Community Wiki, "Dimension Lookup-Update", sección Description**, textual:

> *"As a result of the lookup or update operation of this step type, a field is added to the stream containing the technical key of the dimension. In case the field is not found, the value of the dimension entry for not found (0 or 1, based on the type of database) is returned.*
> ***Note***: *This dimension entry is added automatically to the dimension table when the update is first run. **If you have "NOT NULL" fields in your table, adding this empty row and then the entire step will fail!** So make sure that you have a record with the ID field = 0 or 1 in your table if you don't want PDI to insert a potentially invalid empty record."*

Tres lecturas, en orden de peso:

1. **El corolario de R-K2 (§2.3 de `investigacion-kettle-RK1-RK6.md`) está confirmado por el fabricante**, no solo deducido del fuente. La frase es normativa y no ambigua: "the entire step will fail". El H47 sube de `[FUENTE, deducido]` a `[DOC + FUENTE]`.
2. **La doc no dice "todas las columnas deben ser NULLable o tener DEFAULT".** Dice algo distinto y más barato: *garantizá que exista la fila `tk = 0`*. Es decir, el fabricante **no prescribe relajar el DDL** — prescribe **pre-sembrar**. Eso invierte el orden de preferencia que el plan tenía implícito.
3. **La doc reconoce el pre-sembrado como el patrón normal, no como workaround.** En la misma página, sección *Lookup*:

   > *"We suggest you manually add values -1, -2, -3, etc for these special dimension entry cases, **just like you would add the specific details of the "Unknown" row prior to population of the dimension table**."*

   "prior to population of the dimension table" es exactamente el pre-sembrado. Y resuelve, de paso, el hueco de D21: la etiqueta legible del miembro desconocido (`'DESCONOCIDO'`) **la pone el sembrado**, porque `checkDimZero` no la puede poner nunca (inserta dos columnas). La observación abierta de `investigacion-kettle-RK1-RK6.md` §5 ("la corrida reportó `DESCONOCIDO`, verificar de dónde salió") tiene ahora una hipótesis con respaldo oficial: salió de un sembrado, y ese sembrado es el patrón recomendado.

### C.12.2 El pre-sembrado **desactiva** `checkDimZero` — verificado en fuente

`[FUENTE]` `DimensionLookup.checkDimZero()` (—`DimensionLookup.java:1637-1686`), completo y sin elisiones en la parte que importa:

```java
public void checkDimZero() throws KettleException {
  // Don't insert anything when running in lookup mode.
  //
  if ( !meta.isUpdate() ) {
    return;
  }

  DatabaseMeta databaseMeta = meta.getDatabaseMeta();
  int start_tk = databaseMeta.getNotFoundTK( isAutoIncrement() );

  if ( meta.isAutoIncrement() ) {
    // See if there are rows in the table
    // If so, we can't insert the unknown row anymore...
    //
    String sql = "SELECT count(*) FROM " + data.schemaTable
      + " WHERE " + databaseMeta.quoteField( meta.getKeyField() ) + " = " + start_tk;
    RowMetaAndData r = data.db.getOneRow( sql );
    Long count = r.getRowMeta().getInteger( r.getData(), 0 );
    if ( count.longValue() != 0 ) {
      return; // Can't insert below the rows already in there...
    }
  }

  String sql = "SELECT count(*) FROM " + data.schemaTable
    + " WHERE " + databaseMeta.quoteField( meta.getKeyField() ) + " = " + start_tk;
  RowMetaAndData r = data.db.getOneRow( sql );
  Long count = r.getRowMeta().getInteger( r.getData(), 0 );
  if ( count.longValue() == 0 ) {
    String isql = null;
    try {
      if ( !databaseMeta.supportsAutoinc() || !isAutoIncrement() ) {
        isql = "insert into " + data.schemaTable + "("
          + databaseMeta.quoteField( meta.getKeyField() ) + ", "
          + databaseMeta.quoteField( meta.getVersionField() ) + ") values (0, 1)";
      } else {
        isql = databaseMeta.getSQLInsertAutoIncUnknownDimensionRow( data.schemaTable, ... );
      }
      data.db.execStatement( databaseMeta.stripCR( isql ) );
    } catch ( KettleException e ) {
      throw new KettleDatabaseException( "Error inserting 'unknown' row in dimension ["
        + data.schemaTable + "] : " + isql, e );
    }
  }
}
```

Lo accionable, punto por punto:

- **El chequeo es `SELECT count(*) ... WHERE <tk> = 0`, no `count(*)` de la tabla entera.** Basta con que exista **una** fila con `tk = 0` para que `count != 0` y el INSERT no se ejecute nunca. El sembrado no necesita ser exhaustivo ni ordenado respecto del loader: solo tiene que correr antes.
- **El sembrado puede traer todas las columnas que quiera** — descripciones, `date_from`, `date_to`, `'DESCONOCIDO'`. Kettle no lo valida ni lo pisa: `dimUpdate`/`dimPunchThrough` filtran por clave natural o por `tk` resuelto por el lookup, y la fila 0 nunca es resultado de un lookup con clave natural real.
- **Corolario para §1.3 de `investigacion-kettle-RK1-RK6.md`:** el sembrado tiene que respetar el convenio de centinela de Kettle. Una fila 0 con `date_to = NULL` es invisible al lookup, pero eso **no importa** para la fila 0 (nadie la busca por clave natural; se llega a ella por el fallback `notFoundTk`). Lo que sí importa: el sembrado **no** debe usarse para filas reales de negocio con otro convenio. El checker estructural que §1.3 propone sigue siendo el correcto, con la fila `tk = 0` explícitamente exceptuada.

### C.12.3 ¿Hay opción de config para la fila unknown?

**En PDI/Kettle: no. En Apache Hop: sí.** Esto es el hallazgo más inesperado de la sección.

`[DOC]` **Apache Hop, "Dimension lookup/update", pestaña *Technical key creation*:**

> | Option | Description |
> |---|---|
> | **Do not check or insert the 'unknown' row** | *By default, Hop checks whether there is an 'unknown' record available at ID 0 or 1. If no such record is present in the dimension table, this transform adds it. If you check this option you indicate that you take responsibility for adding this record yourself.* |

`[FUENTE]` **PDI/Kettle no tiene esa casilla.** Dos evidencias independientes:

1. `checkDimZero()` (arriba) tiene **un único guard de salida temprana**: `if (!meta.isUpdate()) return;`. No hay ningún flag de meta consultado.
2. El bundle i18n completo del step —`engine/src/main/resources/org/pentaho/di/trans/steps/dimensionlookup/messages/messages_en_US.properties`— no contiene ninguna etiqueta parecida. El grupo de la creación de clave técnica es exactamente:

   ```
   DimensionLookupDialog.TechGroup.Label=Creation of technical key
   DimensionLookupDialog.TableMaximum.Label=Use table maximum + 1
   DimensionLookupDialog.Sequence.Label=Use sequence
   DimensionLookupDialog.Autoincrement.Label=Use auto increment field
   ```

   Y la lista completa de claves de *metadata injection* del step tampoco tiene un flag equivalente (`TECHNICAL_KEY_CREATION`, `TECHNICAL_KEY_SEQUENCE`, `TECHNICAL_KEY_FIELD`, `TECHNICAL_KEY_NEW_NAME`, `PRELOAD_CACHE`, `CACHE_SIZE`, `MIN_YEAR`, `MAX_YEAR`, `USE_ALTERNATIVE_START_DATE`, `ALTERNATIVE_START_OPTION`, `ALTERNATIVE_START_COLUMN`, ?).

**Veredicto:** el "4º camino" existe, pero en el linaje Hop, no en el que este sistema emite. **No entra en la mesa.** Vale registrarlo como dato de portabilidad: si alguna vez se emite para Hop, C.12 se resuelve con un checkbox.

> **Nota de discrepancia doc-vs-fuente, sin impacto:** tanto la wiki de Pentaho como la de Hop dicen que la clave unknown es *"0 or 1, based on the type of database"*. Para Postgres es **0**: `BaseDatabaseMeta.getNotFoundTK(boolean useAutoinc) { return 0; }` y `PostgreSQLDatabaseMeta` no la sobreescribe (archivo leído completo). El "o 1" corresponde a dialectos que sí la sobreescriben. Confirma R-K4 sin cambios: `IfNull — 0` es correcto **para Postgres**.

### C.12.4 El DDL que el propio Pentaho genera — evidencia del fabricante

El step trae un botón **SQL** que genera el DDL de la dimensión (`[DOC]`: *"SQL button — Generates the SQL to build the dimension and allows you to execute this SQL"*). Ese generador es la definición canónica del fabricante de "cómo debe verse esta tabla". Para Postgres:

`[FUENTE]` `PostgreSQLDatabaseMeta.getFieldDefinition(...)`, archivo completo leído:

```java
switch ( type ) {
  case ValueMetaInterface.TYPE_TIMESTAMP:
  case ValueMetaInterface.TYPE_DATE:
    retval += "TIMESTAMP";
    break;
  ...
  case ValueMetaInterface.TYPE_NUMBER:
  case ValueMetaInterface.TYPE_INTEGER:
  case ValueMetaInterface.TYPE_BIGNUMBER:
    if ( fieldname.equalsIgnoreCase( tk ) || fieldname.equalsIgnoreCase( pk ) ) {
      retval += "BIGSERIAL";
    } else { ... }
  ...
}
```

**El método no emite `NOT NULL` para ninguna columna.** Ni para las fechas, ni para las descripciones, ni para la clave natural. La única columna implícitamente `NOT NULL` es la técnica, vía `BIGSERIAL`. Es decir:

- **El DDL recomendado por el fabricante para `date_from`/`date_to` es `TIMESTAMP` NULLable, sin DEFAULT.**
- **El DDL que V1/V3 de `prompt_validacion_src.txt:24-26` obliga hoy (`date_from TIMESTAMP NOT NULL`) es estrictamente más restrictivo que el del fabricante, y es exactamente la restricción que la doc oficial marca como causa de falla.**

`[DOC]` Ejemplo publicado con la misma forma (DDL de tutorial, no generado por el step) — nótese el patrón mixto:

```sql
CREATE TABLE DIM_PERSONS (
  id         integer  NOT NULL,
  first_name CHAR(25) NOT NULL DEFAULT 'N/A',
  last_name  CHAR(25) NOT NULL DEFAULT 'N/A',
  entity_id  integer  NOT NULL DEFAULT 0,
  version    integer,
  date_from  TIMESTAMP,
  date_to    TIMESTAMP,
  PRIMARY KEY (id)
);
```

Regla que se lee ahí y que es consistente con todo lo anterior: **las columnas de negocio pueden ser `NOT NULL` si traen `DEFAULT`; las columnas técnicas de rango (`date_from`, `date_to`) y `version` van NULLables** — porque las llena el step, no el DDL.

> **Sobre "Steel Wheels":** el sample DB de Pentaho es un esquema de ventas transaccional/analítico, no un banco de pruebas de SCD2 con `date_from`/`date_to` cargado por este step. No aporta el patrón buscado. Se registra como **verificado-y-descartado**, no como pendiente.

### C.12.5 Qué queda decidido y qué queda por decidir

**Decidido por evidencia (ya no es elección):**

- El camino **"relajar el DDL a NULLable"** no es el prescrito por el fabricante, aunque funcione. El fabricante prescribe **pre-sembrar la fila `tk = 0`**.
- El camino **"opción de config del step"** no existe en Kettle.
- Por lo tanto: **la Fase 2 necesita un pre-sembrado de la fila 0 en toda dimensión cargada con `DimensionLookup(update=Y)`**, o bien un DDL donde toda columna fuera de `tk`/`version` sea NULLable o tenga DEFAULT. **Y el pre-sembrado domina**, porque además resuelve D21 (etiqueta legible), cosa que relajar el DDL no hace.

**Sigue siendo decisión de producto — pero acotada a *cómo*, no a *qué*:**

| Mecanismo del sembrado | A favor | En contra |
|---|---|---|
| **En el DDL** (`INSERT` en la "Parte 3" de `prompt_validacion_src.txt`, junto a las columnas) | Un solo lugar, determinista, sin step nuevo, sin tocar topología. El DDL ya es responsabilidad de V1/V3 y ya sabe los nombres de las columnas. La fila existe antes de cualquier corrida. | El DDL pasa de "estructura" a "estructura + un dato". |
| **`ExecSQL` al inicio del `.kjb`** | Idempotente por `INSERT ... WHERE NOT EXISTS`; visible en el artefacto. | Agrega un **segundo escritor** sobre la dimensión — cambia la matriz R/W de la Fase 3 y el corte. Y el orden respecto del loader tiene que garantizarse (S-13). |
| **Dejar que Kettle la cree + relajar DDL** | Cero trabajo. | Atributos NULL (D21 no queda gratis), contradice la recomendación explícita del fabricante, y obliga a que **toda** columna de negocio de toda dimensión sea NULLable o tenga DEFAULT — restricción de contrato mucho más cara que un INSERT. |

**Recomendación de la investigación (no decisión):** sembrado en el DDL. Es el único de los tres que no toca la matriz R/W ni el orden del job, y es el único que cierra D21 sin trabajo adicional.

**Un requisito que sale gratis y no estaba escrito:** si se siembra, `version` de la fila 0 debe ser `1` y `tk` debe ser `0` — no por elegancia, sino porque `checkDimZero` chequea `WHERE <tk> = 0` (`getNotFoundTK` = 0 para Postgres) y porque `IfNull — 0` del lado del hecho apunta ahí. Un sembrado con `tk = -1` no desactiva `checkDimZero`.

---

## C.10 — materialización de hops que cruzan grupos

### C.10.1 `Copy rows to result` / `Get rows from result` — qué es, literalmente

`[DOC]` **Pentaho Community Wiki, "Copy rows to result"**, la página entera de descripción:

> *"This step allows you to transfer rows of data **(in memory)** to the next transformation (or job entry) in a job via an internal result row set. It can be used by the Get rows from result step and some job entries that allow to process the internal result row set."*

Y la tabla de opciones tiene **exactamente una fila**: `Step name`. **No hay ningún parámetro de tamaño, de spill a disco, ni de nombre del rowset.** La doc oficial no documenta ningún límite de tamaño — pero tampoco ofrece ninguna palanca.

### C.10.2 Todo en memoria, sin tope, con doble copia transitoria

`[FUENTE]` `RowsToResult.processRow(...)` (archivo completo, 90 líneas):

```java
Object[] r = getRow();
if ( r == null ) { // no more input to be expected...
  getTrans().getResultRows().addAll( data.rows );
  getTrans().setResultRowSet( true );
  setOutputDone();
  return false;
}

// Add all rows to rows buffer...
data.rows.add( new RowMetaAndData( getInputRowMeta(), r ) );
```

Consecuencias medibles:

- **Acumula el stream completo** en `data.rows` (`List<RowMetaAndData>`) y recién al fin de stream lo vuelca. No hay streaming: durante toda la etapa el 100 % de las filas está en heap.
- **Doble copia transitoria en el `addAll` final:** `data.rows` sigue viva mientras se copia a `getResultRows()`. Pico de memoria — 2× el dataset (las referencias `Object[]` se comparten; lo que se duplica es el `RowMetaAndData` wrapper y la estructura de lista).
- **`new RowMetaAndData(getInputRowMeta(), r)` por fila** — cada fila carga su propia referencia a `RowMeta`. No es un costo grande pero sí un objeto por fila.
- **Un `ArrayList` extra por job entry:** `JobEntryTrans.execute` hace `List<RowMetaAndData> rows = new ArrayList<>( result.getRows() )` (—`JobEntryTrans.java:744`) — copia superficial de la lista en **cada** entry del job, aunque no la use.
- **No hay `KETTLE_*` de spill.** El mecanismo no tiene el equivalente de `Sort rows` (que sí escribe a disco al pasar `sort_size`). Cuando no entra, tira `OutOfMemoryError` — que es el reporte empírico que aparece en el foro oficial (~100 MB de datos contra 1 GB de heap, crash justo antes de arrancar la transformación siguiente). **No hay número oficial documentado**, así que ese dato es indicativo, no normativo: `[INFERENCIA]` a partir de reporte de usuario, no de doc.

### C.10.3 Supervivencia entre `JobEntryTrans` del mismo `.kjb` — sí, y con una regla no obvia

`[FUENTE]` `JobEntryTrans.execute(...)`:

```java
Result previousResult = result;              // —:790
...
trans.setPreviousResult( previousResult );   // —:1155
trans.execute( args );                       // —:1192
```

y

```java
protected void updateResult( Result result ) {              // —:1302-1307
  Result newResult = trans.getResult();
  result.clear(); // clear only the numbers, NOT the files or rows.
  result.add( newResult );
  if ( !Utils.isEmpty( newResult.getRows() ) || trans.isResultRowsSet() ) {
    result.setRows( newResult.getRows() );
  }
}
```

Del lado del consumidor, `[FUENTE]` `RowsFromResult.processRow(...)`:

```java
Result previousResult = getTrans().getPreviousResult();
if ( previousResult == null || getLinesRead() >= previousResult.getRows().size() ) {
  setOutputDone();
  return false;
}
RowMetaAndData row = previousResult.getRows().get( (int) getLinesRead() );
```

**Respuestas directas:**

1. **¿Sobrevive entre `JobEntryTrans` distintas del mismo `.kjb`?** **Sí**, y además **atraviesa entries intermedios que no las tocan**: `updateResult` solo reemplaza las filas si la transformación que acaba de correr produjo filas o marcó `setResultRowSet(true)`. Si una etapa intermedia no usa `Copy rows to result`, el rowset anterior **pasa de largo intacto**. Eso es bueno (no hace falta encadenar) y peligroso (una etapa no relacionada las hereda sin pedirlas).
2. **¿Orden garantizado?** **Sí**, dentro de una copia del step: `data.rows` es una lista con `add` en orden de llegada, y `RowsFromResult` lee por índice creciente (`get((int) getLinesRead())`). **No** entre copias: si `Copy rows to result` corre con `copies > 1`, cada copia acumula su propia `data.rows` y el orden de los `addAll` entre copias es el de finalización de hilos — no determinista. Mismo problema si hay **dos** `Copy rows to result` en la misma transformación.
3. **¿Hay un límite documentado?** **De tamaño, no.** De cantidad, sí y es irrelevante: `get((int) getLinesRead())` castea a `int`, y `ArrayList` topea en `2^31-1` filas.
4. **Palanca relacionada, sin documentar en el plan:** el job entry tiene `<clear_rows>` (campo `clearResultRows`, "Clear the result rows before execution"), **default `N`** (`JobEntryTrans.clear()` — `clearResultRows = false`). Con default, las filas se heredan. Es la palanca para aislar una etapa que **no** debe verlas.

### C.10.4 El límite que decide no es la memoria — es que hay **un solo rowset por job**

Esto es lo que convierte C.10 de "elegir mecanismo" en "el mecanismo no alcanza".

`[FUENTE + INFERENCIA]` El `Result` que viaja por el `.kjb` tiene **una** lista de filas (`Result.getRows()`), sin nombre, sin namespace, sin canal. `RowsToResult` hace `getTrans().getResultRows().addAll(...)` sobre esa lista única y `updateResult` la **reemplaza** entera. `RowsFromResult` consume **toda** la lista sin poder filtrar por origen.

Por lo tanto:

- **Un `.kjb` puede materializar como máximo un stream cruzado a la vez.** Dos hops que crucen grupos en la misma etapa **no** se pueden expresar con este mecanismo: el segundo `Copy rows to result` pisa al primero (o se mezclan, con orden no determinista, y el consumidor no los puede separar).
- Encadenar (etapa1 — escribe — etapa2 — lee y vuelve a escribir) es posible pero acopla las etapas: cada etapa que quiera propagar el rowset tiene que reescribirlo entero, en heap, otra vez.
- El esquema es **implícito**: `RowsFromResult` toma `row.getRowMeta()` **de cada fila**, no de un contrato. Filas heterogéneas pasan sin validación y explotan aguas abajo — o peor, no explotan.

**Veredicto para C.10:** el mecanismo nombrado por Kettle existe y funciona, pero es **de un solo canal, sin esquema, y con el dataset entero en heap**. Sirve para el caso degenerado (exactamente un hop cruzado, volumen chico, esquema estable). **No sirve como mecanismo general del corte**, que por construcción puede producir N hops cruzados. Eso deja **tabla temporal de staging** como el único camino que escala — y ahí sí la decisión es tuya, pero es sobre nombre, ciclo de vida y limpieza, no sobre "qué mecanismo".

**Lo que la investigación agrega al diseño de esa tabla, gratis:** si la materialización es una tabla, entra sola a la matriz R/W de la Fase 3 (es un `Table output` + un `Table input`), el orden queda cubierto por el chequeo a nivel etapa (S-13), y el hop cruzado deja de ser un caso especial: se vuelve dos steps normales. `Copy rows to result` haría lo contrario — sería **invisible** a la matriz, igual que hoy lo es `TableInput`, y reintroduciría exactamente la clase de invisibilidad que la Fase 3 existe para eliminar. **Ese, y no la memoria, es el argumento decisivo.**

---

## C.11 — `schema` obligatorio end-to-end

### C.11.1 Cómo resuelve Kettle una tabla sin schema — literal

`[FUENTE]` `DatabaseMeta.getQuotedSchemaTableCombination(String, String)` (—`DatabaseMeta.java:1666-1679`), textual:

```java
public String getQuotedSchemaTableCombination( String schemaName, String tableName ) {
  if ( Utils.isEmpty( schemaName ) ) {
    if ( Utils.isEmpty( getPreferredSchemaName() ) ) {
      return quoteField( environmentSubstitute( tableName ) ); // no need to look further
    } else {
      return databaseInterface.getSchemaTableCombination(
        quoteField( environmentSubstitute( getPreferredSchemaName() ) ),
        quoteField( environmentSubstitute( tableName ) ) );
    }
  } else {
    return databaseInterface.getSchemaTableCombination(
      quoteField( environmentSubstitute( schemaName ) ), quoteField( environmentSubstitute( tableName ) ) );
  }
}
```

y `[FUENTE]` `BaseDatabaseMeta.getSchemaTableCombination(...)`:

```java
public String getSchemaTableCombination( String schemaName, String tablePart ) {
  return schemaName + "." + tablePart;
}
```

**Respuesta a la pregunta, sin ambigüedad:**

- Con `<schema/>` vacío **y sin schema preferido en la conexión**, Kettle emite el **nombre de tabla pelado**. No hay calificación, no hay default, no hay warning.
- **`PostgreSQLDatabaseMeta` NO sobreescribe `getSchemaTableCombination`** (archivo leído completo — el override no existe). Tampoco hay nada específico de Postgres en el camino.
- Por lo tanto **la resolución la hace íntegramente Postgres vía `search_path` de la sesión JDBC**, con el `search_path` que corresponda al rol/base de la conexión.

**Esto es exactamente lo que C-4 sospechaba, confirmado en fuente.** El riesgo no es hipotético: dos usuarios con `search_path` distinto ejecutando el mismo `.ktr` escriben en tablas distintas, sin error, sin diferencia en el artefacto. Y como el `search_path` es estado de sesión del servidor, no viaja en el `.ktr` ni en el `.kjb` — es **irreproducible desde el artefacto**, que es la propiedad que más molesta para un generador.

### C.11.2 El detalle que agrava: la matriz R/W ya está midiendo mal

Consecuencia que cruza con H43 y con el punto 2 de la Fase 3. Hoy `<schema/>` está vacío en todos los steps de los dos sets. Bajo la regla de arriba, eso significa que **la identidad física de la tabla no está determinada por el artefacto**. La clave `(connection, table)` que la Fase 3 propone es correcta **solo si** el par `(connection, search_path)` es estable — y `search_path` no es parte de `connection` en el `.ktr`. Es decir: la clave normalizada de la Fase 3 arregla C-7 (conexiones lógicas múltiples al mismo destino físico) pero **no** arregla el caso simétrico, dos conexiones aparentemente iguales que resuelven a schemas distintos. S-10 tenía razón en sacar `schema` de la clave *por ahora*; esta investigación agrega el motivo por el que hay que volver a meterlo.

### C.11.3 El lever que no estaba en la mesa: `PREFERRED_SCHEMA_NAME`

`[FUENTE]` `BaseDatabaseMeta`:

```java
/**
 * The preferred schema to use if no other has been specified.
 */
public static final String ATTRIBUTE_PREFERRED_SCHEMA_NAME = "PREFERRED_SCHEMA_NAME";
```

Es un atributo de la **conexión** (`<connection><attributes><attribute><code>PREFERRED_SCHEMA_NAME</code>?`), en Spoon la casilla *"Preferred schema name"* de la solapa Advanced. Y por el `if` de §C.11.1, **cuando el step no trae schema, el schema preferido de la conexión se aplica y califica la tabla**.

Esto cambia el costo de la decisión de C.11 de forma material:

| Alcance | Qué hay que tocar | Qué cierra |
|---|---|---|
| **Mínimo — `PREFERRED_SCHEMA_NAME` en la conexión** | Solo el emisor de `<connection>` (un atributo más, junto a lo que D34 ya maneja). **Cero cambios** en `dim_contracts`, en el modelo de staging, en el DDL, y en cada step. | Elimina la dependencia del `search_path`. El artefacto pasa a determinar el schema físico. **No** habilita multi-schema, ni permite meter `schema` en la clave de la matriz (sigue siendo la cadena vacía en cada step). |
| **Completo — `schema` obligatorio end-to-end** | `dim_contracts`, modelo de staging, DDL calificado, `<schema>` en cada step, clave `(connection, schema, table)`. | Todo lo anterior **más** DWH multi-schema y la clave completa de la matriz. |

**Lo que esto significa para la decisión:** el alcance mínimo y el completo dejan de ser el mismo ítem. El riesgo del `search_path` —que es la parte *urgente* y *demostrada*— se cierra con un atributo en la conexión, sin tocar el contrato. La pregunta "¿el sistema soporta DWH multi-schema?" queda separada y **puede posponerse sin cargar con el riesgo**.

**Sigue siendo tu decisión** —la investigación no la tomaó— pero ya no es "todo o nada". Sugeréncia de reencuadre de C.11 en `02-decisiones.md`: partirla en **C.11a** (schema determinado por el artefacto, vía `PREFERRED_SCHEMA_NAME`; barato, cierra C-4) y **C.11b** (multi-schema real y `schema` en la clave de la matriz; alcance de producto).

> **Caveat honesto:** no verifiqué en fuente **dónde** se lee `getConnectSQL()`/el schema preferido durante `Database.connect()`, ni si el `PREFERRED_SCHEMA_NAME` afecta también a la introspección de metadatos (`getTableFields`, el botón *SQL*) o solo a la construcción de SQL de los steps. Lo verificado es el camino de `getQuotedSchemaTableCombination`, que es el que arma el SQL que efectivamente se ejecuta. Ver §Pendientes.

---

## Pendientes y cómo cerrarlos

| Punto | Estado | Cómo cerrarlo |
|---|---|---|
| `checkDimZero` con la fila 0 **ya sembrada** — no-op | `[FUENTE]`, alta confianza, **no ejecutado** | La misma corrida contra dimensión vacía que §2.3 de la investigación previa ya pedía, ahora con dos variantes: con sembrado y sin sembrado. Con sembrado tiene que pasar limpio contra el DDL actual (`date_from NOT NULL`); sin sembrado tiene que abortar. Si aborta con sembrado, algo del sembrado está mal (probablemente `tk —  0`). |
| Alcance de `PREFERRED_SCHEMA_NAME` | `[FUENTE]` sobre el camino de construcción de SQL; **no verificado** para introspección de metadatos ni para el SQL de conexión | Leer `Database.connect(...)` y `Database.getTableFields(...)` en `core/.../database/Database.java`. Importa si se elige el alcance mínimo de §C.11.3. |
| Límite práctico de `Copy rows to result` | Sin número oficial. El único dato es un reporte de foro (~100 MB / heap 1 GB — OOM) | No vale la pena cerrarlo: la decisión de C.10 la resuelve el **rowset único** (§C.10.4), que es un hecho estructural y no depende del volumen. |
| Etiqueta `DESCONOCIDO` de la corrida | Sigue sin verificar en los artefactos, pero ahora **tiene explicación con respaldo oficial**: un sembrado previo, que es el patrón recomendado por Pentaho | Revisar el DDL / `ExecSQL` de la corrida `Base_01`. Si aparece el sembrado, confirma de paso que `checkDimZero` encontró `count != 0` y no hizo nada — y que la Fase 2 ya venía funcionando por esa vía sin que estuviera escrito. |
| Steel Wheels como fuente de patrón SCD | **Verificado y descartado** — no es un sample de SCD2 con rango de vigencia cargado por este step | — |

---

## Fuentes

- [Dimension Lookup-Update — Pentaho Community Wiki](https://pentaho-public.atlassian.net/wiki/spaces/EAI/pages/371558220/Dimension+Lookup-Update)
- [Dimension lookup/update — Apache Hop](https://hop.apache.org/manual/latest/pipeline/transforms/dimensionlookup.html)
- [Copy rows to result — Pentaho Community Wiki](https://pentaho-public.atlassian.net/wiki/spaces/EAI/pages/371558228/Copy+rows+to+result)
- [Get rows from result — Pentaho Community Wiki](https://pentaho-public.atlassian.net/wiki/spaces/EAI/pages/371558227/Get+rows+from+result)
- [DimensionLookup.java (pentaho-kettle, master)](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/java/org/pentaho/di/trans/steps/dimensionlookup/DimensionLookup.java)
- [messages_en_US.properties — dimensionlookup (pentaho-kettle, master)](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/resources/org/pentaho/di/trans/steps/dimensionlookup/messages/messages_en_US.properties)
- [RowsToResult.java (pentaho-kettle, master)](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/java/org/pentaho/di/trans/steps/rowstoresult/RowsToResult.java)
- [RowsFromResult.java (pentaho-kettle, master)](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/java/org/pentaho/di/trans/steps/rowsfromresult/RowsFromResult.java)
- [JobEntryTrans.java (pentaho-kettle, master)](https://github.com/pentaho/pentaho-kettle/blob/master/engine/src/main/java/org/pentaho/di/job/entries/trans/JobEntryTrans.java)
- [DatabaseMeta.java (pentaho-kettle, master)](https://github.com/pentaho/pentaho-kettle/blob/master/core/src/main/java/org/pentaho/di/core/database/DatabaseMeta.java)
- [BaseDatabaseMeta.java (pentaho-kettle, master)](https://github.com/pentaho/pentaho-kettle/blob/master/core/src/main/java/org/pentaho/di/core/database/BaseDatabaseMeta.java)
- [PostgreSQLDatabaseMeta.java (pentaho-kettle, master)](https://github.com/pentaho/pentaho-kettle/blob/master/core/src/main/java/org/pentaho/di/core/database/PostgreSQLDatabaseMeta.java)
- [How Do I calculate "Copy rows to result" memory limit? — Pentaho Forums](https://forums.pentaho.com/threads/70871-How-Do-I-calculate-quot-Copy-rows-to-result-quot-memory-limit/)
- [Understanding the Pentaho Kettle Dimension Insert/Update Step Null Value Behaviour — Diethard Steiner](http://diethardsteiner.blogspot.com/2013/10/understanding-pentaho-kettle-dimension.html)
