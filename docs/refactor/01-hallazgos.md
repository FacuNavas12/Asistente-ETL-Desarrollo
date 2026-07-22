# Hallazgos — Refactor de fragmentación

**Última actualización:** 2026-07-22

Cada entrada: qué se encontró, evidencia (`archivo:línea`), de qué sesión salió, y estado. Estado se evalúa contra [`02-decisiones.md`](02-decisiones.md) — si una decisión ya cerró el hallazgo, dice cuál.

Todas las líneas de código citadas fueron re-verificadas contra el repo en esta sesión (HEAD `149b836`, rama `run-pentaho`), salvo donde se marca explícitamente "no verificable sin ejecutar".

---

## H1 — Partición fija en 2 KTR

**Qué:** el sistema hoy no tiene noción de "cuántos archivos hacen falta"; siempre son 2 KTR + 1 KJB plano.

**Evidencia:** no localizada con precisión en esta sesión — el material de origen (handoff de fragmentación) señala la existencia del forzado pero no da `archivo:línea` de dónde se fija el número 2. Localizarlo es trabajo de la Fase 1 de investigación ya escrita en el prompt de fragmentación.

**Sesión de origen:** Fragmentación.

**Estado: desinflado (2026-07-22).** No es un hallazgo — es el diseño esperado hoy (Origen→STG / STG→DWH / kjb), y coincide con D1 al 100%: nadie está sorprendido de que sea 2. El `archivo:línea` exacto no hace falta localizarlo por adelantado — va a emerger solo cuando se toquen los archivos generadores durante Track F1/F2, porque la arquitectura del corte deja evidente dónde estaba el número fijo. Única razón para mirarlo temprano, y es barata: confirmar con un grep si el "2" aparece en más de un lugar (afecta el tamaño de Track F1). No es una fase en sí misma.

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
- Copia: `backend/app/services/ktr_builder/validate.py:12` — `def _parse_cfg(raw) -> dict`
- Copia: `backend/app/services/ktr_builder/dimension_step_policy.py:53` — `def _parse_cfg(raw) -> dict`
- Copia: `backend/app/services/ktr_default_validator.py:63` — `def _parse_cfg(raw) -> dict`
- Copia (nombre distinto, mismo patrón): `backend/app/services/lineage_builder.py:41` — `def _parse_config(raw) -> dict`

Ya importan la canónica (no duplican): `backend/app/services/ktr_builder/fields_validate.py:22`, `backend/app/services/ktr_builder/repair.py:22`, `backend/app/services/ktr_builder/build.py:26`.

**Sesión de origen:** LLM y flujo.

**Estado:** abierto. Primer paso del orden de migración propuesto en esa sesión ("dedup de los 4 `_parse_cfg` copiados → import de `contracts.parse_cfg`") — marcado ahí como "cero riesgo", independiente de cualquier decisión pendiente.

---

## H4 — Conocimiento de dominio duplicado y ya divergente (alias de tabla)

**Qué:** `lineage_builder.py` tiene su propia tabla de tipos de step→campo de tabla, y no conoce los alias (`target_table`, `table_name`) que `contracts.STEP_CONTRACTS` sí resuelve.

**Evidencia (verificada, exacta):**
- `backend/app/services/lineage_builder.py:20-27` — `_TABLE_FIELD_TYPES` es un `set` plano de nombres de step, sin alias.
- `backend/app/services/lineage_builder.py:51-53` — `_extract_table` lee `config.get("table")` directo, sin pasar por alias.
- `backend/app/services/ktr_builder/contracts.py:320,328,334,346,350,354,358` — `key_aliases={"target_table": "table", "table_name": "table", ...}` sí normaliza esos alias.

**Sesión de origen:** LLM y flujo, con eco en el prompt (no ejecutado) de Fase 4 de Arquitectura.

**Estado:** abierto. Reclasificado por la propia sesión de origen: de "fragilidad, no bug activo" (porque hoy corre siempre después de la normalización, por orden de llamada) a **"bug de corrección esperando su turno"**, porque bajo fragmentación el linaje deja de ser cosmético (ver H5, H10 y `00-objetivo.md`).

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

**Estado:** abierto.

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

**Estado:** abierto, y en conflicto directo con **D5** ("ante la duda entre tolerar y fallar, se falla"). No requiere ninguna decisión adicional para actuar — D5 ya la resuelve en la dirección de "hacerlo ruidoso".

---

## H7 — El builder de KJB no soporta jobs anidados (bloquea la jerarquía de D1)

**Qué:** el diseño objetivo requiere `job_master.kjb` ejecutando `job_origen_stg.kjb` y `job_stg_dwh.kjb` (jobs que ejecutan jobs). Verificado: el backend no tiene ninguna noción de `JobEntryJob` hoy.

**Evidencia (verificada por esta sesión, no en el material original):** búsqueda de `JobEntryJob` en todo `backend/` → cero resultados. Los únicos archivos que tocan la generación de KJB son `backend/app/services/etl_generator.py`, `backend/app/services/job_analyzer.py` y `backend/app/services/kjb_xml_validator.py`, los tres solo con `JobEntryTrans`.

**Sesión de origen:** ninguna — surge de verificar contra el repo la pregunta 3 de la Fase 1 del prompt de fragmentación ("¿`build_kjb_xml` soporta `JobEntryJob` o solo `JobEntryTrans`? ¿Qué haría falta para anidar jobs?"). Esa pregunta estaba planteada como "a investigar"; esta sesión confirma el hecho base (ausencia total) sin resolver el "qué haría falta" — eso sigue siendo trabajo de esa Fase 1.

