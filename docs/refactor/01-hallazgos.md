# Hallazgos — Refactor de fragmentación

**Última actualización:** 2026-07-24

Cada entrada: qué se encontró, evidencia (`archivo:línea`), de qué sesión salió, y estado. Estado se evalúa contra [`02-decisiones.md`](02-decisiones.md) — si una decisión ya cerró el hallazgo, dice cuál.

Todas las líneas de código citadas fueron re-verificadas contra el repo en esta sesión (HEAD `149b836`, rama `run-pentaho`), salvo donde se marca explícitamente "no verificable sin ejecutar".

---

## H1 — Partición fija en 2 KTR

**Qué:** el sistema hoy no tiene noción de "cuántos archivos hacen falta"; siempre son 2 KTR + 1 KJB plano.

**Evidencia:** no localizada con precisión en esta sesión — el material de origen (handoff de fragmentación) señala la existencia del forzado pero no da `archivo:línea` de dónde se fija el número 2. Localizarlo es trabajo de la Fase 1 de investigación ya escrita en el prompt de fragmentación.

**Sesión de origen:** Fragmentación.

**Estado: desinflado (2026-07-22).** No es un hallazgo — es el diseño esperado hoy (Origen→STG / STG→DWH / kjb), y coincide con D1 al 100%: nadie está sorprendido de que sea 2. El `archivo:línea` exacto no hace falta localizarlo por adelantado — va a emerger solo cuando se toquen los archivos generadores durante Track F1/F2, porque la arquitectura del corte deja evidente dónde estaba el número fijo. Única razón para mirarlo temprano, y es barata: confirmar con un grep si el "2" aparece en más de un lugar (afecta el tamaño de Track F1). No es una fase en sí misma.

**Localizado en Track F1 (2026-07-22):** el "2" está hardcodeado en al menos 3 puntos, no 1:
- `backend/app/services/etl_generator.py:782-786` — dos llamadas al LLM, `mode="origen_stg"` / `mode="stg_dwh"` (cada `mode` recorta el prompt para producir exactamente un KTR).
- `backend/app/services/etl_generator.py:931-935` — la misma pareja de llamadas duplicada en un segundo codepath (flujo de reintento/regeneración) — divergencia sin dueño único, mismo patrón que H3/H4 pero para la orquestación de generación, no para el parseo de config. No es un hallazgo nuevo a resolver acá, queda anotado por si F2/F3 lo pisa sin verlo.
- `_build_job_plan` (`etl_generator.py:224-246`) arma `execution_order` con exactamente 2 `JobEntry` fijos (`etl_generator.py:240-244`).
Ningún punto de corte existe todavía — el "2" no es una variable, es la forma del código. Confirma que Track F2 no "ajusta un número", tiene que reemplazar la estructura de 2 llamadas + 2 builds por N.

---

## H2 — `config` del LLM llega como string con JSON escapado adentro

**Qué:** el schema de salida declara `config` como `"type": "string"`, no objeto, forzando al modelo a doble-encodear datos estructurados.

**Evidencia:** `backend/app/schemas/llm_output_schemas/etl_output.py:101-104`:
```
"config": {
    "type": "string",
    "description": ("JSON string with the fields specific to THIS step's type — ...
```
Confirmado además por el docstring del propio archivo (líneas 4-7), que documenta esta decisión como deliberada ("would either require a massive oneOf discriminator or would reject valid configs").

**Sesión de origen:** LLM y flujo.

**Estado:** abierto. El cambio `string → object` está explícitamente en "Deliberadamente no decidido" en `02-decisiones.md` — depende de spike empírico contra Gemini y Anthropic.

---

## H3 — 5 implementaciones duplicadas del mismo parseo de `config`

**Qué:** el mismo parseo defensivo (`json.loads` si viene string, `{}` si falla) está copiado en 5 lugares en vez de vivir en uno.

**Evidencia (verificada, exacta):**
- Canónica: `backend/app/services/ktr_builder/contracts.py:30` — `def parse_cfg(raw) -> dict`
- ~~Copia: `backend/app/services/ktr_builder/dimension_step_policy.py:53`~~ **eliminada 2026-07-22** (ver H4/H11) — ahora importa `contracts.parse_cfg`.
- Copia: `backend/app/services/ktr_builder/validate.py:12` — `def _parse_cfg(raw) -> dict`
- Copia: `backend/app/services/ktr_default_validator.py:63` — `def _parse_cfg(raw) -> dict`
- Copia (nombre distinto, mismo patrón): `backend/app/services/lineage_builder.py:41` — `def _parse_config(raw) -> dict` (nota: la propia `lineage_builder.py` ya importa `contracts.normalize_config` desde 2026-07-22 para `_extract_table` — el import ya existe en el archivo, falta solo reemplazar esta función)

Ya importan la canónica (no duplican): `backend/app/services/ktr_builder/fields_validate.py:22`, `backend/app/services/ktr_builder/repair.py:22`, `backend/app/services/ktr_builder/build.py:26`, `backend/app/services/ktr_builder/dimension_step_policy.py` (nuevo).

**Sesión de origen:** LLM y flujo.

**Estado: resuelto 2026-07-24.** Las 3 copias restantes (`validate.py`, `ktr_default_validator.py`, `lineage_builder.py`) ahora importan `contracts.parse_cfg` (con alias local `_parse_cfg`/`_parse_config` para no tocar sus ~15 call-sites internos) — 0 duplicados propios. Además se encontró y corrigió una duplicación no contada en el conteo original: `backend/app/services/ktr_builder/build.py` tenía 3 reimplementaciones inline del mismo patrón (líneas ~189-194, ~219-224, ~330-334 pre-fix), separadas de su propio import de la canónica en la línea 26 — 2 de las 3 eran código muerto (el pass de normalización de la función, línea ~118, ya mutaba `step["config"]` a dict antes de que esas 2 corrieran) y se simplificaron; la 3ª (en el loop de emisión XML) se dejó como respaldo defensivo con catch explícito. Ver H6 para el mecanismo de fail-fast que esto habilita.

---

## H4 — Conocimiento de dominio duplicado y ya divergente (alias de tabla)

**Qué:** `lineage_builder.py` tiene su propia tabla de tipos de step→campo de tabla, y no conoce los alias (`target_table`, `table_name`) que `contracts.STEP_CONTRACTS` sí resuelve.

**Evidencia (verificada, exacta):**
- `backend/app/services/lineage_builder.py:20-27` — `_TABLE_FIELD_TYPES` es un `set` plano de nombres de step, sin alias.
- `backend/app/services/lineage_builder.py:51-53` — `_extract_table` lee `config.get("table")` directo, sin pasar por alias.
- `backend/app/services/ktr_builder/contracts.py:320,328,334,346,350,354,358` — `key_aliases={"target_table": "table", "table_name": "table", ...}` sí normaliza esos alias.

**Sesión de origen:** LLM y flujo, con eco en el prompt (no ejecutado) de Fase 4 de Arquitectura.

**Estado: resuelto (2026-07-22).** `lineage_builder._extract_table` (`lineage_builder.py:51-56`) ahora llama `contracts.normalize_config(canonical_type, config)` antes de leer `table` — misma fuente de alias que usa el builder XML, ya no una copia propia. `dimension_step_policy.py:96-99` ídem (reemplaza el `or` inline por `normalize_config`) y de paso elimina su copia local de `_parse_cfg` (importa `contracts.parse_cfg` — un duplicado menos de H3). Verificado: `venv/Scripts/python.exe -m pytest tests/test_dimension_step_policy.py tests/test_lineage_builder.py` → 26/26 en verde, sin regresión. Reclasificado por la propia sesión de origen: de "fragilidad, no bug activo" (porque hoy corre siempre después de la normalización, por orden de llamada) a **"bug de corrección esperando su turno"**, porque bajo fragmentación el linaje deja de ser cosmético (ver H5, H10 y `00-objetivo.md`) — ya cerrado antes de que hiciera falta.

