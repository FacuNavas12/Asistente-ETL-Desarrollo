# Plan de implementación — reparación del generador de ETL

> **Plan confirmado 2026-08-01 — registrado como D55 en `docs/refactor/02-decisiones.md`.** Ese archivo es la fuente de verdad del refactor; esta copia es el detalle de implementación por ítem, D55 tiene el razonamiento y las correcciones de revisión resumidas.
>
> Revisión 2: corrige 3 defectos de "default silencioso" señalados por el usuario en las secciones 1, 7 y 8, y mueve una objeción real desde la sección 3 a OBJECIONES.
> Revisión 3: la regla de la sección 1 ("fields no vacío en modo N es error") quedó refutada contra DimensionLookupMeta.java — corregida a la regla real de D-1 (vocabulario por modo, sin condición sobre si `fields` está vacío). Ver `[REV3]`. También responde la pregunta sobre bloqueo de emisión en el ítem 8.
> Revisión 4: el ítem 4 (semilla `tk=0`) contradecía una decisión ya cerrada del proyecto (D47 — sembrado embebido en el DDL, `ExecSQL`/segundo escritor explícitamente descartado). Reescrito para alinearse con D47: sin `.kjb`, sin `JOBENTRYSQL`. Ver `[REV4]`.
> Revisión 5: la sección 7 (`_sql_projection_has_business_logic`) tenía dos `return False` mudos dentro del `except`/del chequeo de tipo — mismo defecto de clase que motivó la Revisión 2 (default silencioso), esta vez contradiciendo además el precedente ya fijado por D45 pt.1 (SQL no parseable → `Finding(severity=error)`, nunca degradar en silencio) y D5. Verificado contra `sqlglot==30.8.0` real: variable Kettle en posición de identificador (`${VAR}` como schema/tabla) no parsea en ningún dialecto — se neutraliza antes de parsear, en vez de tratarse como SQL roto; `UNION`/`INTERSECT`/`EXCEPT` no son `exp.Select` — el chequeo pasa de `isinstance` a `parsed.find_all(exp.Select)`. Dialecto se mantiene en `None`, documentado por qué. Ver `[REV3]` en la sección 7.
> Revisión 6: barrido de identificadores (variables/funciones/claves de config citadas en cada snippet) contra el código real, archivo por archivo. Encontrados y corregidos: (a) ítem 4 — `dialect` no existe en ningún scope de `etl_generator.py` en los call sites citados; parámetro sacado de la firma, se usa `dialect=None` literal (mismo criterio que las 8 llamadas ya existentes a `parse_ddl()`). Confirmado por grep que el sistema soporta más de un motor destino (`DbType.postgresql`/`sqlserver`, ambos activos en `connection.py:76`/`dialect.py:240-241`) — no cambia la decisión porque el INSERT semilla no genera SQL condicional (`ON CONFLICT`/`MERGE`), la idempotencia la resuelve la detección en Python antes de sintetizar. (b) ítem 8 — `monetary_scale.py` asumía las claves `value_type`/`value_length`/`value_precision` para `Calculator` Y `Formula` por igual; `_step_Formula` (`steps/transform.py:167,186-187`) lee `type`/`length`/`precision` — confirmado también por `system_etl.txt:369`, que documenta la distinción como deliberada. La rama Formula del pass, tal como estaba escrita, era un no-op silencioso. Reescrito con ramificación por canonical type. Además, la reparación mutaba `ktr_data` sin `Finding(repaired=True)` — contradice el contrato propio del paquete (`validators/base.py:9-12`) y el precedente ya en uso (`table_key_recovery.py:63`); corregido. (c) ítem 7 — el snippet usa `parse_cfg`/`ctx.step_type_aliases`, pero `guard_staging_layer.py` no importa `parse_cfg` hoy; agregado. (d) hallazgo colateral en código YA EXISTENTE que el ítem 6 no toca pero cuya superficie hereda: `check_constraint_filter.py:_FIELD_KEYS["DimensionLookup"]` busca la columna destino solo en `table_field`, pero el emisor real (`lookups.py:72`) prioriza `lookup` (`f.get("lookup") or f.get("table_field") or ...`) — un `fields` armado con la clave `lookup` (no sintetizado por el ítem 1, que sí usa `table_field`) queda invisible para el checker. Sumado al ítem 6 como corrección menor. Ver `[REV4]` en la sección 4, `[REV2]` en la sección 6, `[REV2]` en la sección 8.
> Revisión 7: la premisa de `[REV6]` sobre el ítem 4 ("el sistema soporta más de un motor destino") era falsa para el DDL del DWH — verificado (paso 0 a pedido del usuario, 2026-08-01) que el contrato de DDL es Postgres-only sin excepción (`system_inference.txt:86`, `prompt_validacion_src.txt:14`), aunque `DbType.postgresql`/`sqlserver` sí sean dos motores reales de *conexión*. La conclusión operativa de REV6 (`dialect=None` literal, sin ramificar) sobrevive; la premisa se reescribe para no afirmar algo falso. Discrepancia registrada como H52 (`01-hallazgos.md`) y como inventario de puntos de dialecto en § MATERIAL PARA SESIÓN D, para que el trabajo futuro de SQL Server no arranque de cero. Ver `[REV7]` en la sección 4.
> Movido a `docs/refactor/` 2026-08-01 (antes vivía fuera del repo, Desktop). Mutable — no append-only (no es un H ni una D): se reescribe en el mismo turno en que este plan se confirme, se explore un punto marcado abierto, o se impacte una decisión nueva. El detalle de implementación por ítem vive acá; el razonamiento y las correcciones de esta revisión están resumidos en D55, `02-decisiones.md`.

## 1. NUEVA-1 + P1-1/H51 (unidad única) `[REV3]`

**Bibliografía (nueva, agregada en esta revisión):** DimensionLookupMeta.java — `pentaho/pentaho-kettle`, `master` — `getFields()` 741-820, `actualizeWithInjectedValues()` 564-569, `readData()` 930-937, `readRep()` 995-1000.

**Corrección sobre REV2:** la regla "en modo N, `fields` no vacío es error" está refutada por la fuente de arriba. `getFields()` líneas 776-803: `if (!update && fieldLookup.length > 0)` recorre `fields` y agrega cada columna de la dimensión al stream — comentario literal en el fuente, "retrieve extra fields on lookup?" — renombrando por `fieldStream[i]`. `actualizeWithInjectedValues()` (564-569) y `readRep()` (998) lo confirman: en modo lookup, `fields` es el mecanismo de retorno de columnas adicionales, no un residuo de cuando el step era loader. Además, bloquear `fields` no vacío en modo N impide la deduplicación que P3-1 recomienda (un solo lookup devolviendo los atributos que hoy resuelven dos steps). Esa regla se saca del plan.

**Archivos/funciones:**
- `backend/app/services/ktr_builder/steps/lookups.py` — `_step_DimensionLookup` (líneas 56, 74-75), import de `KtrBuilderError` desde `common.py`
- `backend/app/services/ktr_builder/dimension_step_policy.py` — `enforce_dimension_step_policy` (líneas 259-301), branch `role=="fact_lookup"` con `canonical=="DimensionLookup"` (líneas 268-283), y `_has_registered_override` (líneas 137-144, confirmado que existe)
- `backend/app/services/ktr_builder/validators/dimension_lookup_fields.py` — `check_dimension_lookup_fields` (líneas 34-87)
- `backend/app/domain/scd.py` — nueva constante `VALUE_META_TYPE_NAMES`, hermana de `ATTRIBUTE_UPDATE_TYPE_CODES` (línea 387)

**La regla real (D-1, sin condición sobre si `fields` está vacío):** el vocabulario válido de `<field><update>` depende únicamente del modo del step, nunca de si `fields` está poblado. Modo Y → `ATTRIBUTE_UPDATE_TYPE_CODES` (typeCodes: Insert/Update/Punch through/...). Modo N → vocabulario de `ValueMetaFactory` (String/Number/Integer/BigNumber/Date/Boolean/...). Un valor fuera del vocabulario del modo correspondiente es excepción, no fallback — en cualquiera de los dos modos.

**Constante nueva — `domain/scd.py`, junto a `ATTRIBUTE_UPDATE_TYPE_CODES`:**
```python
# Vocabulario de ValueMetaFactory (Kettle) para <field><update> cuando el step
# está en modo N (lookup, D16/D44) — DimensionLookupMeta interpreta el mismo tag
# que en modo Y como nombre de value-meta, no como modo de actualización.
# Subconjunto confirmado contra el contexto de esta serie (String, Number, Date);
# PENDIENTE verificar la lista completa contra ValueMetaFactory.java antes de
# mergear — mismo tipo de verificación de fuente que el ítem 4 (JOBENTRYSQL).
VALUE_META_TYPE_NAMES: tuple[str, ...] = (
    "String", "Number", "Integer", "BigNumber", "Date", "Boolean", "Binary", "Timestamp",
)
```

**Cambio concreto — tres piezas:**