**Estado:** abierto. Prerrequisito no resuelto de D1 — sin `JobEntryJob`, la jerarquía de 3 niveles del objetivo no se puede materializar tal como está descrita.

---

## H8 — Infraestructura de validación ya existe: no debe duplicarse

**Qué:** ya hay un gate estructural genérico wireado al build, y un catálogo de validadores table-driven (V4-V13). El motor de corte de fragmentación (V1/V2/V3, nuevos) debe extenderlos, no vivir en paralelo.

**Evidencia (verificada, exacta):**
- `backend/app/services/ktr_xml_validator.py` existe.
- `backend/app/services/ktr_builder/build.py:46` — `from app.services.ktr_xml_validator import validate_ktr_xml`; `build.py:401` — `validate_ktr_xml(ktr_xml, strict_connections=strict_connections)` (wireado, corre siempre).
- `backend/app/services/ktr_builder/error_catalog_checks.py` — validadores confirmados: `v4_select_values_sin_entradas:79`, `v5_dimension_lookup_columnas_tecnicas:106`, `v6_insert_update_mapeos:171`, `v7_fact_table_output_sin_clave:231`, `v8_truncate_sin_transaccional:253`, `v11_monetario_sin_bignumber:321`, `v13_lookup_key_incompleta:374`.

**Sesión de origen:** Fragmentación (handoff, sección "ACTUALIZACIÓN").

**Estado:** decidido — restricción de diseño ya fijada para cuando se implemente el motor de corte (Fase 3 del prompt de fragmentación, no iniciada).

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

**Estado:** abierto. Reclasificado por la sesión de origen de "parche barato" a **prerrequisito**: bajo fragmentación, un step invisible para el linaje es una dependencia que no se ve y un orden de KJB que puede salir mal.

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

---

## H17 — 12 tests en rojo: no son gate hasta triage

**Qué:** el handoff de Fragmentación menciona 12 tests preexistentes en rojo (SystemInfo, job API, schema JSON), "no introducidos por este trabajo". No se puede usar la suite como gate de regresión sin saber si ese rojo informa algo real.

**Sesión de origen:** Fragmentación (handoff), reclasificado en la respuesta del usuario a esta sesión.

**Estado:** abierto, no bloqueante. Es plausible que sean tests viejos que esperan archivos/formatos ya desactualizados, en cuyo caso su rojo no informa nada. Acción concreta, no juicio a priori: leerlos y clasificarlos en *obsoletos* vs. *rotos de verdad* — solo los segundos sirven como foto de partida para D13 (definición de terminado por fase).

---

## H18 — Auditoría retroactiva de cambios no declarados: alcance sin acotar

**Qué:** el material de fragmentación es un autorreporte de sesión, no evidencia independiente contra el diff real. Ya se confirmó al menos un caso de afirmación no verificada que resultó incorrecta (H4 — ubicación de `_TABLE_FIELD_KEYS`). Falta un chequeo mecánico: por cada commit que tocó generación de KTR, comparar mensaje de commit + lo declarado en la doc contra el diff canónico normalizado (mismo criterio de H-delta que usa D9).

**Sesión de origen:** respuesta del usuario a esta sesión de consolidación (2026-07-22), sección C.4.

**Estado:** abierto. Falta decidir hasta qué commit hacia atrás tiene sentido ir — sin eso, la tarea no está acotada y no se puede estimar.

---

## Resumen de estado

| # | Hallazgo | Estado |
|---|---|---|
| H1 | Partición fija en 2 KTR | **Desinflado** — diseño esperado, coincide con D1, localización emerge sola |
| H2 | `config` como string doble-encodeado | Abierto, alcance no decidido |
| H3 | 5 parseos duplicados de `config` | Abierto, plan de dedup listo |
| H4 | Alias de tabla divergentes (`lineage_builder` vs `contracts`) | Abierto |
| H5 | Acoplamiento temporal `build_lineage`/`stitch_lineage` | Abierto |
| H6 | Fallo silencioso en `_parse_config` | Abierto, choca con D5 |
| H7 | Sin soporte de `JobEntryJob` (jobs anidados) | Abierto, prerrequisito de D1 |
| H8 | Infraestructura de validación existente a reusar | Decidido |
| H9 | E3/E14/key vacía vivos en output fresco | Abierto, no verificable sin ejecutar |
| H10 | E1/V4, E2/V5 no ejercitados | Abierto, pendiente de ejercitar |
| H11 | `DBLookup` fuera del linaje | Abierto, subió a prerrequisito |
| H12 | Docstring `etl_output.py` desactualizado | Abierto, cosmético |
| H13 | Compatibilidad con ETLs guardados | Cerrado por D3 |
| H14 | Colisión con `dim_contracts` (149b836) | Resuelto — D11: no choca, es precedente |
| H15 | D6 pendiente de re-verificación en frío | **Resuelto** — D6/D6-bis, backend determinístico, solo corrección |
| H16 | `sk_producto` puede no generarse (`DimensionLookup`→`InsertUpdate`) | Abierto, acotado — DB confirma secuencia, riesgo es de contenido del step generado |
| H17 | 12 tests en rojo sin triage | Abierto, no bloqueante, acción: leer y clasificar |
| H18 | Auditoría retroactiva de cambios no declarados | Abierto, alcance sin acotar |