**Corrección verificada en esta sesión (2026-07-22, respondiendo pregunta del usuario):** el material de origen afirmaba "el eje dest-side no tiene dueño: `_TABLE_FIELD_KEYS` vive suelto en `dimension_step_policy.py`". Es **incorrecto** — `_TABLE_FIELD_KEYS` vive en `backend/app/services/ktr_default_validator.py:54`, no en `dimension_step_policy.py`. `dimension_step_policy.py` (nuevo en el commit `149b836`, serie `dim_contracts`) no define tabla de campos propia; sí resuelve alias de tabla con un `or` inline en `dimension_step_policy.py:107` (`cfg.get("table") or cfg.get("target_table") or cfg.get("table_name")`) en vez de usar `contracts.STEP_CONTRACTS.key_aliases` — una instancia nueva y chica del mismo patrón de H4, no listada hasta ahora. No bloquea nada: cae dentro del mismo PASO 1 (centralizar dominio) ya planeado.

---

## H5 — Acoplamiento por orden de ejecución, no por tipo (linaje)

**Qué:** `build_lineage` / `stitch_lineage` funcionan porque corren después de `build_ktr`, sin que ningún tipo lo garantice.

**Evidencia (verificada, exacta):**
- `backend/app/services/etl_generator.py:33` — `from app.services.lineage_builder import build_lineage, stitch_lineage`
- `backend/app/services/etl_generator.py:398` — `lineage=build_lineage(ktr_data)`
- `backend/app/services/etl_generator.py:483` — `lineage = stitch_lineage(ktr_data_1, ktr_data_2)`
- `backend/app/services/etl_generator.py:890` — comentario reconoce el riesgo ("Cualquier falla no anticipada (ej. bug en build_lineage) no debe dejar...")

Nota de corrección respecto al material de origen: el hallazgo de la sesión "LLM y flujo" cita estas líneas como si `build_lineage`/`stitch_lineage` estuvieran *definidas* ahí — son *llamadas*; las definiciones viven en `lineage_builder.py`. No cambia el diagnóstico (R10: acoplamiento temporal), corrige la referencia.

**Sesión de origen:** LLM y flujo. Corresponde a la Categoría 1 (R10) del prompt de Fase 4 de Arquitectura — prompt no ejecutado todavía.

**Estado: resuelto (2026-07-22) — ver D15 en `02-decisiones.md`.** Riesgo documentado y notificado, no prerrequisito bloqueante de F2. F1.5 no lo cubre (mantiene alcance H4+H11+H6); F2 diseña el corte apoyándose en `build_lineage()` tal como está, con el acoplamiento R10 todavía presente, y debe emitir aviso accionable cuando no pueda garantizar el orden inferido.

---

## H6 — Fallo silencioso en el parseo de `config` (choca directo con D5/R11)

**Qué:** `lineage_builder._parse_config` degrada un JSON roto a `{}` en vez de fallar.

**Evidencia (verificada, exacta):** `backend/app/services/lineage_builder.py:44-47`:
```python
try:
    return json.loads(raw) if raw.strip() else {}
except json.JSONDecodeError:
    return {}
```
El mismo patrón está en las 4 copias listadas en H3 (`validate.py:14-17`, `dimension_step_policy.py`, `ktr_default_validator.py`, y la canónica `contracts.py` — verificar si esta última ya falla fuerte o también degrada, no confirmado en esta sesión).

**Sesión de origen:** LLM y flujo, doctrina R11 (Arquitectura, `arquitectura-objetivo.md:70`, aún no commiteada al repo).

**Estado: resuelto 2026-07-24.** `contracts.parse_cfg` ahora lanza `ConfigParseError` (subclase de `ValueError`, distinguible de una excepción genérica) en vez de `return {}`. Un solo punto de captura nuevo, `contracts.normalize_step_configs(ktr_data) -> (ktr_data, warnings)`, corre UNA vez en cada uno de los 4 entry points del pipeline (`etl_generator.py`: `generate_etl`, `generate_etl_from_inference`, `generate_etl_async`, `build_etl_from_raw`) — antes de `repair_ktr_steps` — y reemplaza cada `step["config"]` string por su dict parseado, o por `{}` + un warning accionable si el JSON es inválido. A partir de ahí, todo consumidor downstream (fields_validate.py, repair.py, dimension_step_policy.py, lineage_builder.py, validate.py, ktr_default_validator.py, build.py) recibe siempre un dict — nunca vuelve a ver la excepción, sin necesidad de un `try/except` en cada uno de sus ~20 call-sites. `build_ktr` (build.py) mantiene además un catch propio de respaldo para cualquier caller que no pase por el pre-pass. D15 aplica: un config roto no aborta la generación (mejor esfuerzo), solo dispara el warning. Tests: `tests/test_config_parse_fail_fast.py`.

---

## H7 — El builder de KJB no soporta jobs anidados (bloquea la jerarquía de D1)

**Qué:** el diseño objetivo requiere `job_master.kjb` ejecutando `job_origen_stg.kjb` y `job_stg_dwh.kjb` (jobs que ejecutan jobs). Verificado: el backend no tiene ninguna noción de `JobEntryJob` hoy.

**Evidencia (verificada por esta sesión, no en el material original):** búsqueda de `JobEntryJob` en todo `backend/` → cero resultados. Los únicos archivos que tocan la generación de KJB son `backend/app/services/etl_generator.py`, `backend/app/services/job_analyzer.py` y `backend/app/services/kjb_xml_validator.py`, los tres solo con `JobEntryTrans`.

**Sesión de origen:** ninguna — surge de verificar contra el repo la pregunta 3 de la Fase 1 del prompt de fragmentación ("¿`build_kjb_xml` soporta `JobEntryJob` o solo `JobEntryTrans`? ¿Qué haría falta para anidar jobs?"). Esa pregunta estaba planteada como "a investigar"; esta sesión confirma el hecho base (ausencia total) sin resolver el "qué haría falta" — eso sigue siendo trabajo de esa Fase 1.

**"Qué haría falta" — respondido en Track F1 (2026-07-22):**
- `backend/app/services/job_analyzer.py:359-388` — `_trans_entry()` hardcodea `<type>TRANS</type>` (línea 363); es la única función que emite `<entry>`, llamada desde el loop de `build_kjb_xml` (`job_analyzer.py:272-274`).
- `backend/app/schemas/job_schemas.py:42-46` — `JobEntry` no tiene discriminador de tipo (`transformation_name`/`filename`/`rationale`/`order`, nada más): hoy no hay forma de decirle a `build_kjb_xml` "esta entrada es un `.kjb`, no un `.ktr`".
- Falta: (a) discriminador en `JobEntry` (o un modelo paralelo) para distinguir entrada TRANS de entrada JOB; (b) una función `_job_entry()` nueva junto a `_trans_entry()`, con el set de tags de `JobEntryJob` de Kettle (`job_object_id`, `filename`, `pass_export`, etc. — no es swapear el string `<type>`, es una forma de XML distinta); (c) branch en el loop de entries (`job_analyzer.py:272-274`) que despache por tipo de entrada; (d) un call site nuevo que arme el `JobPlan` de `job_master.kjb` apuntando a los `.kjb` de fase (mismo patrón que `_build_job_plan`, `etl_generator.py:224`, pero un nivel arriba).

**Estado: resuelto 2026-07-24.** `JobEntry.entry_type: Literal["trans", "job"] = "trans"` (`job_schemas.py`) — default preserva el comportamiento histórico de todo caller existente sin migración. `_job_entry()` nueva en `job_analyzer.py`, shape verificado contra `JobEntryJob.getXML()` real (pentaho-kettle, ver `kettle-jobentryjob-xml-spec.md` aportado por el usuario): `<type>JOB</type>` + `<specification_method>filename</specification_method>` (obligatorio — sin él, `checkObjectLocationSpecificationMethod()` puede resolver contra un repositorio conectado en vez del archivo en disco) + `<jobname>`/`<directory>`/`<job_object_id>` vacíos (solo aplican a métodos de repositorio). Branch en el loop de `build_kjb_xml` por `entry.entry_type`. Efecto colateral encontrado y corregido: `kjb_xml_validator._check_has_trans_entry` exigía al menos una entrada TRANS — un `job_master.kjb` que delega enteramente en jobs hijos (todas sus entries son JOB) es válido y esa regla lo hubiera rechazado; ampliada a TRANS-o-JOB. Tests: `tests/test_job_entry_job.py` (4 casos: default trans sin cambios, entry JOB con shape correcto, kjb solo-JOB pasa validación, kjb sin ninguna entrada real sigue rechazado).