**(a) Validador** (`dimension_lookup_fields.py`), reemplazar el loop de líneas 62-86 para que seleccione vocabulario por modo, sin ninguna condición sobre si `fields` está vacío:
```python
step_update_mode = "Y" if str(cfg.get("update", "Y")).strip().upper() != "N" else "N"
valid_vocab = _VALID_TYPE_CODES if step_update_mode == "Y" else _VALID_VALUE_META_NAMES
vocab_literals = ATTRIBUTE_UPDATE_TYPE_CODES if step_update_mode == "Y" else VALUE_META_TYPE_NAMES

for f in cfg.get("fields", []):
    raw_field_type = f.get("type")
    field_type = str(raw_field_type or "").strip()
    field_name = f.get("stream_field") or f.get("stream") or f.get("name") or "?"
    if not field_type:
        findings.append(Finding(
            severity="error", step_name=step_name,
            message=(
                f"{DIMENSION_LOOKUP_FIELDS_PREFIX}Step '{step_name}' (modo {step_update_mode}), "
                f"atributo '{field_name}': sin 'type' explícito. "
                f"Literales válidos para este modo: {', '.join(vocab_literals)}."
            ),
        ))
    elif field_type.lower() not in valid_vocab:
        findings.append(Finding(
            severity="error", step_name=step_name,
            message=(
                f"{DIMENSION_LOOKUP_FIELDS_PREFIX}Step '{step_name}' (modo {step_update_mode}), "
                f"atributo '{field_name}': type='{raw_field_type}' no pertenece al vocabulario de "
                f"este modo — {', '.join(vocab_literals)}."
            ),
        ))
```
con `_VALID_VALUE_META_NAMES = {c.lower() for c in VALUE_META_TYPE_NAMES}` definida junto a `_VALID_TYPE_CODES` (línea 31 actual).

**(b) Emisor** (`lookups.py`) — con (a), la garantía que justificaba un fallback silencioso (`f.get("type") or "Insert"`) desaparece: en modo N, `fields` puede venir poblado (columnas de retorno del lookup) y su vocabulario correcto ya no es "Insert" por default. Ramifica por modo y levanta excepción si el valor falta o está fuera del vocabulario — mismo criterio que ya usa este mismo módulo en `build.py:376-385` para step type no soportado ("un .ktr que abre pero tiene un step mal formado es peor que uno que no se genera"), aplicado acá al mismo nivel de consecuencia (semántica SCD2 incorrecta en silencio). Reemplazar líneas 74-75:
```python
_sub(field, "update", "Y" if f.get("update", True) else "N")
_sub(field, "type",   f.get("type", "Insert"))
```
por:
```python
valid_vocab = ATTRIBUTE_UPDATE_TYPE_CODES if step_update_mode == "Y" else VALUE_META_TYPE_NAMES
field_value = f.get("type")
if field_value not in valid_vocab:
    raise KtrBuilderError(
        f"DimensionLookup '{el.findtext('name', '?')}': campo con type={field_value!r} fuera "
        f"del vocabulario de modo {step_update_mode} ({', '.join(valid_vocab)}) — "
        "check_dimension_lookup_fields.py debió reportar esto antes; no se emite XML con "
        "vocabulario cruzado (D-1)."
    )
_sub(field, "update", field_value)
```
Sin `<type>` — un solo tag por campo, D-1. La clave interna `f["type"]` no cambia; solo cambia a qué tag XML va y qué vocabulario se exige según el modo. `KtrBuilderError` ya se importa en el resto de `ktr_builder` desde `common.py` (línea 31) — agregar el import a `lookups.py`.

**(c) Checker de rol/tipo** (`dimension_step_policy.py`): dentro de `if canonical in DIMENSION_STEP_TYPES:`, después de `# role == "loader": cae al chequeo general de abajo.` y antes de `if canonical == expected:`, agregar:
```python
if canonical == "DimensionLookup" and str(cfg.get("update", "Y")).strip().upper() != "Y":
    if _has_registered_override(validaciones_modelo, table):  # línea 137-144, ya existe
        results.append({"tipo": "info", "campo": table, "mensaje": (
            f"Step '{step.get('name')}' para '{table}': loader con update=N, override "
            f"'{OVERRIDE_STEP_PREFIX}' registrado — no se corrige, respetado tal cual."
        )})
        continue
    new_cfg = _synthesize_dimension_lookup_config(cfg, contract, update="Y")
    step["config"] = new_cfg
    results.append({"tipo": "warning", "campo": table, "mensaje": (
        f"Step '{step.get('name')}' para '{table}' es el loader (rol) pero tenía "
        "update=N — corregido a update=Y y vocabulario de campos regenerado desde "
        "dim_contracts (H51)."
    )})
    continue
```
El branch de override ya no hace `continue` mudo — deja un finding `tipo="info"` con el motivo, mismo principio que V-1.

También corregir el branch gemelo `role=="fact_lookup"` cuando `canonical=="DimensionLookup"` (línea 281-283): hoy hace `new_cfg = dict(cfg); new_cfg["update"]="N"` sin tocar `fields`. Con (a)/(b) esto deja de ser automáticamente incorrecto (un `fields` con vocabulario Y-mode heredado de cuando el step era loader SÍ sigue siendo un problema real, porque ahora ese modo N interpretaría esos mismos valores contra `VALUE_META_TYPE_NAMES`, y "Insert"/"Update" no pertenecen a ese vocabulario) — el fix se mantiene: `new_cfg = _synthesize_dimension_lookup_config(cfg, contract, update="N")` no reconstruye `fields` para el rol fact_lookup salvo que el contrato declare columnas de retorno adicionales explícitas; revisar si `_synthesize_dimension_lookup_config` necesita un parámetro para eso o si alcanza con limpiar `fields` heredado y dejar que el modelo/override declare las columnas de retorno que de verdad necesita el fact_lookup (P3-1, deduplicación) — **nota, no bloqueo:** el mecanismo de origen de esas columnas de retorno en modo N (qué atributos trae P3-1 a esta rama) no está definido en el contexto de esta tarea; si el fix de deduplicación se planifica, entra como ítem aparte.

**Criterio de aceptación sobre el XML:** en el `.ktr` emitido, para todo `<step><type>DimensionLookup</type>` con `<update>Y</update>`, cada `<fields><field><update>` toma un valor de `{Insert, Update, Punch through, DateInsertedOrUpdated, DateInserted, DateUpdated, LastVersion}`. Para `<update>N</update>`, cada `<fields><field><update>` (si `fields` no está vacío) toma un valor de `VALUE_META_TYPE_NAMES` (String/Number/Integer/BigNumber/Date/Boolean/...) — nunca un valor del vocabulario Y-mode. En ningún caso existe `<fields><field><type>` en un step DimensionLookup. Un `ktr_data` con vocabulario cruzado (ej. modo N + `type="Insert"`) no debe llegar a producir `.ktr` — `build_ktr()` debe levantar `KtrBuilderError`, verificable con `pytest.raises`.

**Dependencias:** ninguna hacia atrás. El ítem 3 depende de este (test de reparación H51 lo ejercita, y ahora también debe cubrir: modo Y con vocabulario correcto, modo N con `fields` poblado y vocabulario correcto — caso legítimo de P3-1 —, y el caso de vocabulario cruzado que debe levantar `KtrBuilderError`).

---

## 2. P1-3 — ConcatFields

**Archivo/función:** `backend/app/services/ktr_builder/steps/transform.py` — `_step_ConcatFields` (líneas 241-252)

**Cambio concreto:** confirmado contra el fixture del repo (`golden_run_base_01/ktr_1_origen_a_staging.ktr:951-955`) — `separator`/`enclosure` van sueltos como ahora (ya correctos), pero `extra_field`/`remove_selected_fields` sueltos no existen en el formato real. Reemplazar:
```python
_sub(el, "extra_field",         cfg.get("target_field", "concat_result"))
...
_sub(el, "remove_selected_fields", "N")
fe = SubElement(el, "fields")
for f in cfg.get("fields", []): ...
```
por: mantener `separator`/`enclosure` al inicio, mover el bloque de destino a **después** de `<fields>`, anidado:
```python
fe = SubElement(el, "fields")
for f in cfg.get("fields", []):
    ...  # sin cambios

concat_el = SubElement(el, "ConcatFields")
_sub(concat_el, "targetFieldName",      cfg.get("target_field", "concat_result"))
_sub(concat_el, "targetFieldLength",    str(cfg.get("target_field_length", 255)))
_sub(concat_el, "removeSelectedFields", "Y" if cfg.get("remove_selected_fields", False) else "N")
```

**Criterio de aceptación sobre el XML:** ningún `<step><type>ConcatFields</type>` tiene `<extra_field>` ni `<remove_selected_fields>` como hijo directo de `<step>`; todos tienen `<ConcatFields><targetFieldName>/<targetFieldLength>/<removeSelectedFields></ConcatFields>` anidado, con los mismos nombres de tag que el fixture del repo.

