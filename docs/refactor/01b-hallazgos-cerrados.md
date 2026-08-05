# Hallazgos cerrados — archivo frío

**Cuerpo append-only, no se edita.** Entradas movidas acá desde [`01-hallazgos.md`](01-hallazgos.md) por Regla 6 (`CLAUDE.md`) — archivado frío, hecho una sola vez al cerrar un objetivo, nunca continuo. El cuerpo de cada entrada es exactamente el que tenía en el archivo caliente al moverse; no se reescribe.

**Sesión de archivado:** 2026-08-04. Criterio: estado cerrado/resuelto/entregable/decidido, y la(s) fase(s) de la columna `Toca` (índice de `01-hallazgos.md`) ya cerradas — F1, F1.5, F2, F2.5, F3, F5, A0, A0.5. Ninguna entrada tocada por F4 o A1-A7/Track A (en curso) se movió, aunque diga "Cerrado" en su propio índice — ver `docs/README.md`.

En `01-hallazgos.md`, la fila de índice de cada una de estas queda como stub de una línea apuntando acá.

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

**Estado:** abierto en `01-hallazgos.md` al momento de escribirse; cerrado 2026-07-25 (F5) según el índice — ver `01-hallazgos.md` para el estado final si difiere de este cuerpo.

---

## H15 — D6 (quién decide la fragmentación) pendiente de re-verificación en frío

**Qué:** la decisión de que el backend decide la fragmentación de forma determinista (no el LLM) está en `02-decisiones.md` como D6, pero marcada ahí mismo: "apoyada en memoria, no en documento. Pendiente de re-verificación en frío antes de aplicar."

**Sesión de origen:** LLM y flujo (§8, primera pregunta abierta) y `02-decisiones.md` mismo.

**Estado: resuelto (2026-07-22).** Re-verificado en frío. Respuesta: **B — el backend, determinístico.** Ver D6 y D6-bis en `02-decisiones.md` para la evidencia completa (`_build_job_plan`, `build_lineage`, `repair_ktr_steps`/`repair_integrity_gaps`/`enforce_dimension_step_policy` como precedentes de mutación determinística post-LLM) y el alcance (D6-bis: solo corrección estructural, nunca legibilidad — descarta formalmente que crear una tabla nueva, agregar una rama de validación, o reescribir SQL cuenten como "fragmentación").

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

## H22 — `dim_contracts`/`dimension_step_policy` no deriva ningún step de solo lectura (prerrequisito real de F3, no fantasma)

**Qué:** `derive_dimension_step_type` (`dimension_step_policy.py:41-50`) solo devuelve `DimensionLookup` (scd_type==2) o `CombinationLookup` (cualquier otro caso). Ambos son R+W siempre (H19). `enforce_dimension_step_policy` tampoco distingue, entre los steps que matchean una tabla de `dim_contracts`, cuál es el loader y cuál es un lookup del lado del hecho — corrige el tipo de cualquiera de los dos igual. Consecuencia: un lookup de FK del lado del hecho, aunque tenga el tipo "correcto" según SCD, sigue siendo estructuralmente R+W.

**Evidencia:** `dimension_step_policy.py:41-50` (vocabulario de `derive_dimension_step_type`), `dimension_step_policy.py:104-165` (`enforce_dimension_step_policy` no distingue rol de step, solo tabla+tipo), H19 (R+W siempre de `DimensionLookup`/`CombinationLookup`), confirmado por orden de pipeline: `enforce_dimension_step_policy` corre antes de H20 (`etl_generator.py:800-818`) — el orden está bien, la cobertura no.

**Sesión de origen:** Track F2 (2026-07-22), disparado por `extracto_corte_F2.md` (`bitacora_etl_ventas.md`), pregunta "¿C1-bis es un fantasma?".

**Estado:** cerrado — **ver D16 en `02-decisiones.md`**. `role_of_dimension_step()` + Paso 4 de `enforce_dimension_step_policy` (código 2026-07-24) distinguen loader vs. fact_lookup y fuerzan solo-lectura para `scd_type==2`; el caso `scd_type` 0/1 se cerró el mismo día vía guía de generación (`system_etl.txt` — `TableInput`+`StreamLookup`), con el backend como red de seguridad "reporta, no repara" si el LLM no lo sigue.

---

## H43 — Asimetría de namespace en la clave de la matriz R/W

**Qué:** `table_key_recovery._bare()` (`table_key_recovery.py:53`) quita el schema al escribir `cfg["table"]` de vuelta; el camino feliz (step que ya trae `table` sin pasar por recovery) lo deja tal cual venga. Dos namespaces distintos conviven en la misma matriz según si la tabla se resolvió por recovery o no.

**Evidencia:** `table_key_recovery.py:53`, ver sección "Context" de `03c-investigacion-vocabulario-dimension-kettle.md`.

**Sesión de origen:** revisión con evidencia de ejecución real (`hallazgos-y-sugerencias-para-code.md`), verificado contra código 2026-07-30.

**Estado: abierto, ruteado a Fase 3 — cerrará con D45.** La clave `(connection, table)` normalizada (Fase 3, ítem 2) resuelve la asimetría de raíz al pasar los dos caminos por la misma normalización. No se toca fuera de esa fase.

*Nota de archivado:* el índice de `01-hallazgos.md` marca esta entrada "Cerrado — D45 (clave `(connection, table)` normalizada)" y `D45` (`02-decisiones.md`) confirma "Ejecutado completo" — el cuerpo de arriba nunca recibió el párrafo de cierre formal (queda tal como se escribió, append-only), pero el índice y D45 son la evidencia de cierre real. Fase que la toca (F3) cerrada — ver `docs/README.md` Regla A.