---

## H8 — Infraestructura de validación ya existe: no debe duplicarse

**Qué:** ya hay un gate estructural genérico wireado al build, y un catálogo de validadores table-driven (V4-V13). El motor de corte de fragmentación (V1/V2/V3, nuevos) debe extenderlos, no vivir en paralelo.

**Evidencia (verificada, exacta):**
- `backend/app/services/ktr_xml_validator.py` existe.
- `backend/app/services/ktr_builder/build.py:46` — `from app.services.ktr_xml_validator import validate_ktr_xml`; `build.py:401` — `validate_ktr_xml(ktr_xml, strict_connections=strict_connections)` (wireado, corre siempre).
- `backend/app/services/ktr_builder/error_catalog_checks.py` — validadores confirmados: `v4_select_values_sin_entradas:79`, `v5_dimension_lookup_columnas_tecnicas:106`, `v6_insert_update_mapeos:171`, `v7_fact_table_output_sin_clave:231`, `v8_truncate_sin_transaccional:253`, `v11_monetario_sin_bignumber:321`, `v13_lookup_key_incompleta:374`.

**Sesión de origen:** Fragmentación (handoff, sección "ACTUALIZACIÓN").

**Estado:** decidido — restricción de diseño ya fijada para cuando se implemente el motor de corte (Fase 3 del prompt de fragmentación, no iniciada).

**Corrección (2026-07-22, ver D15 en `02-decisiones.md`):** no las tres por igual. V1 y V3 son la señal que guía dónde separar — viven en el algoritmo de corte (F2), no extienden este catálogo. Solo **V2** (todo lookup tiene productor) es un chequeo de integridad post-construcción — ese es el que efectivamente extiende `ktr_xml_validator.py`/`error_catalog_checks.py`, con el patrón anota-y-notifica de D15, no el `raise` que usan hoy.

---

## H9 — Errores vivos del generador sobre output fresco

**Qué:** tres errores confirmados en una corrida real reciente:
- **E3** — mapeo invertido (`sk_producto`/`sk_tiempo`) en el step `Cargar Fact Venta` (`InsertUpdate`).
- **E14** — el step `Calcular Importe` (Formula) emite `value_type=Number` en vez de `BigNumber` para un campo monetario.
- **Key vacía** en `CombinationLookup` del step `Lookup o Crear Dim Producto` — fuera de catálogo, no ejecuta en Spoon (el más grave de los tres).

**Evidencia:** nombres de step de una corrida de prueba, documentados en el handoff de Fragmentación, sección "Estado actual". No son `archivo:línea` de código — son identificadores de steps generados por el LLM en esa corrida. **No verificable sin ejecutar** una generación nueva para confirmar que persisten.

**Sesión de origen:** Fragmentación.

**Estado:** abierto. Plan de fix propuesto en el mismo documento (punto 1-4 de "Próximos pasos"): derivación determinista desde `dim_contracts` en backend, no parche de prompt.

---

## H10 — E1/V4 y E2/V5: no evaluados, no arreglados

**Qué:** dos puntos ciegos del corpus de prueba: el modelo no emitió `SelectValues` solo-cast (E1/V4) ni una dimensión SCD2 declarada (E2/V5) en la corrida usada como referencia. No se puede afirmar que estén arreglados, solo que no se ejercitaron.

**Evidencia:** handoff de Fragmentación, sección "Estado actual — No evaluables este run". Sin `archivo:línea` propio — depende de forzar esos casos en una generación nueva.

**Sesión de origen:** Fragmentación.

**Estado:** abierto, pendiente de ejercitar (punto 5 de "Próximos pasos" del handoff).

---

## H11 — `DBLookup` queda fuera del linaje

**Qué:** el linaje no reconoce steps `DBLookup` como tocando ninguna tabla — quedan invisibles para cualquier motor que razone sobre el grafo de dependencias.

**Evidencia (verificada, exacta):** `backend/app/services/lineage_builder.py:20-27` (`_TABLE_FIELD_TYPES`) y `:51-59` (`_extract_table`) — ninguno de los dos incluye `"DBLookup"`; el `if/elif` de `_extract_table` retorna `None` para cualquier tipo no listado.

**Sesión de origen:** LLM y flujo (§6, §9 del hallazgo de borde de entrada).

**Estado: resuelto (2026-07-22).** `DBLookup` agregado a `_TABLE_FIELD_TYPES` (`lineage_builder.py:20-29`) — mismo cambio que cerró H4, ya que agregar el tipo al set y resolver su alias son la misma línea de código una vez centralizado en `contracts.normalize_config`. Verificado manualmente: `_extract_table("DBLookup", {"target_table": "dim_tiempo"})` → `"dim_tiempo"` (antes: `None`, invisible). Tests existentes en verde (26/26, ver H4). Reclasificado por la sesión de origen de "parche barato" a **prerrequisito**: bajo fragmentación, un step invisible para el linaje es una dependencia que no se ve y un orden de KJB que puede salir mal — ya cerrado antes de que hiciera falta.

---

## H12 — Docstring de `etl_output.py` desactualizado y contradictorio con el propio schema

**Qué:** el docstring del módulo describe `config` como si fuera `{"type": "object"}`, y menciona un campo `proceso_etl.steps[*].configuracion` que no existe en el schema real.

**Evidencia (verificada, exacta):** `backend/app/schemas/llm_output_schemas/etl_output.py:4-7` (docstring) dice:
> "Fields proceso_etl.steps[*].configuracion and ktr.steps[*].config are left as {"type": "object"}..."

Pero la definición real, 94 líneas más abajo, es `etl_output.py:101-102`: `"config": {"type": "string", ...}`. Búsqueda de `"configuracion"` en el archivo: solo aparece en el docstring, ninguna vez en las `properties` reales del schema.

**Sesión de origen:** LLM y flujo (§6, listado como "trabajo independiente — hacer ya"). Confirmado con mayor precisión en esta sesión: no solo el campo no existe, el docstring afirma un tipo (`object`) que contradice el tipo real (`string`) del campo que sí existe.

**Estado:** abierto. Fix cosmético, cero riesgo, sin dependencias.

---

## H13 — Objeción de compatibilidad con ETLs guardados: cerrada

**Qué:** el hallazgo de borde de entrada tenía una objeción abierta ("¿qué pasa con los ETLs viejos que dejan de poder abrirse?").

**Sesión de origen:** LLM y flujo (§5, primera fila de la tabla de objeciones).

**Estado:** **cerrado por D3.** Los datos guardados son descartables. Cae también la conclusión previa de que `parse_cfg` "no se puede eliminar nunca" — descansaba enteramente en compatibilidad con filas históricas.

---

## H14 — Colisión con `dim_contracts` (commit 149b836): ya no es riesgo futuro, ya ocurrió

**Qué:** el hallazgo de borde de entrada marcaba como objeción abierta "migrar 18 firmas en 8 archivos choca con `dim_contracts` recién mergeado (commit `149b836`) — verificar trabajo en vuelo antes de ordenar los pasos 1 y 2."

**Evidencia:** `git log` confirma `149b836` es HEAD de la rama actual (`run-pentaho`) — el commit ya está mergeado, no en vuelo. Introdujo `dimension_step_policy.py` (nuevo), `ddl_validation.py` (nuevo), y consumo de `dim_contracts` en `etl_generator.py` e `inference_output.py`.

**Sesión de origen:** LLM y flujo, reclasificado en esta sesión de consolidación.