**Dependencias:** ninguna.

---

## 3. NUEVA-2 — tests que generan, no consumen, el artefacto `[REV2 — suma caso Formula]`

**Archivos:**
- Nuevo archivo `backend/tests/test_build_ktr_emission.py`
- `backend/tests/test_dimension_step_policy.py`

**Cambio concreto:**
1. Nuevo test que arma un `ktr_data` con un step `DimensionLookup` (loader, `update` ausente → default Y, `fields` con vocabulario Y-mode), un step `DimensionLookup` fact_lookup (`update="N"`, `fields` **poblado con vocabulario N-mode válido** — caso legítimo de retorno de columnas, `getFields()` líneas 776-803 de la bibliografía del ítem 1, no el caso vacío), un `ConcatFields`, un `Formula` con un campo `BigNumber` sin `length`/`precision` (`[REV2]`, caso (c) del ítem 8 — sin este step el pass de escala monetaria no se ejercita para la mitad `Formula`), y una tabla con CHECK de rango en `dim_contracts`/DDL; llama `build_ktr(ktr_data, ...)`; parsea el XML resultante con `ElementTree`; assert:
   - loader: `<update>Y</update>` en el step, cada `<fields><field><update>` ∈ `ATTRIBUTE_UPDATE_TYPE_CODES`, sin `<field><type>`.
   - fact_lookup: `<update>N</update>`, cada `<fields><field><update>` ∈ `VALUE_META_TYPE_NAMES`, sin `<field><type>`.
   - ConcatFields: `<ConcatFields><targetFieldName>...` presente, sin `<extra_field>`.
   - Formula: `<formula><value_length>`/`<value_precision>` tomados del DDL (ítem 8, caso c).
2. `[REV3]` caso de vocabulario cruzado: `ktr_data` con `DimensionLookup` `update="N"` y un field con `type="Insert"` (vocabulario Y-mode en modo N) → `build_ktr()` debe levantar `KtrBuilderError` (`pytest.raises`), y por separado `check_dimension_lookup_fields()` sobre el mismo `ktr_data` debe devolver `severity="error"` (los dos gates, validador y emisor, cubiertos por separado).
3. En `test_dimension_step_policy.py`, nuevo test `test_loader_with_update_n_is_repaired_to_update_y` — parte de exactamente el caso H51 (`canonical=="DimensionLookup"`, rol resuelve a `"loader"`, `cfg["update"]="N"`), llama `enforce_dimension_step_policy`, assert `step["config"]["update"]=="Y"`, `step["config"]["fields"]` poblado con vocabulario correcto por atributo (vía `_FakeDimContract`), y `results` trae un finding `tipo="warning"`. Agregar un segundo test para el caso override: mismo setup + validación registrada con `OVERRIDE_STEP_PREFIX` → `results` trae un finding `tipo="info"`, config no se toca.

**Criterio de aceptación:** los tests corren contra el XML/dict de salida de `build_ktr()`/`enforce_dimension_step_policy()`/`check_dimension_lookup_fields()`, no contra fixtures usadas como input. `pytest backend/tests/test_dimension_step_policy.py backend/tests/test_build_ktr_emission.py backend/tests/test_dimension_lookup_fields.py` pasa en verde después de aplicar ítems 1 y 2.

**Dependencias:** depende de 1 y 2.

---

## 4. P1-4 — fila semilla sk=0 `[REV4 — reescrito, mecanismo cambiado]` `[REV6 — parámetro fantasma corregido]`

**Por qué la v1 estaba mal — conflicto con una decisión ya cerrada, no con la investigación de esta sesión:** antes de registrar este plan como decisión (D55, `02-decisiones.md`) hice el chequeo de rutina de revisar las últimas entradas del archivo para elegir el número correlativo, y encontré que **D47** (`02-decisiones.md:1181-1204`, estado "ejecutado", 2026-07-30) ya resuelve el mecanismo del sembrado — y decide explícitamente lo contrario de lo que proponía acá:

> **Decisión — mecanismo del sembrado: embebido en el DDL, no `ExecSQL`.** [...] **Descartado: `ExecSQL` al inicio del `.kjb`.** Agrega un segundo escritor sobre la dimensión — cambiaría la matriz R/W de la Fase 3 y obligaría a garantizar orden respecto del loader (S-13), costo que el sembrado en DDL no tiene.

La v1 de este ítem (entry `JOBENTRYSQL` nueva en el `.kjb`) es la misma familia de mecanismo que D47 ya evaluó y descartó, con una razón concreta que sigue aplicando. Por regla del proyecto, `02-decisiones.md` "manda sobre cualquier análisis o plan que lo contradiga" — no se puede dejar así. Reescrito para alinearse con D47, no para reabrirla.

**Por qué el diagnóstico original (P1-4) sigue en pie — esto no lo reabre:** D47 decidió el *mecanismo* (INSERT sembrado vía `prompt_validacion_src.txt`, I8/V5) pero eso es una instrucción al LLM, no una garantía de código. `validate_and_correct_ddl()` (`ddl_validation.py:77`) — la única pasada que toca el DDL final antes de construir KTR_2 — también es una llamada al modelo, no una síntesis determinista. El grep original de P1-4 ("cero resultados en `app/services`") es coherente con esto: D47 cerró el *diseño*, pero nada en el backend verifica que el modelo realmente emitió el INSERT en una corrida dada. Ese es el gap real que este ítem cierra — sin tocar el mecanismo que D47 ya fijó.

**`[REV6]` Parámetro `dialect` sacado de la firma — no existe en ningún scope de `etl_generator.py`.** La v1 de este ítem (REV4) proponía `synthesize_missing_seed_rows(dwh_ddl, dim_contracts, dialect)` y encadenar el call site pasando una variable `dialect` — verificado contra el código real: en los dos call sites (`~1262`, `~1546`) lo único en scope es `ddl_result = await validate_and_correct_ddl(...)` / `dwh_ddl = ddl_result.dwh_ddl`, ninguna variable `dialect`. Las 8 llamadas reales a `parse_ddl()` que existen en todo `etl_generator.py` usan siempre el literal `dialect=None` — nunca una variable resuelta.

**`[REV7]` Premisa de REV6 corregida — no hay dos motores de DDL, hay uno.** REV6 evaluó un único eje ("¿el INSERT semilla necesita sintaxis condicional por motor — `ON CONFLICT`/`MERGE`/`IF NOT EXISTS`?") y concluyó, correctamente, que no. Pero de ahí saltó a una premisa falsa: que `DbType.postgresql`/`sqlserver` (`connection.py:23-25`, los dos activos como motor de *conexión*) implica que el DDL del DWH pueda salir en dos dialectos. Verificado que no es así — el contrato de DDL es Postgres-only, sin excepción, esté como esté configurada la conexión: `system_inference.txt:86` fija `## DDL` → `"PostgreSQL. Sin esquemas ni prefijos de base."`, instrucción incondicional al LLM; `prompt_validacion_src.txt:14` (I2) solo prescribe sintaxis Postgres para la surrogate key (`SERIAL`/`BIGSERIAL`/`GENERATED BY DEFAULT AS IDENTITY`, prohíbe `GENERATED ALWAYS AS IDENTITY` citando el error Postgres `428C9`) — cero mención de `IDENTITY(1,1)` en ningún prompt vivo. `resolve_real_connections` (`ktr_builder/connection.py:110`) sí diferencia `db_type`, pero solo para la metadata JDBC de la conexión (host/puerto/tipo), nunca para seleccionar el dialecto del texto DDL. Registrado como hallazgo abierto — H52, `01-hallazgos.md` — porque es una discrepancia real y preexistente (una conexión de DWH declarada `sqlserver` recibe igual un `dwh_ddl` en sintaxis Postgres), fuera de alcance de este ítem y de D55.

El eje que sí faltaba evaluar en REV6 — el que motivó volver a esto (paso 0 de la sesión que cierra REV7) — es distinto: no si el INSERT necesita sintaxis condicional, sino si **la columna PK acepta el valor explícito bajo su propia declaración**. Verificado en Postgres, bajo las 3 formas que permite I2: sí — `SERIAL`/`BIGSERIAL` es una columna común con default por secuencia (acepta cualquier valor explícito sin más), y `GENERATED BY DEFAULT AS IDENTITY` acepta valor explícito sin `OVERRIDING SYSTEM VALUE` (esa es la diferencia con `GENERATED ALWAYS`, que sí lo exige — motivo exacto por el que I2 la prohíbe). Bajo `IDENTITY(1,1)` de SQL Server, en cambio, ese mismo INSERT se rechaza sin `SET IDENTITY_INSERT dim_x ON` envolviendo la sentencia — dato que hoy es irrelevante para este ítem (SQL Server no es motor de DDL) pero que **deja de serlo el día que H52 se resuelva y SQL Server pase a ser un dialecto real de `dwh_ddl`**: en ese momento este ítem necesita una segunda rama de síntesis (`SET IDENTITY_INSERT ON` antes del INSERT sembrado / `OFF` después, condicionada al motor) — no alcanza con el `dialect=None` literal actual. Conclusión operativa de REV6 sobrevive intacta (`dialect=None` es correcto **hoy**, con un solo motor de DDL activo); la premisa de por qué sobrevive queda corregida y explícitamente marcada como caduca cuando corresponda, no como cerrada para siempre. Inventario de puntos de dialecto para esa sesión futura, incluido este, en § MATERIAL PARA SESIÓN D.