**Estado:** cambia de naturaleza — de "riesgo a verificar antes de actuar" a "hecho consumado a evaluar". Falta (no hecho en esta sesión, por alcance): confirmar si el trabajo de dedup de `parse_cfg` / centralización de dominio (H3, H4) es compatible con la forma actual de `dimension_step_policy.py` y `contracts.py` tal como quedaron tras ese merge, o si hay que adaptar el plan de migración a la nueva estructura.

---

## H15 — D6 (quién decide la fragmentación) pendiente de re-verificación en frío

**Qué:** la decisión de que el backend decide la fragmentación de forma determinista (no el LLM) está en `02-decisiones.md` como D6, pero marcada ahí mismo: "apoyada en memoria, no en documento. Pendiente de re-verificación en frío antes de aplicar."

**Sesión de origen:** LLM y flujo (§8, primera pregunta abierta) y `02-decisiones.md` mismo.

**Estado: resuelto (2026-07-22).** Re-verificado en frío. Respuesta: **B — el backend, determinístico.** Ver D6 y D6-bis en `02-decisiones.md` para la evidencia completa (`_build_job_plan`, `build_lineage`, `repair_ktr_steps`/`repair_integrity_gaps`/`enforce_dimension_step_policy` como precedentes de mutación determinística post-LLM) y el alcance (D6-bis: solo corrección estructural, nunca legibilidad — descarta formalmente que crear una tabla nueva, agregar una rama de validación, o reescribir SQL cuenten como "fragmentación").

---

## H16 — Gap de generación de surrogate key al pasar de `DimensionLookup` a `InsertUpdate`

**Qué:** en el material de fragmentación, el step `Cargar Dim Producto` pasó de `DimensionLookup` a `InsertUpdate` como parte de una división de KTR. `DimensionLookup` genera el surrogate key (`sk_producto`) como parte de su propia ejecución; `InsertUpdate` no. Si la base de datos tampoco genera ese valor (columna `IDENTITY`, secuencia, o default), el KTR falla al insertar la próxima vez que corra.

**Resultado de la query contra la base real (2026-07-22):**
```json
{"column_name": "sk_producto", "column_default": "nextval('dim_producto_sk_producto_seq'::regclass)", "is_identity": "NO"}
```
La base sí genera `sk_producto` sola, vía secuencia con `DEFAULT` (no `IDENTITY`) — **pero solo si el `INSERT` omite la columna.** Verificado en `backend/app/services/ktr_builder/steps/output.py:43-63` (`_step_InsertUpdate`): arma los `<value>` desde `cfg["fields"]` tal cual vienen, sin excluir claves técnicas/surrogate. Si el step que carga la dimensión mapea algo — aunque sea vacío — a `sk_producto`, el `INSERT` generado incluye la columna y pisa el `DEFAULT`.

**Sesión de origen:** respuesta del usuario a esta sesión de consolidación (2026-07-22), sección C.3. Verificación de código y reformulación en esta sesión.

**Estado:** abierto, ya no "rotura genérica urgente" sino caso puntual a confirmar. `err1.ktr`/`err2.ktr` (`C:\Users\05147\OneDrive\Escritorio\Test_Asistente_ETL\Simplificado\Sol\02\Errores\`, ver D7) contienen `InsertUpdate` + `sk_producto` — candidatos directos para confirmar si el mapeo problemático ocurre de verdad. Análisis de contenido de esos archivos queda para Track F1/F4, no para esta sesión.

**Contenido analizado en Track F2 (2026-07-22):** `Cargar Fact Venta` (`InsertUpdate` sobre `fact_venta`) mapea `sk_producto`/`sk_tiempo` con `rename` a `fk_producto`/`fk_tiempo` (no a `sk_producto` de una tabla dimensión) — **no aplica el gap de H16 tal como estaba planteado**, el `InsertUpdate` de estos fixtures no toca ninguna columna `sk_*` de una dimensión, solo la FK dentro de `fact_venta`. H16 queda sin caso confirmado en este corpus; sigue abierto como riesgo genérico, no instanciado acá.

**Caso hermano confirmado por log real (2026-07-22, R8 de `bitacora_etl_ventas.md`, L3-E01/L6):** dirección opuesta a H16 pero misma causa raíz. `_step_InsertUpdate` (`ktr_builder/steps/output.py:43-63`) es un pass-through fiel de `cfg["keys"]`/`cfg["fields"]` — no agrega ni quita nada. H16 es el caso "una columna técnica aparece en `fields` cuando NO debería" (se filtra el `DEFAULT` de la BD). R8 es el caso inverso confirmado por log real contra Postgres: al cargar una dimensión con clave natural + surrogate `SERIAL` vía `Insert/Update`, si la clave natural va **solo** en `keys` (para el `WHERE` del upsert) y no también en `fields` (con `update:false`), Kettle 9.4 nunca la incluye en la lista de columnas del `INSERT` — la deja tomar el default de la tabla, que para una columna sin `DEFAULT` propio es `NULL`, y viola el `NOT NULL` de la clave natural en la primera fila (`ERROR: null value in column "id_producto"`, confirmado en Lectura 3 de la bitácora). Fix mínimo verificado por log: agregar la clave también como `<value>` con `update=N`. **Regla unificada para ambos casos:** la corrección de un `InsertUpdate` de dimensión (loader) no vive en el builder (que ya es correcto — pass-through fiel) — vive en quien arma el `config` (hoy el LLM vía `system_etl.txt`; si D16 amplía `dim_contracts` a derivar `Insert/Update`, vive ahí). Ruteo: F4 (mientras el config lo arma el LLM) — si D16 se resuelve por el camino 1 (ampliar `dim_contracts`), pasa a ser un requisito del emisor determinístico nuevo, no una regla de prompt.

---

## H21 — Análisis de contenido `err1.ktr`/`err2.ktr`: confirma E4/E5 (doble escritor/carrera sobre `dim_producto`) y E6 (`dim_tiempo` sin productor)

**Qué:** los dos fixtures (`err1.ktr`, `err2.ktr` — casi idénticos, `err2` solo agrega `<meta>` completos en el `SelectValues`) son un único `.ktr` de STG→DWH (`ktr_staging_to_dwh_ventas`) con dos problemas estructurales reales, ambos de los que motivan el refactor (`00-objetivo.md`):

1. **`dim_producto` — doble escritor + carrera (E4/E5).** Dos steps `DimensionLookup` distintos tocan `dim_producto`, ambos R+W (H19, `<update>Y</update>` en los dos):
   - `Cargar Dim Producto` — rama muerta: `Leer Staging Productos → Cargar Dim Producto`, sin hop de salida. Es el "productor" real de la dimensión.
   - `Lookup Dim Producto` — en la rama de hechos: `... → Calcular Importe → Lookup Dim Producto → Lookup Dim Tiempo → Cargar Fact Venta`. Busca el `sk_producto` para la FK, pero al ser `DimensionLookup` con `update=Y` (no `CombinationLookup` ni `DBLookup`) también inserta/actualiza si no matchea.
   - **Sin hop entre las dos ramas.** PDI corre ambas en paralelo (cada step es un thread propio); no hay garantía de que `Cargar Dim Producto` haya commiteado antes de que `Lookup Dim Producto` lea/escriba la misma fila. Confirma exactamente el mecanismo de E4 y E5 descrito en `00-objetivo.md`.

2. **`dim_tiempo` — consultada, nunca cargada (E6).** `Lookup Dim Tiempo` (`DBLookup`, R puro, H19) busca contra `dim_tiempo`. Ningún step en el archivo la escribe — no hay `DimensionLookup`/`CombinationLookup`/`TableOutput`/`InsertUpdate` sobre `dim_tiempo` en ningún lado. Es un `V2` (lookup sin productor) real, no hipotético.

**Consecuencia para el diseño del corte (F2):** el caso real NO es "tabla escrita y leída por el mismo step" (que sería inofensivo, ver H19 sobre `DimensionLookup`/`CombinationLookup`) — es tabla escrita y leída por **dos steps distintos sin hop entre ellos**, ya en componentes conexos separados del grafo de hops. El corte natural en este ejemplo es: `{Leer Staging Productos, Cargar Dim Producto}` → un KTR; el resto (`{Leer Staging Ventas, Filtrar Ventas Anuladas, Descartar Anuladas, Castear Campos Ventas, Calcular Importe, Lookup Dim Producto, Lookup Dim Tiempo, Cargar Fact Venta}`) → otro KTR, ordenados por KJB con el primero antes que el segundo (dims antes que hechos). `dim_tiempo` no dispara corte — dispara notificación (D15).

**Sesión de origen:** Track F2 (2026-07-22), análisis de contenido pedido por D7/03-plan.md como insumo obligatorio del diseño del corte.

**Estado:** entregable — caso de prueba concreto para F2/F3 (D7: "cada caso histórico de falla es también un caso de prueba: debe producir la partición correcta").

**¿C1-bis es un fantasma? — reconciliado (2026-07-22) con `bitacora_etl_ventas.md`.** El `extracto_corte_F2.md` de la bitácora plantea la misma pregunta sobre su propio caso de `dim_producto`: el doble escritor ¿era un conflicto estructural real, o un artefacto de que el step del lado del hecho estaba mal elegido (`DimensionLookup(update=Y)` en vez de un lookup de solo lectura)? **Respuesta, verificada contra código, no contra intuición: no es un fantasma, todavía.** Ver **H22** — hoy no existe ningún tipo de step derivable por `dim_contracts` que sea de solo lectura, así que un lookup del lado del hecho sigue siendo R+W por construcción incluso después de que `enforce_dimension_step_policy` "corrija" su tipo. C1-bis sigue siendo la señal correcta de disparar sobre este patrón — lo que cambia es la ubicación del fix real (ver D16, `02-decisiones.md`): no es un ajuste al algoritmo de corte, es una dependencia externa que el corte no controla.

**C1 necesita una excepción — self-lookup / insert-new-only (nuevo, de `bitacora_etl_ventas.md`, sección 3 del extracto).** El patrón `Leer → DBLookup/StreamLookup (existe?) → FilterRows (no existe) → Table Output` lee y escribe la MISMA tabla dentro de una sola KTR, a propósito y de forma segura (Lectura 3 de la bitácora, reforzado con `UNIQUE` sobre la clave natural — L2-E05/R7). C1 tal cual ("cortar si hay W y R por steps distintos") dispara sobre este patrón y sobre-corta. **Regla de excepción para el algoritmo de F2 (ver reporte F2 abajo):** dentro de un componente de hop ya conexo, si el/los step(s) que leen T son estrictamente aguas arriba (hay camino de hops) del/los step(s) que escriben T, y no al revés, es el idioma "chequear-antes-de-insertar" — no dispara corte. Si la relación es la inversa (se escribe y más adelante se vuelve a leer esperando ver la propia escritura) o no hay relación de hops entre ambos, sigue el trato original (C1 dispara, o "mismo componente sin hop determinable" queda como caso no soportado en la primera vuelta de F3 — ver reporte F2).

---

## H17 — 12 tests en rojo: no son gate hasta triage

**Qué:** el handoff de Fragmentación menciona 12 tests preexistentes en rojo (SystemInfo, job API, schema JSON), "no introducidos por este trabajo". No se puede usar la suite como gate de regresión sin saber si ese rojo informa algo real.

**Sesión de origen:** Fragmentación (handoff), reclasificado en la respuesta del usuario a esta sesión.

**Verificado 2026-07-22 (Track F1.5, H4/H11):** confirmado con `git stash` + rerun contra el código previo a los fixes de H4/H11 — los mismos 12 tests fallan igual con o sin esos cambios (`test_ktr_build_job_api.py` ×6, `test_ktr_builder_fidelity.py::test_systeminfo_not_degraded_to_dummy`, `test_ktr_xml_validator.py` ×3, `test_structured_outputs.py::TestEtlGeneratorUnit` ×2). Preexistentes, confirmado, no reclasificados todavía como *obsoletos* vs *rotos de verdad* (sigue pendiente esa lectura). Adicional, no parte del conteo original de H17: los 37 tests de `test_api.py` fallan siempre en local por `ConnectionError` (no hay server en `localhost:8000` — necesitan `uvicorn` corriendo, ambiental, no señal de bug) y `test_structured_outputs.py::TestEtlGeneratorIntegration::test_etl_generate_adversarial_prompt` es flaky (pega a Gemini real, falla por `MAX_TOKENS` según la corrida) — ninguno de los dos es candidato a triage de H17, son ruido de entorno reconocido, no tests rojos por bug.

**Estado: cerrado — triage completo (2026-07-24).** Leídos y clasificados los 12, uno por uno, contra el código committeado en HEAD (`git show HEAD:<archivo>`, sin tocar working tree — ningún cambio de esta sesión ni de F1.5/F2.5 sin commitear influyó el resultado):

- **Obsoletos, corregidos en esta sesión (4 de los 12 rojos + 1 extra que ya pasaba por la razón equivocada):** `test_systeminfo_not_degraded_to_dummy`, `test_get_system_info_without_fields_rejected`, `test_build_ktr_generic_connection_without_real_data_gets_driver_attributes`, `test_build_response_uses_json_data` — todos por el mismo patrón, `<type>GetSystemInfo</type>` a mano en vez de `SystemInfo` (ID real del plugin Kettle, `_XML_TYPE_OVERRIDES` en `build.py`, ya así desde antes de esta sesión) o el literal `"SELECT 1"` como relleno de fixture, que `build.py` rechaza a propósito como placeholder no-query (H16). Sin ambigüedad: comportamiento cambiado a propósito, fixture no actualizada. De paso, `test_get_system_info_with_fields_passes` (no estaba en rojo) se corrigió igual — pasaba por una razón incorrecta (el chequeo de children nunca se disparaba para `<type>GetSystemInfo</type>`, no porque los fields estuvieran bien formados).
- **Rotos de verdad (8, quedan abiertos):** los 6 de `test_ktr_build_job_api.py` (conexiones `conn_dwh`/`conn_staging`) — ver **H24** — más `test_build_ktr_get_system_info_without_fields_gets_default_field` — ver **H25** — más `test_etl_schema_validates_minimal` — ver **H26**.

Los 37 de `test_api.py` (requieren servidor local en `localhost:8000`) y el flaky de `test_etl_generate_adversarial_prompt` (pega a Gemini real) siguen sin ser candidatos a H17 — ruido de entorno reconocido, no bug.

---

## H18 — Auditoría retroactiva de cambios no declarados: alcance sin acotar

**Qué:** el material de fragmentación es un autorreporte de sesión, no evidencia independiente contra el diff real. Ya se confirmó al menos un caso de afirmación no verificada que resultó incorrecta (H4 — ubicación de `_TABLE_FIELD_KEYS`). Falta un chequeo mecánico: por cada commit que tocó generación de KTR, comparar mensaje de commit + lo declarado en la doc contra el diff canónico normalizado (mismo criterio de H-delta que usa D9).

**Sesión de origen:** respuesta del usuario a esta sesión de consolidación (2026-07-22), sección C.4.

**Estado:** abierto. Falta decidir hasta qué commit hacia atrás tiene sentido ir — sin eso, la tarea no está acotada y no se puede estimar.

---

## H19 — Matriz tipo_step → {R,W} sobre tabla (Track F1, entregable Q2)

**Qué:** ningún módulo hoy modela "qué tabla toca cada step y en qué modo" como dato de primera clase (ver H4) — la pregunta 2 de la Fase 1 del handoff pide construirla. Resultado, verificado contra los builders (`backend/app/services/ktr_builder/steps/lookups.py`, `output.py`) y el catálogo (`backend/prompts/system_etl.txt`):

| Tipo | Modo | Evidencia |
|---|---|---|
| `TableInput` | R | lee tablas arbitrarias del `FROM`/`JOIN` del SQL — extracción hoy solo en `lineage_builder._TABLE_RE` (lineage_builder.py:29-34), no en `contracts.py` |
| `TableOutput` | W | `table` directo, `steps/output.py` |
| `InsertUpdate` | W | ídem |
| `Update` | W | ídem |
| `Delete` | W | ídem |
| `DimensionLookup` | **R+W siempre** | `_step_DimensionLookup` (`ktr_builder/steps/lookups.py:47`) hardcodea `<update>Y</update>` sin condición — todo `DimensionLookup` que emite este backend hace lookup (R) e insert/update de SCD (W) sobre la misma tabla. No es un caso a detectar, es el único caso que existe |
| `CombinationLookup` | **R+W siempre** | semántica nativa de Kettle ("Lookup/Update"): inserta la combinación si no existe. El builder (`lookups.py:117-131`) no tiene ningún flag `update` porque no hace falta — el step no tiene modo "solo lectura" |
| `DBLookup` | R | sin bloque de insert/update en el builder (`lookups.py:84-99`); el catálogo lo declara explícito ("SIN generar surrogate key ni manejar SCD", `system_etl.txt:271`) |
| `StreamLookup` | — (no toca tabla) | busca contra OTRO stream en memoria, no BD (`lookups.py:134+`) — fuera de la matriz R/W por diseño, no un gap |
| `ExecSQL` | **no clasificable estáticamente** | SQL arbitrario (`system_etl.txt:316-319`), puede ser R o W según el texto. Ni `contracts.py` ni `lineage_builder.py` lo tocan hoy. El motor de corte tiene que fallar fuerte (D5) ante un `ExecSQL`, no asumir modo |

**Sesión de origen:** Track F1 (2026-07-22), respondiendo la pregunta 2 del handoff de Fragmentación.

**Estado:** entregable, no problema — insumo directo para F2 (regla C1: toda tabla W y R en la misma etapa marca corte). El caso doble-modo de `DimensionLookup` citado en el prompt del handoff está confirmado como real y como el ÚNICO modo, no una posibilidad condicional.

---

## H20 — Punto de inserción del corte: entre `repair_integrity_gaps` y `build_ktr`

**Qué:** la pregunta 5 de la Fase 1 (¿se puede construir la matriz R/W sin re-parsear el XML final?) tiene respuesta: sí. `build_lineage(ktr_data)` (`backend/app/services/lineage_builder.py:87-132`) ya opera sobre el dict pre-XML (`steps[].config`, la misma forma que `data_1["ktr"]`/`data_2["ktr"]`), sin tocar XML — precedente directo (mismo dato citado en D6, evidencia #3). El fallback por XML (`_parse_ktr_xml`, `lineage_builder.py:216-250`) solo existe para el flujo `CreateJob`, que analiza `.ktr` de autoría externa sin dict propio — no aplica al flujo de generación, donde el dict ya está en memoria.

**Consecuencia — dónde insertar el corte:** después de `repair_integrity_gaps` y antes de `build_ktr()` (hoy en `etl_generator.py:801-804` → `:438-460`), mismo punto del pipeline que ya usan las otras mutaciones determinísticas post-LLM (`repair_ktr_steps`, `repair_integrity_gaps`, `enforce_dimension_step_policy` — ver D6 evidencia #4). El corte necesita el dict ya reparado/íntegro (para no fragmentar sobre datos que todavía van a cambiar) pero antes de que se congele en XML.

**Nota — Q4 no tiene precedente de orden por FK:** `_build_job_plan` (`etl_generator.py:224-246`) no ordena nada — arma una lista fija de 2 `JobEntry` porque el orden STG-antes-que-DWH nunca fue ambiguo con solo 2 archivos (docstring explícito, `etl_generator.py:225-229`). Bajo fragmentación (N>1 por etapa), el ordenamiento por grafo de FK que pide `00-objetivo.md` ("dimensiones antes que hechos") es lógica nueva — no existe ningún código hoy que ordene componentes por dependencia, ni en `_build_job_plan` ni en otro lado.

**Sesión de origen:** Track F1 (2026-07-22), preguntas 4 y 5 del handoff.

**Estado:** entregable — responde la recomendación pedida como cierre de F1 ("dónde insertar el corte").

---

## H22 — `dim_contracts`/`dimension_step_policy` no deriva ningún step de solo lectura (prerrequisito real de F3, no fantasma)

**Qué:** `derive_dimension_step_type` (`dimension_step_policy.py:41-50`) solo devuelve `DimensionLookup` (scd_type==2) o `CombinationLookup` (cualquier otro caso). Ambos son R+W siempre (H19). `enforce_dimension_step_policy` tampoco distingue, entre los steps que matchean una tabla de `dim_contracts`, cuál es el loader y cuál es un lookup del lado del hecho — corrige el tipo de cualquiera de los dos igual. Consecuencia: un lookup de FK del lado del hecho, aunque tenga el tipo "correcto" según SCD, sigue siendo estructuralmente R+W.

**Evidencia:** `dimension_step_policy.py:41-50` (vocabulario de `derive_dimension_step_type`), `dimension_step_policy.py:104-165` (`enforce_dimension_step_policy` no distingue rol de step, solo tabla+tipo), H19 (R+W siempre de `DimensionLookup`/`CombinationLookup`), confirmado por orden de pipeline: `enforce_dimension_step_policy` corre antes de H20 (`etl_generator.py:800-818`) — el orden está bien, la cobertura no.

**Sesión de origen:** Track F2 (2026-07-22), disparado por `extracto_corte_F2.md` (`bitacora_etl_ventas.md`), pregunta "¿C1-bis es un fantasma?".

**Estado:** abierto — **ver D16 en `02-decisiones.md`**, decisión de scope: F3 tiene un prerrequisito externo a Track F (ampliar `dim_contracts` para derivar `Insert/Update`/`Table Output` para el loader y forzar `StreamLookup` para el lookup del lado del hecho), o arranca con el riesgo documentado (D15). No lo resuelve esta sesión.

---

## H23 — Entorno: `DBLookup` falla la introspección de metadata contra el pooler de Supabase

**Qué:** en el entorno real usado para las pruebas (Postgres vía pooler de Supabase, `aws-0-us-east-1.pooler.supabase.com`), `DBLookup` falla con `KettleStepException: Field [id_producto] couldn't be found in the table!` en `DatabaseLookup.determineFieldsTypesQueryingDb` — la columna existe (confirmado por el `NOT NULL` de una lectura anterior de la misma bitácora), es la introspección de metadata del step la que no resuelve contra el pooler, no un problema de esquema real. `Insert/Update` (que también introspecciona) funcionó sin problema en el mismo entorno — no es "todo step con introspección falla", es específico de `DBLookup`.

**Evidencia:** `bitacora_etl_ventas.md`, Lectura 4 (`L4-E01`, log real) y Lectura 6 (`R9`, refinado y confirmado por una segunda solución independiente que nunca usó `DBLookup`). Sustituto que funcionó en el mismo entorno: `StreamLookup` (lee la dimensión con un `TableInput` propio, matchea en memoria, sin tocar introspección de metadata del step de lookup).

**Consecuencia doble:**
1. **Prompt (`system_etl.txt`):** el catálogo debería advertir contra `DBLookup` para este tipo de entorno (Postgres vía pooler) y preferir `StreamLookup`, en vez de dejar que el modelo lo elija libremente y falle en runtime — información que hoy solo vive en una bitácora de sesión, no en la fuente que el LLM realmente lee.
2. **Corte (H19/H22):** un lookup del lado del hecho implementado como `StreamLookup` no toca ninguna tabla en la matriz R/W (H19 ya lo excluye) — adoptar `StreamLookup` para ese rol no es solo un fix de entorno, es también el camino que estructuralmente nunca dispara C1/C1-bis, sin necesidad de que el motor de corte haga nada especial.

**Sesión de origen:** Track F2 (2026-07-22), `bitacora_etl_ventas.md` (R9, L4-E01, L6).

**Estado:** nuevo, sin dueño de track todavía — no es un bug de código del backend (el backend no eligió `DBLookup`, el LLM lo hizo dentro de lo que el catálogo permite). Candidato a regla nueva en `system_etl.txt`, fuera del alcance de los 6 puntos originales de F4 — ver tabla de ruteo abajo y nota sobre F4 en `03-plan.md`.

---

## H24 — `ConnectionsMapRequest.conn_dwh/conn_staging` más estricto que `resolve_real_connections()`, que documenta soportar ambas formas

**Qué:** `ConnectionsMapRequest` (`etl_schemas.py:264-276`) tipa `conn_staging`/`conn_dwh` como `Optional[InlineConnection]` — solo acepta el dict de metadata inline. Pero `resolve_real_connections()` (`ktr_builder/connection.py:93-125`) tiene una rama explícita para `isinstance(value, dict)` (inline) Y una rama para string (`connection_id`, resuelto contra la tabla `Connection`) — su propio docstring dice: *"conn_staging/conn_dwh pueden llegar como dict... en vez de connection_id"*, frase que en sí misma documenta connection_id como forma válida también. El endpoint (`routers/ai.py:244`, `POST /api/v1/etl/{job_id}/connections`) valida el body contra `ConnectionsMapRequest` ANTES de que `resolve_real_connections()` vea nada — la rama string de la capa de servicio queda inalcanzable desde HTTP para `conn_dwh`/`conn_staging` (sigue viva para `conn_origen`, que es `Optional[str]`).

**Evidencia:** `etl_schemas.py:274-276` (schema), `ktr_builder/connection.py:115-121` (docstring + rama string), `routers/ai.py:244-264` (endpoint, valida `ConnectionsMapRequest` primero). 6 tests rojos en `test_ktr_build_job_api.py` — todos mandan `{"conn_dwh": <connection_id string>}` (patrón reusado de un `Connection` ya creado vía `POST /api/connections`, igual que hace `conn_origen`) y reciben 422 antes de llegar a `resolve_real_connections()`.

**Sesión de origen:** esta sesión (2026-07-24), triage de H17. Confirmado contra `git show HEAD` — ya así en el commit `5c4b15e`, no en trabajo sin commitear de ninguna sesión.

**Estado:** abierto, sin dueño de track — no es F3 (fragmentación), toca el flujo de conexiones destino del flujo async de 2-KTR. Dos salidas posibles, no elegidas: (a) `ConnectionsMapRequest.conn_dwh/conn_staging` pasa a aceptar `Union[str, InlineConnection]` (restaura el caso "reusar una Connection guardada" para destino, que `resolve_real_connections` ya sabe resolver); (b) si esa forma se dejó de soportar a propósito (el diseño de "metadata inline, nunca se persiste" sugiere que sí), la rama string de `resolve_real_connections` para `conn_dwh`/`conn_staging` es la que sobra, y los 6 tests están probando un caso que el producto ya no ofrece — habría que borrarlos o reescribirlos contra `InlineConnection`. Decisión de producto, no de código.

---

## H25 — `_CRITICAL_FIELDS["GetSystemInfo"]` vuelve inalcanzable el fallback de field por defecto que `_step_GetSystemInfo` ya implementa

**Qué:** `_CRITICAL_FIELDS["GetSystemInfo"] = ["fields"]` (`registry.py:240`) hace que `build_ktr()` aborte con `KtrBuilderError` (`build.py:196-219`, corre ANTES del loop que invoca los builders de step) apenas un step `GetSystemInfo` llega sin `fields`. Pero `_step_GetSystemInfo` (`ktr_builder/steps/control.py:33-45`) tiene lógica dedicada para ese caso exacto: *"GetSystemInfo: config sin 'fields', se agrega field por defecto 'fecha_carga'"* — nunca se ejecuta, porque el build ya abortó antes de llegar ahí. El propio módulo `ktr_xml_validator.py` documenta el fallback como comportamiento esperado del sistema (docstring: *"GetSystemInfo sin `<fields>` -> KtrXmlValidationError (y confirma que build_ktr() ahora agrega un field por defecto, evitando el error)"*) — la intención de diseño y el chequeo crítico se contradicen entre sí, ambos ya committeados.

**Evidencia:** `registry.py:240` (`_CRITICAL_FIELDS`), `build.py:196-219` (orden: chequeo crítico antes que builders), `ktr_builder/steps/control.py:40-45` (fallback muerto), `ktr_xml_validator.py:1-8` (docstring que asume el fallback vivo). Test rojo: `test_ktr_xml_validator.py::test_build_ktr_get_system_info_without_fields_gets_default_field`.

**Sesión de origen:** esta sesión (2026-07-24), triage de H17. Confirmado contra `git show HEAD` — ya así en `5c4b15e`.

**Estado:** abierto, sin dueño de track — no es F3. Arreglo aparente simple (sacar `"fields"` de `_CRITICAL_FIELDS["GetSystemInfo"]`, dejar que `_step_GetSystemInfo` inyecte el default) pero es cambio de comportamiento de validación ya en producción — no se tocó sin decisión explícita.

---

## H26 — `ETL_OUTPUT_SCHEMA` no declara `documentacion` como property top-level; `ETLGenerateResponse`/`etl_generator.py` sí la esperan

**Qué:** `ETL_OUTPUT_SCHEMA` (`llm_output_schemas/etl_output.py:16-25`) tiene `additionalProperties: False` en el nivel raíz y su `properties` NO incluye `documentacion` — un LLM bajo structured output real (Gemini/Anthropic con schema estricto) no puede devolver esa clave sin violar el schema. Pero `ETLGenerateResponse.documentacion` (`etl_schemas.py:122`) existe como campo de respuesta, y `etl_generator.py` (`_build_response_from_data`/`_build_response_from_two_ktr_data`) hace `data.get("documentacion", "")` — código que asume la clave puede venir poblada, pero bajo el schema actual nunca puede.

**Evidencia:** `llm_output_schemas/etl_output.py:16-25` (schema sin `documentacion`), `etl_schemas.py:122` (campo de respuesta), `etl_generator.py` (lectura con default vacío). Test rojo: `test_structured_outputs.py::TestEtlGeneratorUnit::test_etl_schema_validates_minimal` (fixture incluye `documentacion`, `jsonschema.validate` la rechaza).

**Sesión de origen:** esta sesión (2026-07-24), triage de H17. Confirmado contra `git show HEAD` — ya así en `5c4b15e`.

**Estado:** abierto, ambiguo — a diferencia de H24/H25, acá no está claro cuál lado es el correcto sin una decisión de producto: (a) `documentacion` se sacó del contrato LLM a propósito en algún momento (¿reemplazada por otro mecanismo de generar documentación?) y el campo de respuesta + el `.get()` con default son restos sin limpiar — en ese caso el test está probando un contrato viejo; (b) es un olvido real al escribir el schema y `documentacion` debería declararse como property opcional — en ese caso `ETLGenerateResponse.documentacion` viene vacía siempre en producción hoy, silenciosamente. No se decide acá.

---

## Intake — `bitacora_etl_ventas.md` (R1-R12): clasificación y ruteo

Demuestra la taxonomía S/G/D/Env que pide el punto 3 del pedido del usuario (2026-07-22) — evita que cada regla nueva de un test se acumule como un H-number suelto. Ver la sección "Intake de hallazgos de tests" en `03-plan.md` para el mecanismo completo; acá solo la aplicación concreta a R1-R12.

| Regla | Tag | Resumen | Rutea a | Nota |
|---|---|---|---|---|
| R1 | G-step | Step de loader por forma de tabla (simple→Insert/Update, SCD2→DimensionLookup) | Eje `dim_contracts` (D11), no Track F | Gap confirmado — **H22**, decisión **D16** |
| R2 | G-step | Lookup del lado del hecho siempre de solo lectura | Eje `dim_contracts` (D11), no Track F | Mismo gap — **H22**/**D16** |
| R3 | S | Corte por tabla + KJB secuencial, dims antes que hechos | F2/F3 | Confirma el diseño de F2 (2 derivaciones independientes en verde) |
| R4 | D-dialecto | Default de `COALESCE` debe tipar igual que la columna del DDL | F4 (contenido) + D12/C.1 (dialecto) | **Ya cubierto — cerrado 2026-07-24 sin cambio (D22).** `system_etl.txt` K17/checklist-20 ya lo exigía |
| R5 | D-integridad | (a) Toda dim referenciada tiene loader antes del hecho | Ya cubierto — **V2** (F2/F3, no nuevo trabajo) | Confirmado por `dim_tiempo` en H21 |
| R5 | D-integridad | (b) Prever miembro desconocido o ruteo de huérfanos | F4, diseño resuelto (D21), código pendiente | Ver **C.6**/**D21** en `02-decisiones.md` — bloqueado por diseño de implementación, no por decisión de negocio (ya no) |
| R6 | D-dialecto | Alinear tipos de clave en lookups contra el DDL | F4 (contenido) + D12/C.1 | **Ya cubierto — cerrado 2026-07-24 sin cambio (D22).** `system_etl.txt` regla (e)/checklist-16 ya lo exigía |
| R7 | D-ddl-constraint | Emitir/recomendar constraints (`UNIQUE`) que el upsert asume | Nuevo — sin dueño hasta decisión de producto | Ver **C.5** en `02-decisiones.md` |
| R8 | G-step | Clave natural debe ir también como `value` (`update=N`) en `Insert/Update` de dimensión | F4 (mientras el LLM arma el config) → eje `dim_contracts` si D16 amplía el vocabulario | Extiende **H16**. **Cerrado 2026-07-24 (prompt, D22)** — regla B16 + checklist-21 en `system_etl.txt` |
| R9 | Env | `DBLookup` falla introspección contra pooler de Supabase → preferir `StreamLookup` | Nuevo hallazgo de entorno — candidato a regla en `system_etl.txt` | **H23. Cerrado 2026-07-24 (prompt, D22)** |
| R10 | D-dialecto | `dim_tiempo` como calendario contiguo vía `generate_series` | F4 (contenido) + D12/C.1 | **Ya cubierto — cerrado 2026-07-24 sin cambio (D22).** `system_etl.txt` K18 ya lo instruía completo |
| R11 | D-integridad | Validar claves resueltas, rutear huérfanos antes del insert del hecho | F4, diseño resuelto (D21), código pendiente | Ver **C.6**/**D21** en `02-decisiones.md` |
| R12 | D-dialecto | Dedup de staging vía `DISTINCT ON (...) ORDER BY ... DESC` + flag de auditoría | F4 (contenido) + D12/C.1 | Tercera ocurrencia real — nota en D12 (junto a R10). **Cerrado 2026-07-24 (prompt, D22)** — K19 + checklist-22 en `system_etl.txt` |

**Excepción de corte (self-lookup/insert-new-only, sección 3 del `extracto_corte_F2.md`):** no es una regla R con número propio en la bitácora, pero es una tercera conclusión de corte junto a R3 y la reconciliación de C1-bis — documentada en **H21** (arriba) y en el reporte de F2 (`03-plan.md`).

---

## Resumen de estado

| # | Hallazgo | Estado |
|---|---|---|
| H1 | Partición fija en 2 KTR | **Desinflado** — diseño esperado, coincide con D1, localización emerge sola |
| H2 | `config` como string doble-encodeado | Abierto, alcance no decidido |
| H3 | 5 parseos duplicados de `config` | **Resuelto 2026-07-24** — `validate.py`, `ktr_default_validator.py`, `lineage_builder.py` importan `contracts.parse_cfg`, 0 copias propias restantes |
| H4 | Alias de tabla divergentes (`lineage_builder` vs `contracts`) | **Resuelto 2026-07-22** — centralizado vía `contracts.normalize_config` |
| H5 | Acoplamiento temporal `build_lineage`/`stitch_lineage` | **Resuelto** — D15, riesgo documentado + notificado, no bloqueante |
| H6 | Fallo silencioso en `_parse_config` | **Resuelto 2026-07-24** (F1.5) — `parse_cfg` lanza `ConfigParseError`; `normalize_step_configs()` (pre-pass único, 4 entry points de `etl_generator.py`) lo atrapa una vez, marca el step y emite warning accionable — D15 mejor-esfuerzo, no aborta. `build_ktr` tiene catch propio de respaldo. Tests: `test_config_parse_fail_fast.py` |
| H7 | Sin soporte de `JobEntryJob` (jobs anidados) | **Resuelto 2026-07-24** (F2.5) — `JobEntry.entry_type` (`"trans"`\|`"job"`), `_job_entry()` en `job_analyzer.py` (shape verificado contra `JobEntryJob.getXML()`), `kjb_xml_validator._check_has_trans_entry` amplíado a TRANS-o-JOB. Tests: `test_job_entry_job.py` |
| H8 | Infraestructura de validación existente a reusar | Decidido |
| H9 | E3/E14/key vacía vivos en output fresco | Abierto, no verificable sin ejecutar |
| H10 | E1/V4, E2/V5 no ejercitados | Abierto, pendiente de ejercitar |
| H11 | `DBLookup` fuera del linaje | **Resuelto 2026-07-22** — agregado a `_TABLE_FIELD_TYPES` |
| H12 | Docstring `etl_output.py` desactualizado | Abierto, cosmético |
| H13 | Compatibilidad con ETLs guardados | Cerrado por D3 |
| H14 | Colisión con `dim_contracts` (149b836) | Resuelto — D11: no choca, es precedente |
| H15 | D6 pendiente de re-verificación en frío | **Resuelto** — D6/D6-bis, backend determinístico, solo corrección |
| H16 | `sk_producto` puede no generarse (`DimensionLookup`→`InsertUpdate`) | Abierto, acotado — DB confirma secuencia, riesgo es de contenido del step generado |
| H17 | 12 tests en rojo sin triage | **Cerrado 2026-07-24** — triage completo: 4 obsoletos corregidos (+1 que ya pasaba por razón incorrecta), 8 rotos de verdad quedan abiertos como H24/H25/H26 |
| H18 | Auditoría retroactiva de cambios no declarados | Abierto, alcance sin acotar |
| H19 | Matriz tipo_step → {R,W} sobre tabla (Track F1 Q2) | Entregable — insumo de F2 |
| H20 | Punto de inserción del corte + gap de orden por FK (Track F1 Q4/Q5) | Entregable — insumo de F2 |
| H21 | Análisis de contenido `err1.ktr`/`err2.ktr`: confirma E4/E5 (`dim_producto`) y E6 (`dim_tiempo`); C1-bis reconciliado (no es fantasma); excepción self-lookup a C1 | Entregable — caso de prueba real de F2/F3 |
| H22 | `dim_contracts` no deriva ningún step de solo lectura — prerrequisito externo real de F3 | **Parcialmente resuelto 2026-07-24** (D16 camino 1, código) — `role_of_dimension_step()` (BFS forward, ancla en escritor no-ambiguo) + `enforce_dimension_step_policy` Paso 4 fuerzan `DimensionLookup update=N` para el rol fact-lookup cuando `scd_type==2`. **Residual sin cerrar:** `scd_type` 0/1 (`CombinationLookup` esperado) no tiene mecanismo de solo-lectura seguro sin `date_from`/`date_to` conocidas — se reporta (tipo="error"), no se repara. Tests: `test_dimension_step_policy.py` |
| H23 | Entorno: `DBLookup` falla introspección contra pooler de Supabase, preferir `StreamLookup` | **Cerrado 2026-07-24 (F4/D22)** — nota agregada en `system_etl.txt` junto al bloque `DBLookup` |
| H24 | `ConnectionsMapRequest.conn_dwh/conn_staging` no acepta connection_id string, pese a que `resolve_real_connections()` sí lo soporta | Abierto, sin dueño de track — decisión de producto (extender schema vs. borrar la rama string del service) |
| H25 | `_CRITICAL_FIELDS["GetSystemInfo"]` deja inalcanzable el fallback de field por defecto de `_step_GetSystemInfo` | Abierto, sin dueño de track — fix simple pero cambia validación ya en producción |
| H26 | `ETL_OUTPUT_SCHEMA` no declara `documentacion`, pese a que `ETLGenerateResponse`/`etl_generator.py` la esperan | Abierto, ambiguo — feature perdida vs. resto de código sin limpiar |