**Archivos/funciones:**
- `backend/app/services/ddl_validation.py` — nueva función `synthesize_missing_seed_rows(dwh_ddl: str, dim_contracts: list[DimContract]) -> tuple[str, list[str]]` (sin parámetro `dialect`). Para cada tabla en `dim_contracts`: parsea `dwh_ddl` con `sqlglot.parse(dwh_ddl, dialect=None)` (mismo patrón que `parse_ddl`, `ddl_adapter.py:128`, que también usa `dialect=dialect or None` — acá fijo en `None` porque no hay señal de motor resuelta en este punto del pipeline), busca un `exp.Insert` cuyo target de tabla matchee (case-insensitive, con/sin schema — mismo criterio `full`/`bare` que `etl_generator._dwh_column_check_constraints`, `etl_generator.py:240-243`). Detección por presencia, no verificación semántica de columnas (D6-bis, mínimo aceptable — mismo criterio que el pass del ítem 6/7): si existe algún INSERT contra esa tabla, se asume que el LLM siguió I8/V5 y no se toca. Si no existe ninguno, se sintetiza el INSERT completo con los valores exactos de la nota de ejecución de D47 — `technical_key=contract.unknown_key_value` (`schemas/etl_schemas.py:155`, campo real; D47: debe ser `0` para que `checkDimZero` lo encuentre, `WHERE <tk> = 0` literal — no se reinventa el valor acá, se toma del contrato), `version_field=1`, `date_from='1900-01-01 00:00:00'`, `date_to='2199-12-31 23:59:59.999'`, y cualquier columna NOT NULL sin DEFAULT del DDL de esa tabla (ya resuelta por `parse_ddl`) → `'DESCONOCIDO'`/`0` según tipo — y se agrega al texto del DDL final, después de la última definición de esa tabla.
- `backend/app/services/etl_generator.py` — en los 2 call sites de `validate_and_correct_ddl()` (líneas ~1262, ~1546): encadenar `dwh_ddl, seed_warnings = synthesize_missing_seed_rows(ddl_result.dwh_ddl, req.dim_contracts)` (sin tercer argumento) antes de que ese `dwh_ddl` se use para construir KTR_2. `seed_warnings` (lista de "tabla X sin INSERT sembrado, sintetizado" cuando aplica) entra al mismo canal que el resto de advertencias de la etapa — visible, no bloqueante (D15).

**Sin schemas nuevos, sin `.kjb` tocado** — a diferencia de la v1, no hay `JobEntry.entry_type` nuevo ni investigación de formato `JOBENTRYSQL` pendiente (ese bloqueo de fuente de la v1 queda sin objeto).

**Idempotencia:** el detector es por presencia de CUALQUIER INSERT contra la tabla — si ya hay uno (del modelo o de una corrida anterior de este mismo pass), no se duplica.

**Criterio de aceptación sobre el XML:** no aplica a un `.ktr`/`.kjb` — el artefacto de este ítem es el **DDL final** que consume la construcción de KTR_2 (`req.dwh_model` corregido, lo que `_build_ktr_stage` recibe como `dwh_ddl` para STG→DWH). Criterio: dado un `dwh_ddl` donde el modelo omitió el INSERT sembrado para `dim_producto` (I8/V5 no respetado en esa corrida), el `dwh_ddl` que efectivamente llega a la construcción de KTR_2 contiene un `INSERT INTO dim_producto` con `technical_key=0` — verificable parseando ese DDL final con `sqlglot` y confirmando el `exp.Insert` correspondiente, no inspeccionando el prompt.

**Dependencias:** ninguna hacia atrás. Ya no comparte nada con `role_of_dimension_step`/ítem 1 (ese acoplamiento era del mecanismo `.kjb` descartado).

---

## 5. V-1/V-2 — contra-chequeo determinista narración↔XML

**Archivos/funciones:**
- Nuevo: `backend/app/services/ktr_builder/validators/narration_crosscheck.py` — pass pre-emisión: recibe `data["validaciones"]`/`advertencias_buenas_practicas` y `ktr_data`, busca afirmaciones sobre el modo de un DimensionLookup (patrón acotado: menciones de `update=Y`/`"todos los atributos en modo Update"`/nombre de tabla + "SCD2"/"versiona") y las cruza contra `cfg.get("update")`/`cfg["fields"][i]["type"]` reales del step correspondiente.
- `backend/app/services/ktr_builder/validators/__init__.py` — agregar a `PRE_EMIT_PASSES`.
- `backend/app/services/etl_generator.py:825` — el punto donde se arma `validaciones=[*data.get("validaciones",[]), ...]` mezclando narración y hallazgos deterministas: renombrar el canal de la narración del modelo (p. ej. `narracion_modelo`) para diferenciar origen.

**Criterio de aceptación sobre el XML:** dado un caso donde `data["validaciones"]` narra `"update=Y y todos los atributos en modo Update"` para `dim_x`, pero el `<step>` correspondiente en el XML emitido tiene `<update>N</update>`, el pass produce un finding de error.

**`[REV8]` Alcance real tras la implementación — ver D56.** El pass quedó
implementado como estaba especificado, más una pieza que la especificación
no tenía: un Finding severity="info" de cobertura al cierre ("N/M step(s)
DimensionLookup cruzados contra alguna afirmación de la narración"), que
con cobertura 0 declara explícitamente "no verificado" en vez de devolver
lista vacía. Sin eso, un regex que no matchea era indistinguible de una
narración consistente — falso negativo invisible, el mismo modo de falla
de V-1 que este ítem viene a reparar, y cuarta instancia de la clase de
defecto que las revisiones 2, 5 y 6 corrigieron en otros ítems.

La limitación de fondo NO se resolvió y no se resuelve por esta vía:
parsear prosa generada por un LLM para verificar un artefacto es el camino
frágil. La alternativa —derivar el informe del XML emitido— quedó abierta
para la sesión D (GAP-2, prompt-sesion-D.txt Q1), pendiente de contexto
sobre el consumo del informe. Mientras tanto: no se extiende ni se
generaliza el regex. Detalle completo y punto ciego residual (narración
que afirma sobre una dimensión sin ningún step DimensionLookup en el
artefacto) en D56.


**Dependencias:** depende del ítem 1 (necesita que `<update>`/`<field><update>` ya sean el tag real y único a inspeccionar).

---

## 6. P2-1 — mitad restante: condición del CHECK, no solo presencia `[REV2 — hallazgo colateral en _FIELD_KEYS]`

**Verificación previa:** `check_constraint_filter_rows` (`check_constraint_filter.py:56-125`) hoy solo confirma que existe *algún* `FilterRows` sobre el mismo `stream_field` con operador de la familia `{>,>=,<,<=}` (línea 71, 99-100), y separadamente valida `value_type` (líneas 112-124). **No compara `cfg["value"]` contra `bound.get("minimum")`/`bound.get("maximum")`, ni exige que ambos extremos de un rango estén cada uno cubiertos.** Confirmado abierto.

**Archivo/función:** `check_constraint_filter.py` — `check_constraint_filter_rows` (líneas 63-73 recolección, agregar el valor; líneas 90-124 comparación).

**Cambio concreto:** extender la tupla recolectada a `(step_name, field, value_type, operator, value)` (leyendo `cfg.get("value")`, ya presente en `steps/transform.py:75`). Al validar cada columna con bound:
- si `bound.get("minimum")` está declarado, debe existir un filtro con operador `{>,>=}` cuyo `value` sea numéricamente `== bound["minimum"]` (o más estricto) — si no, error: "CHECK exige mínimo X pero el filtro usa Y / no hay filtro de mínimo".
- simétrico para `maximum` con `{<,<=}`.
- mantener el chequeo de `value_type` existente.

**Criterio de aceptación sobre el XML:** con `CHECK (precio >= 0)` y un único `FilterRows` sobre `precio` con `operator=">"` `value="-999"`, el pass reporta error — hoy no lo hace.

**`[REV2]` Hallazgo colateral — `_FIELD_KEYS["DimensionLookup"]` no busca la clave que el emisor real prioriza.** No es parte del cambio pedido originalmente, apareció rastreando las claves que `check_constraint_filter_rows` ya lee hoy contra el emisor real (regla: toda clave de config que un pass lee se rastrea hasta el emisor que la produce). `_FIELD_KEYS["DimensionLookup"]` (`check_constraint_filter.py:40`) declara `dest_keys=("table_field",)` — pero el emisor real, `lookups.py:72`, resuelve la columna destino con `f.get("lookup") or f.get("table_field") or f.get("name", "")`: prioriza `lookup`, `table_field` es el segundo fallback. Un `fields` de `DimensionLookup` armado con la clave `lookup` (válida y prioritaria para el emisor) queda invisible para este checker — `_first(f, ("table_field",))` no la encuentra, `dest_col` sale `""`, `bounds.get("")` no matchea nada, el CHECK de esa columna no se verifica, sin ningún error visible. La ruta de reparación del ítem 1 (`_synthesize_dimension_lookup_config`, `dimension_step_policy.py:178-185`) sí usa `table_field` — así que el gap solo se manifiesta cuando el `fields` viene directo del LLM con la clave `lookup`, no cuando pasó por la síntesis del ítem 1. Mismo gap de prioridad en `stream_keys` (`("stream_field", "stream", "name")`, el emisor real prioriza `stream` antes que `stream_field` — `lookups.py:70`), menos grave porque en la práctica el LLM no suele declarar las dos claves con valores distintos para el mismo campo.

**Cambio adicional — `check_constraint_filter.py:40`:**
```python
"DimensionLookup":  (("lookup", "table_field"), ("stream", "stream_field", "name")),
```
Mismo orden de prioridad que `lookups.py:70,72` — no cambia semántica para `TableOutput`/`InsertUpdate`/`Update` (`_FIELD_KEYS` líneas 37-39, no tocadas, ya coinciden con sus respectivos emisores en `output.py:39-40,71-72,83-84,101-102,109-110`).

**Dependencias:** ninguna.

---

## 7. P2-1b/S-5 — guard_staging_layer inspecciona la proyección SQL `[REV3 — precedente de mecanismo corregido, verificado contra sqlglot real]`

**Por qué la v1 estaba mal:** el caso que motiva esta sección (citado en el contexto original de la tarea) es un `CASE WHEN` en la proyección del `SELECT`:
```sql
CASE WHEN precio_lista < 0 THEN NULL ELSE CAST(precio_lista AS NUMERIC(15,2)) END AS precio_lista
```
Esto no tiene `WHERE` — la heurística `\bWHERE\b` de la v1 no lo detecta. Y en la dirección contraria, esa heurística dispara sobre cualquier extracción legítima con filtro técnico (por fecha, por tenant, por flag de activo), silenciando el checker por ruido. Lo que hay que detectar es **transformación de columnas en la proyección** (`CASE`, `NULLIF`, `COALESCE`, aritmética), no filtrado de filas — `WHERE` queda fuera de alcance de este checker. No hay ninguna decisión del proyecto que acote deliberadamente este guard a `FilterRows` — D53 (que lo creó) lo construyó sobre la única evidencia disponible en su momento (H-5/Set B, un `WHERE` literal), no como exclusión consciente de proyección SQL. Extender su alcance es exactamente lo que D7 pide ("las reglas se derivan de casos reales"), no una reapertura de nada cerrado.

**Por qué la v2 (REV2) también estaba mal — mismo defecto de clase, esta vez con precedente de mecanismo ya fijado en el proyecto:** la v2 tenía dos `return False` mudos:
1. `except Exception: return False` ante SQL no parseable — degradar a un valor vacío dentro de un `except` es exactamente lo que D5 prohíbe ("nada de degradar a valores vacíos dentro de un except... un input inválido produce un error explícito"). Y no es solo un principio general: D45 pt.1 ya fijó el mecanismo concreto para SQL no parseable dentro de esta misma familia de módulos (`ktr_builder/validators/`, mismo `sqlglot`, mismo tipo de pass pre-emisión) — `resolve_sql_tables()`: "SQL no parseable → `Finding(severity=error)`, no aborta (D15)". La v2 citaba "mismo criterio que ddl_adapter/etl_generator" pero ese no es el precedente correcto — `ddl_adapter` parsea DDL de entrada (falla ahí es best-effort porque el DDL es input del usuario, no algo que el sistema deba auditar); acá el guard existe específicamente para detectar una violación, así que tragarse el parseo roto en silencio anula el propósito del checker.
2. `if not isinstance(parsed, exp.Select): return False` — un `TableInput`/`ExecSQL` con `UNION`/`UNION ALL` (`exp.Union`, no `exp.Select`) pasa sin inspección aunque cada rama tenga `CASE WHEN`. Mismo defecto de clase que el `except`, verificado abajo.

**Verificado contra `sqlglot==30.8.0` instalado (venv del repo), antes de fijar el diseño:**
- Variable Kettle en posición de **identificador** (schema/tabla sin comillas) no parsea, en ningún dialecto: `SELECT a FROM ${TARGET_TABLE}` falla con `dialect="postgres"` (pasa con `None`); `SELECT a FROM ${STG_SCHEMA}.productos` y `... JOIN ${STG_SCHEMA}.categorias c ON ...` fallan con los dos. Es un patrón real y legítimo (schema/tabla parametrizado por variable Kettle), no SQL roto — bajo la política simple "no parsea → error" produciría falso positivo indistinguible del caso que el checker existe para atrapar (mismo defecto de la heurística `WHERE`, mudado de lugar).
- Variable Kettle dentro de un **literal** (`WHERE fecha > '${FECHA_DESDE}'`), parámetro posicional (`?`) y parámetro nombrado (`:id`) parsean limpio en ambos dialectos — no son riesgo, no se tocan.
- Sintaxis Postgres real (`::numeric(15,2)`, `ILIKE`, `generate_series`, `DISTINCT ON`) parsea limpio con `dialect=None` y con `"postgres"` — sin divergencia en los casos probados.
- `UNION ALL` con `CASE WHEN` en cada rama resuelve a `exp.Union`; `WITH x AS (...) SELECT CASE WHEN ...` sí resuelve a `exp.Select` (el CTE cuelga del nodo `Select`) y se detecta bien — el gap real es específicamente `UNION`/`INTERSECT`/`EXCEPT`, no CTE.
- No existe en el pipeline ninguna señal de dialecto `sqlglot` ya resuelta para reusar: `services/dialect.py` (`DialectProfiler`/`get_dialect(db_type)`) cotiza identificadores para introspección de esquema en vivo, no selecciona dialecto de `sqlglot` para parsear texto SQL — concepto distinto pese al nombre compartido. `resolve_sql_tables()` (D45 pt.1) y las 8 llamadas a `parse_ddl()` en `etl_generator.py` usan siempre `dialect=None` literal, nunca una variable resuelta. Y en el único caso probado donde importa (`${TARGET_TABLE}` sin schema), pasar a `"postgres"` explícito empeora (falla donde `None` no fallaba) — no hay plumbing que reusar, y construirlo no sería gratis.

**Decisión de diseño resultante — preprocesar antes de parsear, no tratar "no parsea" como una sola categoría:**

**Archivo/función:** `backend/app/services/ktr_builder/validators/guard_staging_layer.py` — `guard_staging_layer` (líneas 53-92), agregar una segunda fuente de detección junto a `filter_names` (líneas 57-61).

**`[REV6]` Import faltante:** `guard_staging_layer.py` hoy solo importa `Finding, ValidationContext` desde `validators.base` — no importa `parse_cfg`, que el snippet de integración usa. Agregar:
```python
from app.services.ktr_builder.contracts import parse_cfg
```
junto al import existente (mismo patrón que `check_constraint_filter.py:22` y `dimension_lookup_fields.py:24`, que ya importan `parse_cfg` de ahí).

```python
import re
import sqlglot
from sqlglot import exp

_BUSINESS_LOGIC_EXPR_TYPES = (exp.Case, exp.Coalesce, exp.Nullif, exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod)

# Neutraliza ${VAR} SOLO en posición de identificador (schema/tabla) — Kettle
# parametriza así, sqlglot no lo entiende en ningún dialecto (verificado:
# "postgres" empeora, no mejora). Dentro de literales/params (?, :id) sqlglot
# ya parsea bien — no se tocan esos casos.
_KETTLE_IDENTIFIER_VAR = re.compile(
    r"\$\{(\w+)\}(?=\s*\.)"                              # ${SCHEMA}.tabla
    r"|\b(?:FROM|JOIN|INTO|UPDATE)\s+\$\{(\w+)\}\b",      # FROM/JOIN/INTO/UPDATE ${TABLA}
    re.IGNORECASE,
)


def _neutralize_kettle_identifier_vars(sql: str) -> str:
    def _sub(m: re.Match) -> str:
        var = m.group(1) or m.group(2)
        return m.group(0).replace(f"${{{var}}}", f"kettle_var_{var.lower()}")
    return _KETTLE_IDENTIFIER_VAR.sub(_sub, sql)


def _sql_projection_has_business_logic(sql: str) -> bool | None:
    """True/False si parsea; None si el SQL está roto de verdad (caller debe
    emitir Finding(severity="error") — D45 pt.1, D5: no degradar en silencio)."""
    if not sql or not sql.strip():
        return False
    try:
        parsed = sqlglot.parse_one(_neutralize_kettle_identifier_vars(sql), dialect=None)
    except Exception:
        return None
    # find_all(exp.Select), no isinstance: cubre UNION/INTERSECT/EXCEPT y
    # subconsultas (un CASE WHEN dentro de un FROM (SELECT ...) también
    # es lógica de negocio en staging) en una sola pasada.
    return any(
        next(projection.find_all(*_BUSINESS_LOGIC_EXPR_TYPES), None) is not None
        for select in parsed.find_all(exp.Select)
        for projection in select.expressions
    )
```
Confirmado con `sqlglot.parse_one("SELECT CASE WHEN precio_lista < 0 THEN NULL ELSE CAST(precio_lista AS NUMERIC(15,2)) END AS precio_lista, COALESCE(x,0) AS x, NULLIF(y,0) AS y, a+b AS c FROM productos", dialect=None)` — cada proyección resuelve a `['Case']`, `['Coalesce']`, `['Nullif']`, `['Add']` respectivamente vía `find_all`. Dialecto se deja en `None` a propósito (ver verificación arriba) — comentario en el propio código, no una omisión.

Integrar en `guard_staging_layer` — el `None` (SQL roto de verdad) se separa de `True`/`False` y genera su propio `Finding`, distinto en mensaje del de lógica de negocio detectada:
```python
for s in steps:
    if ctx.step_type_aliases.get(s.get("type", ""), s.get("type", "")) not in ("TableInput", "ExecSQL"):
        continue
    sql = parse_cfg(s.get("config", {})).get("sql", "")
    has_logic = _sql_projection_has_business_logic(sql)
    if has_logic is None:
        findings.append(Finding(severity="error", step_name=s.get("name", ""),
            message=f"Step '{s.get('name')}': SQL no parseable, no se pudo auditar la proyección — revisar sintaxis."))
    elif has_logic:
        sql_transform_writers.add(s.get("name", ""))
```
y tratar `sql_transform_writers` con el mismo mecanismo de reachability ya existente (`_ancestors` + `staging_writers`, líneas 33-50, 69-91), generando un `Finding` con mensaje propio (menciona CASE/NULLIF/COALESCE/aritmética, no FilterRows).

**Criterio de aceptación sobre el XML:**
- `TableInput` con `<sql>SELECT CASE WHEN precio_lista &lt; 0 THEN NULL ELSE precio_lista END AS precio_lista FROM productos</sql>` alimentando (vía hop) un `TableOutput` a `stg_productos` produce finding de `guard_staging_layer` — hoy no lo hace.
- `TableInput` cuyo `sql` solo tiene `WHERE fecha_baja IS NULL` (filtro técnico, sin transformación de columna) **no** produce finding.
- `TableInput` con `SELECT a FROM ${STG_SCHEMA}.productos` (variable Kettle en schema, sin lógica de negocio) **no** produce finding de ningún tipo — confirma que el preproceso evita el falso positivo.
- `TableInput` con `SELECT CASE WHEN precio<0 THEN NULL ELSE precio END AS precio FROM a UNION ALL SELECT CASE WHEN precio<0 THEN NULL ELSE precio END AS precio FROM b` produce finding de lógica de negocio — confirma que `find_all(exp.Select)` cubre `UNION`.
- `TableInput` con SQL genuinamente roto (paréntesis sin cerrar) produce finding de "no parseable", con mensaje distinto al de lógica de negocio.

**`[REV7]` Riesgo evaluado — origen SQL Server con la política "no parsea → error" de este mismo ítem.** A diferencia del DWH (Postgres-only, H52), el origen sí es multi-motor real: `Connection.db_type`/`InlineConnection.db_type` acepta `sqlserver` para conexiones de origen, y `sqlglot` con `dialect=None` (ANSI genérico) no entiende sintaxis T-SQL (`[identificador]` entre corchetes, `TOP n`) — un `TableInput.sql` legítimamente T-SQL produciría el finding "SQL no parseable" de este mismo ítem, falso positivo sistemático contra un origen SQL Server real. Verificado que **no es un riesgo ya vivo hoy**, por dos motivos: (a) `guard_staging_layer.py` antes de este ítem no parsea SQL en absoluto (sin `import sqlglot`, docstring propio: "TableInput/ExecSQL invisibles") — el mecanismo que podría fallar así no existe todavía; (b) `context_builder.py` no tiene ninguna referencia a `db_type`/motor/engine — ningún canal le informa al LLM que el origen es SQL Server, así que K19 (`system_etl.txt:565`, "asume PostgreSQL salvo que el usuario haya declarado otro motor") es guía sin canal real hoy: en la práctica el `TableInput.sql` que el modelo escribe es siempre ANSI/Postgres-flavored, incluso contra una conexión de origen `sqlserver`. El riesgo se activa el día que alguien conecte ese canal (le pase `db_type` real al prompt de generación) sin ajustar este pass en el mismo cambio — momento en el que hace falta resolver el dialecto real de `sqlglot.parse_one` (`"tsql"` si `db_type=="sqlserver"`) en vez de `None` fijo, mismo patrón que ya existe para DDL-paste de origen (`schema.py:101,118,129` → `ddl_adapter.parse_ddl(ddl, dialect)`, con selector `tsql` real en `InputDDL.jsx:9-12`). No bloquea este ítem — anotado para que quien conecte ese canal en el futuro no reintroduzca el falso positivo.

**Dependencias:** ninguna.

---

## 8. P3-4 (BigNumber) + V-3 (min_year/max_year) `[REV2 — P3-4 reescrito]` `[REV6 — Calculator/Formula ramificado, Finding(repaired=True)]`

**Por qué la v1 estaba mal:** defaultear a `cfg.get("value_length", 18)`/`cfg.get("value_precision", 2)` es exactamente el defecto que este ítem viene a cerrar, solo que con un número más plausible en vez de `-1`. El DDL del caso motivador declara `NUMERIC(15,2)` — 18,2 no coincide. "Precedente estándar de columna monetaria" no es una fuente verificable por columna; es un valor inventado con más autoridad aparente que `-1`.

**La escala tiene que salir del DDL, no de un default.** Ya existe la extracción: `CanonicalField.precision`/`.scale` (`schemas/canonical.py:94-95`) se completan desde `ddl_adapter.py:339-397` cuando el DDL declara `NUMERIC(p,s)`/`DECIMAL(p,s)` — confirmado por lectura de código, no hace falta parsing nuevo. Lo que falta es **el hilo de esa información hasta el paso que arma `Calculator`/`Formula`**, que hoy no la recibe.

**Diseño — reparar cuando se puede resolver desde el DDL, error cuando no se puede (nunca 18,2 fabricado):**

**Archivos/funciones:**
- `backend/app/services/etl_generator.py` — nueva función `_dwh_numeric_scale(dwh_ddl) -> dict[str, tuple[int,int]]`, misma forma/mismo best-effort que `_dwh_column_check_constraints` (líneas 211-244) pero **sin** el filtro de "solo columnas con CHECK" (línea 231) — incluye TODA columna numérica con precisión/escala declarada, indexada por nombre de columna en minúsculas (no por tabla — igual que `v11_monetario_sin_bignumber` ya correlaciona por nombre de campo vía `MONEY_FIELD_HINTS`, sin cruzar por tabla).
- `backend/app/services/ktr_builder/validators/base.py` — `ValidationContext`, agregar `dwh_numeric_scale: dict[str, tuple[int, int]] = field(default_factory=dict)`.
- Wireado en los mismos call sites donde hoy se pasa `dwh_constraints` (`etl_generator.py` líneas ~289-291, 1294-1297, 1564, 1589, 1622) — agregar `dwh_numeric_scale` al lado.
**`[REV6]` Claves de config distintas entre `Calculator` y `Formula` — la v1 asumía las mismas tres para los dos, confirmado incorrecto contra el emisor real.** `_step_Calculator` (`steps/transform.py:156-158`) lee `value_type`/`value_length`/`value_precision`. `_step_Formula` (`steps/transform.py:167,186-187`) lee `type`/`length`/`precision` — claves distintas, no un alias que `normalize_config` resuelva (`contracts.py` — `StepContract` de `"Formula"` solo tiene `key_aliases={"fieldName": "field_name"}`, nada para type/length/precision). Confirmado además por `system_etl.txt:369`, instrucción explícita al LLM: *"Declará `value_length`/`value_precision` (`Calculator`) o `length`/`precision` (`Formula`/`SelectValues`)"* — es una convención de prompt deliberada, no un descuido. La v1 de este pass, escrita con las claves de `Calculator` para ambos steps, era un no-op silencioso para `Formula`: ni detectaba `BigNumber` (buscaba `value_type`, la clave real es `type`) ni, si lo hubiera detectado, la reparación habría tenido efecto (escribía `value_length`/`value_precision`, claves que `_step_Formula` nunca lee).

- Nuevo: `backend/app/services/ktr_builder/validators/monetary_scale.py` — pass pre-emisión, ramificado por canonical type:
  ```python
  MONETARY_SCALE_PREFIX = "[Escala BigNumber] "

  # canonical -> (entries_key, type_key, length_key, precision_key) — claves de
  # INPUT que cada emisor realmente lee, no intercambiables (ver nota arriba).
  _SCALE_KEYS_BY_CANONICAL: dict[str, tuple[str, str, str, str]] = {
      "Calculator": ("calculations", "value_type", "value_length", "value_precision"),
      "Formula":    ("formulas",     "type",       "length",       "precision"),
  }


  def check_monetary_scale(ctx: ValidationContext) -> list[Finding]:
      findings: list[Finding] = []
      for step in ctx.ktr_data.get("steps", []):
          canonical = ctx.step_type_aliases.get(step.get("type", ""), step.get("type", ""))
          keys = _SCALE_KEYS_BY_CANONICAL.get(canonical)
          if keys is None:
              continue
          entries_key, type_key, length_key, precision_key = keys
          cfg = parse_cfg(step.get("config", {}))
          entries = cfg.get(entries_key, cfg.get("fields", []))
          for e in entries:
              if e.get(type_key) != "BigNumber":
                  continue
              field_name = (e.get("field_name") or e.get("name") or "").strip().lower()
              scale = ctx.dwh_numeric_scale.get(field_name)
              has_explicit = e.get(length_key) is not None and e.get(precision_key) is not None
              if scale is not None and not has_explicit:
                  e[length_key], e[precision_key] = scale
                  # D9/D13 (registro de deltas) + contrato del paquete (base.py:9-12,
                  # "toda mutación real va acompañada de un Finding con repaired=True")
                  # — mismo patrón que table_key_recovery.py:61-69 (severity="warning",
                  # repaired=True). La v1 mutaba sin este Finding: reparación sin rastro.
                  findings.append(Finding(
                      severity="warning", step_name=step.get("name", ""), repaired=True,
                      message=(
                          f"{MONETARY_SCALE_PREFIX}Step '{step.get('name')}': campo '{field_name}' "
                          f"tipado BigNumber sin longitud/precisión — completado desde el DDL del DWH "
                          f"({scale[0]},{scale[1]})."
                      ),
                  ))
              elif scale is None and not has_explicit:
                  findings.append(Finding(
                      severity="error", step_name=step.get("name", ""),
                      message=(
                          f"{MONETARY_SCALE_PREFIX}Step '{step.get('name')}': campo '{field_name}' "
                          "tipado BigNumber sin longitud/precisión explícita, y no se pudo resolver "
                          "desde el DDL del DWH (columna no encontrada) — no se fabrica un valor "
                          f"default; declarar {length_key}/{precision_key} en el config o corregir "
                          "el nombre del campo."
                      ),
                  ))
      return findings
  ```
- `backend/app/services/ktr_builder/validators/__init__.py` — agregar `MONETARY_SCALE_PREFIX, check_monetary_scale` al import desde `monetary_scale.py`, a `PRE_EMIT_PASSES` y a `__all__` — mismo patrón que las 5 entradas existentes (`check_constraint_filter.py`/`guard_staging_layer.py` líneas 22-29 del archivo).
- `backend/app/services/ktr_builder/steps/transform.py` — `_step_Calculator`/`_step_Formula` (líneas 157-158, 186-187): **sin cambios de default** — se quedan en `str(c.get("value_length", -1))`/`str(c.get("value_precision", -1))` tal como están hoy. Con el pass de arriba corriendo antes, `cfg` ya trae el valor correcto cuando es resoluble; `-1` solo se emite cuando de verdad no hay fuente — visible en el XML, no oculto detrás de un número que parece intencional.

**Criterio de aceptación sobre el XML:** (a) con `dim_producto.precio_lista NUMERIC(15,2)` en el DDL y un `Calculator` que produce `precio_lista` como `BigNumber` sin longitud/precisión explícita, el XML emitido tiene `<value_length>15</value_length>`/`<value_precision>2</value_precision>` — tomado del DDL, no de un default fijo. (b) con un campo `BigNumber` cuyo nombre no matchea ninguna columna del DDL, el XML sigue mostrando `<value_length>-1</value_length>`/`<value_precision>-1</value_precision>` (sin fabricar nada) **y** existe un finding `severity="error"` — ambas cosas verificables en el mismo test. (c) `[REV6]` mismo caso que (a) pero con un `Formula` (no `Calculator`) produciendo un campo `BigNumber` sin `length`/`precision` — el XML emitido tiene `<value_length>15</value_length>`/`<value_precision>2</value_precision>` en el `<formula>` correspondiente, **y** existe un finding `severity="warning"` con `repaired=True` — sin (c), el test no ejercita la mitad del pass que la v1 dejaba muerta.

**`[REV3]` Respuesta a la pregunta — un finding `severity="error"` de un pass pre-emisión, ¿bloquea la entrega?** No. Confirmado por el propio contrato del paquete: `validators/base.py:9-12` — "un pass PUEDE mutar `ktr_data`, pero toda mutación real debe venir acompañada de un `Finding` con `repaired=True`. Un pass nunca aborta el build por su cuenta — reporta severidad 'error' y deja que el caller decida (D15: notifica, no bloquea)." Y en la práctica, `build.py:163-174`: los findings de `run_passes()` (severidad incluida) se aplanan a `warnings`/`cfg_parse_warnings` vía `split_findings_by_severity` y nunca se usan para levantar excepción — lo único que aborta `build_ktr()` es `incomplete` (claves de config estructuralmente faltantes, línea 156-157) y el `KtrBuilderError` de step-type no soportado (línea 383, mismo mecanismo que el ítem 1 ahora también usa para vocabulario cruzado). Consecuencia directa para este ítem: el caso (b) de más arriba — `BigNumber` sin escala resoluble — **se entrega igual**, con `-1,-1` en el XML y el finding de error solo listado (se promueve a `Validacion tipo=error` en el frontend vía `PRE_EMIT_ERROR_PREFIX`, visible pero no bloqueante). Distinto del ítem 1: ahí el gate real es el `KtrBuilderError` del emisor (capa distinta, sí bloquea), no el finding del validador — por eso el ítem 1 necesita las dos piezas (validador que notifica + emisor que corta) y este ítem 8 se queda solo con la primera, a propósito: acá no hay una fuente confiable para fabricar un valor cuando falla, así que cortar la entrega completa por un campo sin escala sería más disruptivo que dejarlo visible en `-1` y seguir.

**V-3 — decisión, en función del ítem 3:** el ítem 3 no compara byte-a-byte contra `golden_run_base_01` (ver OBJECIONES). Aun así, se decide **emitir `<min_year>`/`<max_year>`** en `_step_DimensionLookup` (default `1900`/`2199`, mismos valores que Kettle usa como fallback interno) — más barato que normalizar comparaciones en cualquier test futuro que sí compare contra un golden real, y el runtime es idéntico con o sin el tag (confirmado por lectura de `readData()`), sin riesgo de regresión.

**Archivo/función:** `steps/lookups.py` — `_step_DimensionLookup`, agregar tras `_sub(el, "batch_size", "0")`:
```python
_sub(el, "min_year", str(cfg.get("min_year", 1900)))
_sub(el, "max_year", str(cfg.get("max_year", 2199)))
```

**Criterio de aceptación sobre el XML:** todo `<step><type>DimensionLookup</type>` tiene `<min_year>`/`<max_year>` como hijos directos del `<step>`, con valor numérico.

**Dependencias:** el nuevo pass de escala monetaria comparte superficie (`ValidationContext`, `validators/__init__.py`) con los ítems 5, 6 y 7 — solo relevante para orden de merge, no hay dependencia lógica entre ellos.

---

## BLOQUEADOS

Ninguno requiere una decisión de usuario pendiente. El único gap real (formato XML de `JOBENTRYSQL` para el ítem 4) es investigación de fuente, no decisión — descrito dentro del ítem 4.

## MATERIAL PARA SESIÓN D

- **`[REV7]` Inventario de puntos de dialecto — para que un futuro soporte de SQL Server como motor de DDL (H52, `01-hallazgos.md`) no arranque de cero.** Contexto: hoy el DDL del DWH es Postgres-only sin excepción (`system_inference.txt:86`, `prompt_validacion_src.txt:14`) — este inventario no es trabajo pendiente de D55, es el mapa de qué tocaría el día que esa decisión se tome.

  **(a) Los 11 puntos `dialect=None` (parseo determinista, no texto de prompt):**
  - 8 preexistentes en `etl_generator.py`, todos `parse_ddl(ddl_o_dwh_ddl, dialect=None)`: líneas 109, 133, 204, 224, 258, 375, 417, 442.
  - +1 que agrega el ítem 4 — `ddl_validation.py`, nueva `synthesize_missing_seed_rows()`: `sqlglot.parse(dwh_ddl, dialect=None)`.
  - +1 que agrega el ítem 7 — `guard_staging_layer.py`, nueva `_sql_projection_has_business_logic()`: `sqlglot.parse_one(sql, dialect=None)` — este parsea SQL de **origen** (`TableInput.sql`/`ExecSQL.sql`), no DDL del DWH; ver riesgo anotado en la sección 7 de este plan (origen sí es multi-motor real hoy, a diferencia del DWH).
  - +1 que agrega el ítem 8 — `etl_generator.py`, nueva `_dwh_numeric_scale()`: `parse_ddl(dwh_ddl, dialect=None)`, mismo patrón que `_dwh_column_check_constraints`.

  **(b) Prompts que prescriben sintaxis Postgres de forma incondicional (texto, no código):**
  - `system_inference.txt:86` — `## DDL` → `"PostgreSQL. Sin esquemas ni prefijos de base."` (contrato completo del DDL del DWH, sin rama por motor).
  - `system_inference.txt:75` / `prompt_validacion_src.txt:14` — I2, sintaxis de surrogate key (`SERIAL`/`BIGSERIAL`/`GENERATED BY DEFAULT AS IDENTITY`), sin equivalente `IDENTITY(1,1)` documentado en ningún lado.
  - `system_etl.txt:565` (K19) — `TableInput.sql`/`ExecSQL.sql` "asume PostgreSQL salvo que el usuario haya declarado otro motor" — la única regla que sí prevé un segundo motor, pero sin canal real que le pase el motor al modelo (ver ítem 7 arriba y punto (d) abajo).

  **(c) Los tres cambios concretos que exigiría SQL Server como motor de DDL, uno por ítem de este plan:**
  - **Ítem 4** — el INSERT semilla pasa de una sentencia suelta a un bloque envuelto en `SET IDENTITY_INSERT <tabla> ON` / `... OFF` alrededor del INSERT (contraparte de `OVERRIDING SYSTEM VALUE` si algún día se permitiera `GENERATED ALWAYS` en Postgres). Confirmado con el paso 0 de esta sesión: bajo `IDENTITY(1,1)`, el `INSERT (technical_key, ...) VALUES (0, ...)` se rechaza sin ese wrapper — a diferencia de las 3 formas que permite I2 en Postgres, que sí lo aceptan directo. `synthesize_missing_seed_rows()` devuelve un splice de texto (se agrega al `dwh_ddl` final, no reemplaza sentencias existentes) — el cambio queda localizado a esa función; confirmar la firma real cuando se implemente, no asumirla desde acá.
  - **Ítem 7** — ver anotación completa en la sección 7. Resumen: `_sql_projection_has_business_logic` necesitaría resolver `dialect="tsql"` cuando el origen sea SQL Server (en vez de `None` fijo), o la política nueva "no parsea → error" produce falsos positivos sistemáticos contra SQL genuinamente T-SQL (`[corchetes]`, `TOP`). Verificado que esto NO es un riesgo ya vivo hoy — recién se activa si se conecta `db_type` real del origen al prompt de generación (`context_builder.py` hoy no tiene ningún canal así) sin ajustar este pass en el mismo cambio.
  - **Ítem 8** — `_dwh_numeric_scale` extrae precisión/escala de columnas declaradas `NUMERIC(p,s)`/`DECIMAL(p,s)` en el DDL. SQL Server tiene `MONEY`/`SMALLMONEY` como tipos monetarios nativos (precisión/escala fijas por el motor, 4 decimales, no declaradas en la sintaxis de columna) — una columna `MONEY` no matchea el patrón `NUMERIC(p,s)` que `_dwh_numeric_scale` busca, y un campo `BigNumber` correlacionado a ella caería en la rama de error "columna no encontrada" de `monetary_scale.py` aunque la columna exista y tenga escala bien definida por el motor. Hoy moot (DWH DDL es Postgres-only, H52) — relevante recién si SQL Server pasa a ser motor real de DDL del DWH.

  **(d) Cuarto punto no anticipado, encontrado escribiendo este inventario — el único que YA es dialect-aware de punta a punta:** el modo "pegar DDL" de origen (`InputDDL.jsx`) tiene selector real `ansi`/`postgres`/`tsql`/`mysql` (`InputDDL.jsx:9-12,32,42,72`) que viaja hasta `POST /api/schema/from-ddl` (`schema.py:101,118,129`, `sqlglot_dialect = None if body.dialect == "ansi" else body.dialect`) y de ahí a `ddl_adapter.parse_ddl(ddl, dialect)` (`ddl_adapter.py:114,128`) — el parseo respeta el dialecto real que el usuario declara, incluido `tsql`. Es el precedente a copiar cuando se resuelva H52 o el riesgo del ítem 7: en vez de inventar un mecanismo nuevo de selección de dialecto, extender esta misma señal (hoy limitada al modo DDL-paste de origen) hasta el DWH y hasta el resto de los caminos de origen (conexión viva, que ya tiene `db_type` en `Connection` pero no lo propaga a `context_builder.py`).

- **Ítem 4 (seed rows), detección por presencia de INSERT, no por columnas/valores exactos** — mismo criterio D6-bis que el resto del plan. Si en el futuro el modelo empieza a emitir INSERTs incompletos (columnas de más/de menos, valor de `technical_key` distinto de `unknown_key_value`) que pasan la detección de presencia pero no cumplen el contrato real de D47, hace falta subir el pass a verificación semántica (parsear columnas/valores del INSERT existente, no solo su presencia) — no evidenciado todavía.
- **`monetary_scale.py` (ítem 8) correlaciona por nombre de campo, sin cruzar por step de escritura destino** — mismo criterio ya usado por `v11_monetario_sin_bignumber` (hints de nombre, no trazado de linaje). Si dos tablas del DWH declaran la misma columna con escalas distintas, `_dwh_numeric_scale` se queda con la primera que encuentra — nunca ocurrió como caso reportado, pero si aparece, la solución de fondo es correlacionar por linaje real (`lineage_builder.py`), no por nombre.
- **El contra-chequeo narración↔XML (ítem 5): el problema no es que sea
  incompleto, es que su incompletitud era invisible.** Cubre un patrón
  acotado (modo update de dimensión) vía regex sobre prosa generada por un
  LLM; fuera de ese patrón no detecta nada, y hasta la corrección de D56
  ese "nada" era indistinguible de "narración consistente". La mitigación
  aplicada (Finding de cobertura N/M) lo hace declarar cuándo no verificó,
  pero no lo vuelve confiable. Generalizar el regex no es el camino: es
  agrandar la superficie de un verificador que falla en silencio.
  La alternativa a evaluar en D es la inversión —derivar el informe del
  XML emitido y sacar la prosa del modelo del rol de fuente de validación—
  registrada como GAP-2 (prompt-sesion-D.txt, Q1). Alcance real, mitigación,
  punto ciego residual y procedencia: D56.
- **`[REV6]` La distinción `value_length`/`value_precision` (`Calculator`) vs. `length`/`precision` (`Formula`/`SelectValues`) vive únicamente en `system_etl.txt:369`** — no hay ningún `key_aliases` en `contracts.py` que la codifique, ni un tipo/schema Python que la haga explícita; el backend depende de que el LLM haya leído esa línea del prompt y de que ningún código nuevo (como la v1 de `monetary_scale.py`, ítem 8) asuma una convención uniforme entre steps que parecen intercambiables. Encontrado al rastrear las claves que el ítem 8 lee contra el emisor real (`steps/transform.py`). No es un bug puntual — es un patrón de riesgo (convención de formato que solo existe en texto de prompt, sin contraparte verificable en código) que puede repetirse en cualquier otro step con más de una forma de nombrar el mismo campo. Candidato a revisar en la próxima sesión de arquitectura: ¿vale centralizar esta clase de convención en `contracts.STEP_CONTRACTS` (aunque sea como metadata, no como `key_aliases` funcional, ya que acá las claves NO son alias del mismo dato — son dos convenciones de nombre distintas para el mismo rol) para que un test de coherencia (mismo espíritu que `test_pdi_step_coherence.py`) pueda detectar el próximo caso sin depender de que alguien lo encuentre a mano?

## OBJECIONES

- **Sección 3 (NUEVA-2), movida acá desde el cuerpo del plan (v1 la había dejado mal ubicada):** no existe en el repo un JSON de entrada (`ktr_data`) que reproduzca `golden_run_base_01` — esos dos `.ktr` son captura de una corrida real sin input companion. Comparar byte-a-byte contra ese golden específico, tal como pedía el enunciado original del ítem 3, no es viable sin reconstruirlo por ingeniería inversa del XML. Esto es una objeción al alcance tal como estaba planteado, no un hallazgo re-abierto: se resolvió generando un `ktr_data` nuevo y mínimo, diseñado para este test, en vez de intentar reproducir el golden existente — la decisión queda documentada en el ítem 3 y aplicada, no bloquea nada.

No hay otras objeciones — el resto de la evidencia del contexto consolidado se sostiene contra lectura directa del código actual (confirmada archivo por archivo antes de planificar sobre cada ítem), y las tres correcciones de esta revisión no contradicen ningún hallazgo cerrado: son errores introducidos en la v1 del plan mismo, no en el contexto que lo originó.
