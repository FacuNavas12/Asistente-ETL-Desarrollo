# Decisiones — Refactor de fragmentación

**Cuerpo append-only, índice mutable.** Una D se escribe una vez; si una decisión cambia, se escribe una D nueva que supersede a la anterior, y el índice marca la vieja `superseded por D<n>` — el cuerpo original no se toca.

**Última actualización:** 2026-08-04 (D68, O3 caso testigo — step de dimensión se sintetiza siempre, no se pide y corrige)

Este archivo es la fuente de verdad del refactor. Manda sobre cualquier análisis, plan o conclusión de sesión que lo contradiga. Cuando un análisis choca con una decisión de acá, gana la decisión y el análisis queda marcado como obsoleto.

Toda sesión que tome una decisión cierra actualizando este archivo.

---

## Índice — el estado de una decisión vive únicamente acá

El cuerpo de cada D es evidencia append-only (regla 2, `CLAUDE.md`) — no se edita para reflejar estado nuevo. Si una decisión cambia, la nueva D la supersede y esta fila se marca `superseded por D<n>`.

| # | Qué es | Estado |
|---|---|---|
| D1 | Fase lógica ≠ archivo físico | Vigente |
| D2 | No se preserva comportamiento actual | Vigente |
| D3 | Datos guardados descartables | Vigente — verificado 2026-07-22 |
| D4 | Compat. hacia atrás no es requisito | Vigente |
| D5 | Ante la duda, falla | Vigente — acotada por D15 (detección sí, emisión no) |
| D6 | Backend decide fragmentación, determinístico | Confirmado, evidencia en repo |
| D6-bis | Fragmentación = corrección, no legibilidad | Vigente |
| D7 | Reglas derivadas de casos reales | Vigente |
| D8 | Conocimiento de dominio: una sola casa | Vigente |
| D9 | Criterio de verificación: delta declarado | Vigente |
| D10 | Sin convivencia parseo viejo/nuevo | Vigente |
| D11 | `dim_contracts` no choca con fragmentación | Vigente |
| D12 | Dialecto SQL: Postgres default + notificación | Vigente |
| D13 | Definición de terminado (toda fase) | Vigente — reforzada por D26 |
| D14 | F1.5/F2.5 no dependen circularmente de sí mismas | Vigente, F1.5/F2.5 cerradas |
| D15 | Fail-fast en detección, no fail-hard en emisión | Vigente |
| D16 | Dependencia externa real: eje `dim_contracts` | Resuelto — camino 1 en código (scd_type==2); residual 0/1 **superseded por D44** (criterio de rol y exclusión de `DBLookup` se conservan) |
| D17 | F2 aprobado por el usuario | Cerrado |
| D18 | H2 (config string→object) pospuesto | No decidido — requiere spike |
| D19 | Wiring de servicio cerrado, HTTP en notificación | Superseded en parte por D20 (backend ya implementado) |
| D20 | Forma de la respuesta con N archivos | Diseño cerrado, backend implementado — falta frontend (D20-punto5) |
| D21 | Miembro inferido (cierra C.6) | Resuelto — detección en código; residual en `04-verificacion.md` |
| D22 | Triage F4, 3 gaps cerrados por prompt | Resuelto |
| D23 | Alcance validador de contrato entre KTR | Alcance cerrado — implementado por D38 |
| D24 | Track A retomada, A0 ejecutada | Cerrado |
| D25 | A0.5 ejecutada, deriva H29 | Cerrado |
| D26 | Suite roja marcada + test arquitectura + separación tests | Parte 2 (test de arquitectura) implementada 2026-07-27 como `backend/tests/test_architecture_layers.py` — no `test_architecture_boundaries.py` como decía el texto original, mismo objetivo. Partes 1 (xfail known failures) y 3 (separación unit/integration/manual) siguen sin implementar |
| D27 | Split `registry.py` → `step_types.py`/`step_emitters.py`, borrado de `KNOWN_PDI_STEP_TYPES`, `CanonicalType`/`FieldFormat`/`ColumnRole` → `domain/`, criterio "vocabulario PDI es dominio" | Ejecutado, suite verde |
| D28 | D20-punto5 cerrado: frontend consume `etapas`/`kjb_master`; linaje recalculado se borra del front; datos viejos se rechazan explícitos; `EtapaOutput` gana `nombre`; Superset fuera de alcance | Ejecutado, F3 cerrada |
| D29 | Progreso observable del job async: bitácora persistida + polling existente, no SSE | Diseño cerrado |
| D30 | Checkpoint por etapa de la salida del modelo; tensión con D3 resuelta a favor del checkpoint | Diseño cerrado |
| D31 | Reanudación de la etapa 2 sin endpoint ni estado servidor nuevos (`reuse_stage_1`) | Diseño cerrado |
| D32 | Contrato del status extendido: `raw_llm_data` inmutable, lo parcial va en `stages` | Diseño cerrado |
| D33 | Superficie de acceso a las respuestas del modelo: botón de header + drawer, dos acciones distintas | Diseño cerrado |
| D34 | D15 ejecutado para conexiones: sin resolver ya no aborta el build; `conn_origen` acepta metadata inline | Ejecutado |
| D35 | El mapa de conexiones es por-ETL y se aplica en todo camino de build (incluido `build-from-raw`); `conn_origen` derivado se valida antes de usarse | Ejecutado |
| D36 | H27/H28 cerrados con evidencia real (Kettle fuente + auditoría de `STEP_BUILDERS`); B17 reescrita, `FIELD_TYPE_SOURCES` +6 entradas | Ejecutado |
| D37 | Criterio determinista de SCD1 vs SCD2 — pre-check en `domain/scd.py` + criterio escrito en `system_inference.txt` | Ejecutado |
| D38 | Validador de contrato entre KTR (D23) implementado — nombres, tipos como gap documentado | Ejecutado |
| D39 | `validate_business_rules()` (D23) removido — responsabilidad se traslada a DDL + futura herramienta Data Validator (PDI), fuera de esta sesión | Ejecutado |
| D40 | H29 — recuperación determinista de `table` por contenido (no posición); `TABLE_BEARING_STEPS` explícito en vez de `required_keys`; nace `ktr_builder/validators/` | Ejecutado |
| D41 | H40 — nuevo pass `flag_dead_computed_fields` (warning, no repara) para `Calculator` sin consumidor downstream; corrige de paso un bug de wiring en D40 (prefijo `TABLE_KEY_PREFIX` se aplicaba a TODOS los findings de `run_passes()`, no solo a los de `recover_table_key`) | Ejecutado |
| D42 | H39 — prompt `origen_stg` deja de recibir `## REGLAS DE NEGOCIO`; staging queda como copia fiel del origen (truncate+load) sin steps de validación de negocio, por diseño de prompt, no por validador post-hoc | Ejecutado |
| D44 | Vocabulario de dimensión uniforme por rol (`DimensionLookup` para loader y lookup, todo `scd_type`; modo por atributo, no por dimensión) — investigación Kettle R-K1-R-K6/R-K3b cierra el bloqueo. **Supersede parcialmente D16** (retira el residual scd_type 0/1) | Diseño cerrado — bloqueante de ejecución (C.12/H47) resuelto por D47, ya no bloqueada |
| D45 | Corte visible: resolución de tabla por SQL como port inyectado (`domain`/`infrastructure`), clave de matriz `(connection, table)` normalizada, C1 con RW desdoblado, exención por camino dirigido eliminada | Ejecutado completo (Sesión A 3/4/5/7 + Sesión B 1/2/6, 2026-07-30) |
| D46 | Severidad promovida (`Finding.severity` deja de aplanarse) + `error_catalog_checks.py` cableada a `build_ktr` con golden negativo como gate + `v8_truncate_sin_transaccional` corregida (estaba invertida, no aproximada — R-K5) antes de cablearse con severidad `error`. D15 se ejecuta, no se supersede | Ejecutado (2026-07-30) |
| D47 | C.12 resuelta: sembrado de la fila `tk=0`/`version=1` embebido en el DDL de toda dimensión — mecanismo prescrito por doc oficial Pentaho, no relajar `date_from` a NULLable | Ejecutado (2026-07-30) — índice no reflejaba el estado real hasta hoy, ver nota de ejecución en el cuerpo |
| D48 | C.10 resuelta: materialización de hops que cruzan grupos vía tabla de staging, no `Copy rows to result` — límite estructural de rowset único por `.kjb` | Ejecutado (2026-07-30) para el patrón evidenciado (único writer, todos los readers ancestros directos — self-lookup). Caso general de corte multi-par no construido, sin evidencia (D6-bis) |
| D49 | C.11a resuelta: `PREFERRED_SCHEMA_NAME` obligatorio en toda `<connection>` emitida — cierra el riesgo real de `search_path` no determinista sin tocar `dim_contracts`/DDL/steps. C.11b (multi-schema completo) queda abierta, alcance separado | Ejecutado (2026-07-30) |
| D52 | Fase 2-bis, mitigaciones 1+2 (finding de consecuencia por dimensión + regla dura columna monetaria en `attributes_scd2`) — mitigaciones 3/4 quedan backlog explícito | Ejecutado (2026-07-30) |
| D53 | Fase 2-ter ejecutada: `FilterRows` de saneamiento exigido por CHECK del DDL (S-4/H45) + guard determinista de capa staging (S-5/H-5) | Ejecutado (2026-07-30) |
| D54 | Fase 4 (corrida real): 1 corrida completa (sonnet), 0 corridas Haiku (fallo de inferencia previo al ETL) — criterio de cierre (S-12, 2+ modelos × N corridas) no se cumple todavía, sigue en curso | Parcial (2026-07-31) |
| D55 | Plan de reparación del generador ETL (8 ítems): vocabulario `<field><update>` por modo sin condición de vacío (cierra H51), `ConcatFields` al formato real, suite que genera en vez de consumir el golden, semilla `tk=0` sintetizada en el DDL (alineada con D47, no lo reabre), contra-chequeo narración↔XML, `check_constraint_filter_rows`/`guard_staging_layer` completados, escala `BigNumber` desde el DDL | Planificado (2026-08-01), no ejecutado — ítem 1, rótulo interno "D-1" (`KtrBuilderError` obligatorio en `lookups.py`/`build.py`), **superseded en parte por D60** |
| D56 | Ítem 5 de D55 (contra-chequeo narración↔XML): implementado con limitación conocida (falso negativo si el regex no matchea) | Ejecutado, limitación registrada |
| D57 | Reclasificación a fact_lookup en `enforce_dimension_step_policy`: se limpia `fields`, no se conserva vocabulario Y-mode cruzado | Ejecutado |
| D58 | `role_of_dimension_step`: BFS solo desambigua con 2+ candidatos; `already_readonly` valida vocabulario antes de dejar pasar | Ejecutado — discriminador por contenido de `fields` y rama `already_readonly` **superseded por D68** (O3: la síntesis reconstruye el config siempre, ya no hay "ya venía bien" ni evidencia en `fields` del modelo); BFS de rol y regla de conteo con 1 candidato, vigentes |
| D59 | O1, lote E-04…E-08: StringOperations/Unique/ExcelInput/JsonInput/TextFileOutput corregidos contra `readData()` real de Kettle, evidencia citada por clase+línea | Ejecutado (2026-08-03) |
| D60 | O1-b: `VALUE_META_TYPE_NAMES` verificada y corregida (E-02); criterio de degradación legítima escrito; política de los 4 sitios de aborto por contenido — supersede la parte de D55 (rótulo interno "D-1") que exige `KtrBuilderError` en esos 4 sitios | Decidido (2026-08-03); criterio y `VALUE_META_TYPE_NAMES` ejecutados, conversión de los 4 sitios pendiente (Alcance punto 2 de `10-estabilizar-emision.md`) |
| D61 | O2-a: `common.py` partido — `_yn`/`KtrBuilderError` quedan (dominio puro), `_sub` se muda a `xml_helpers.py` nuevo (infra) | Ejecutado (2026-08-03) |
| D62 | O2-b (T1): `resolve_step_table()` nueva en `domain/step_table.py` — unifica el `if not table: continue` mudo de `fragmentation.py`/`dimension_step_policy.py`/`fields_validate.py`, devuelve mensaje en vez de tragarlo | Ejecutado (2026-08-03) |
| D63 | O1-b: dedupe de vocabulario cruzado en `DimensionLookup` — canal único `check_dimension_lookup_fields`, registro retroactivo de D60 | Ejecutado (2026-08-03) |
| D64 | O1: Alcance punto 3 de `10-estabilizar-emision.md` (findings de `enforce_dimension_step_policy` llegan al usuario) — verificado en corrida real contra el corpus de E-01, canal ya existía, sin cambio de código. Encontrado E-20 (duplicación de `PRE_EMIT_PASSES`) | Verificado (2026-08-03); E-20 abierto, no bloquea |
| D65 | O1-b cierra vía corrida real async (`/generate-async`→`/status`) + fix de Bloque 3 (`_build_response_from_two_ktr_data` ya no descarta la etapa origen→STG cuando STG→DWH falla estructuralmente). Con esto, O1 completo | Ejecutado (2026-08-03), commit `80a1e3b` |
| D66 | O2-c: `lineage_builder.py` partido — `build_lineage`/`stitch_lineage_many`/`stitch_lineage` a `domain/lineage.py` (`LineageGraphData`, dataclass stdlib); `_parse_ktr_xml` queda de infra en `services/lineage_builder.py`. Registro retroactivo — código y mapa ya decían "Ejecutado" sin D-N propia | Ejecutado (2026-08-03) |
| D67 | O2 verificado completo al pedir "empezar O2": O2-a/b/c ya ejecutadas (D61/D62/D66), `test_architecture_layers.py` verde, `FROZEN_R1` vacío. Nada nuevo que ejecutar — corrección de `docs/README.md` (línea O2-c apuntaba a D63, que ya era de otro tema) | Verificado (2026-08-03), sin cambio de código |
| D68 | O3 caso testigo: el step de dimensión se sintetiza siempre (`apply_dimension_contracts`/`build_dimension_lookup_config`), no se pide y corrige. Estación de reparación borrada (cierra E-21/E-23 por construcción); `PRE_EMIT_PASSES` partida en `TABLE_RECOVERY_PASSES`/`VERIFY_PASSES`; prompt y `_format_dim_contracts` recortados. Supersede parcialmente D58 | Ejecutado (2026-08-04) — falta criterio 5 de `30-decision-python-llm.md` (corrida real end-to-end) |

---

## Índice por fase

Navegación rápida — clic para ir directo a la decisión. Grupos según la taxonomía de fases de [`03-plan.md`](03-plan.md). El tag `[Fase]` al final de cada título de decisión repite este agrupamiento in situ, para orientarse sin volver acá.

**Fundamentos** (doctrina general, aplica a todo el refactor, no a una fase puntual)
[D1](#d1) fase lógica ≠ archivo físico · [D2](#d2) no se preserva comportamiento actual · [D3](#d3) datos guardados descartables · [D4](#d4) compat. hacia atrás no es requisito · [D5](#d5) ante la duda, falla · [D9](#d9) criterio de verificación: delta declarado · [D10](#d10) sin convivencia parseo viejo/nuevo · [D13](#d13) definición de terminado (toda fase) · [D15](#d15) fail-fast en detección, no fail-hard en emisión · [D26](#d26) suite roja marcada (xfail/known failures) + test de arquitectura ejecutable + separación de tests

**Eje `dim_contracts` / G-step** (fuera de Track F, pero lo cruza en F3/F4)
[D11](#d11) `dim_contracts` no choca con fragmentación

**F1.5** — dominio mínimo para el corte
[D8](#d8) conocimiento de dominio: una sola casa · [D14](#d14) F1.5/F2.5 no dependen circularmente de sí mismas · [D18](#d18) H2 (config string→object) pospuesto, no decidido

**F2** — diseño del corte
[D6](#d6) el backend decide la fragmentación, determinístico · [D6-bis](#d6-bis) fragmentación = corrección, no legibilidad · [D7](#d7) reglas derivadas de casos reales · [D17](#d17) F2 aprobado por el usuario

**F3** — implementación del corte
[D16](#d16) dependencia externa real: eje `dim_contracts` · [D19](#d19) wiring de servicio cerrado, HTTP en modo notificación · [D20](#d20) forma de la respuesta con N archivos

**F4** — track de errores / contenido generado
[D12](#d12) dialecto SQL: Postgres por defecto + notificación obligatoria · [D21](#d21) miembro inferido (cierra C.6) · [D22](#d22) triage F4, 3 gaps cerrados por prompt · [D23](#d23) alcance del validador de contrato entre KTR (cierra ítem pendiente de D22) · [D29](#d29) progreso observable del job async · [D30](#d30) checkpoint por etapa del LLM · [D31](#d31) reanudación de la etapa 2 sin estado servidor nuevo · [D32](#d32) contrato del status extendido (`stages`) · [D33](#d33) superficie de acceso a las respuestas del modelo · [D36](#d36) B17 reescrita + `FIELD_TYPE_SOURCES` +6 entradas (cierra H27/H28) · [D38](#d38) validador de contrato entre KTR implementado (cierra D23) · [D39](#d39) `validate_business_rules()` removido, responsabilidad a DDL + Data Validator · [D40](#d40) recuperación determinista de `table` por contenido (cierra parcial H29), nace `ktr_builder/validators/` · [D42](#d42) staging deja de recibir reglas de negocio en el prompt · [D44](#d44) vocabulario de dimensión uniforme por rol (supersede parcial D16) · [D45](#d45) corte visible: resolución SQL por port, clave normalizada, RW desdoblado · [D46](#d46) severidad promovida + `error_catalog_checks` cableada + golden negativo · [D47](#d47) C.12: sembrado fila `tk=0` en el DDL · [D48](#d48) C.10: materialización de hops cruzados vía tabla de staging · [D49](#d49) C.11a: `PREFERRED_SCHEMA_NAME` obligatorio · [D52](#d52) Fase 2-bis mitigaciones 1+2: finding de consecuencia + regla dura monetaria en `attributes_scd2` · [D53](#d53) Fase 2-ter: `FilterRows` de CHECK del DDL + guard capa staging · [D54](#d54) Fase 4 corrida real: resultado parcial, 1 corrida sonnet, H51 nuevo · [D55](#d55) plan de reparación del generador ETL (8 ítems), cierra H51, semilla `tk=0` alineada con D47

**Track A** — auditoría de arquitectura
[D24](#d24) Track A retomada, A0 ejecutada · [D25](#d25) A0.5 ejecutada (censo de fallos silenciosos), H29 · [D26](#d26) adelanta en chico una porción de A2/R1 (test de arquitectura), sin esperar a A7 · [D27](#d27) split `registry.py`, `KNOWN_PDI_STEP_TYPES` borrado, `CanonicalType` a `domain/`, criterio vocabulario-PDI-es-dominio

**Otras secciones del archivo**
[Deliberadamente no decidido](#deliberadamente-no-decidido) · [Verificaciones pendientes](#verificaciones-pendientes) · [Abiertos](#abiertos-no-bloquean-el-arranque-del-refactor-sí-bloquean-ítems-puntuales) — [C.1](#c1) dialecto multi-motor `[F4]` · [C.2](#c2) reglas de corte vs. D6-bis `[F2]` ✓ · [C.3](#c3) verificaciones DB real `[F1/F4]` · [C.4](#c4) auditoría retroactiva `[Fundamento]` · [C.5](#c5) constraints DDL `[F4]` · [C.6](#c6) FK no resuelta `[F4]` ✓ resuelta por D21 · [C.7](#c7) `ConnectionsMapRequest` vs. connection_id string `[sin track]` · [C.8](#c8) `GetSystemInfo` fallback inalcanzable `[sin track]` · [C.9](#c9) `documentacion` ambigua en el schema `[sin track]` · [C.10](#c10) materialización de hops que cruzan grupos `[F3]` ✓ resuelta por D48 · [C.11a](#c11a) `PREFERRED_SCHEMA_NAME` obligatorio `[F4]` ✓ resuelta por D49 · [C.11b](#c11b) multi-schema completo end-to-end `[F3]` · [C.12](#c12) `checkDimZero` vs. `date_from NOT NULL` sin DEFAULT `[F4]` ✓ resuelta por D47

---

## Objetivo

Hoy el sistema fuerza todo ETL a exactamente dos archivos KTR (Origen→Staging, Staging→DWH). **Ese forzado es la falla:** cuando un proceso necesitaba separarse, meterlo igual dentro de dos archivos produjo errores.

El refactor desacopla la fase lógica del archivo físico. El orden macro Origen→Staging / Staging→DWH se mantiene como concepto de fases, pero deja de determinar la cantidad de archivos. El backend decide, en base a reglas concretas, cómo se materializan esas fases: puede ser un KTR, pueden ser varios. Cuando son varios, se genera además un KJB que los ordena.

Fragmentar no es obligatorio ni el caso por defecto: es una decisión razonada sobre el conjunto de steps y sus dependencias. Para un ETL simple, el resultado correcto puede seguir siendo dos archivos.

**Razón:** corrección estructural — races de lectura/escritura, dimensiones consultadas pero no cargadas, doble escritor sobre la misma tabla, arreglos de KTR que fallen silenciosamente. **No** es legibilidad ni buenas prácticas de organización en general — ver D6-bis. Un KTR largo pero correcto no se parte.

Todo lo demás del proyecto es río abajo de este objetivo y se evalúa contra él.

---

## Decisiones vigentes

<a id="d1"></a>
### D1 — Fase lógica ≠ archivo físico `[Fundamento]`

La cantidad de archivos KTR deja de estar fijada. Se deriva de reglas aplicadas sobre el conjunto de steps y su grafo de dependencias.

*Por qué:* hoy los dos conceptos están mapeados 1:1 y hardcodeados, y esa es la causa raíz de los errores que motivan el refactor.

*Consecuencia:* hay que encontrar y remover la partición fija en dos, y revisar qué código asume que siempre son dos.

*Qué la invalidaría:* que se demuestre que ningún caso real requiere más de dos archivos.

<a id="d2"></a>
### D2 — No optimizamos por preservar el comportamiento actual `[Fundamento]`

Las zonas afectadas van a sufrir cambios estructurales que vuelven irrelevante si hoy funcionaban. "Esto hoy anda" no es argumento para protegerlo.

*Por qué:* el plan estaba gastando esfuerzo en conciliar comportamientos que el refactor vuelve obsoletos.

<a id="d3"></a>
### D3 — Los datos guardados son descartables `[Fundamento]`

Regenerar los ETLs desde datos base es preferible, y además sirve para volver a probar el sistema. No pedimos migración de datos ni modo permisivo por compatibilidad histórica.

*Consecuencia:* cae la objeción de "los ETLs viejos dejan de abrir". También cae la conclusión previa de que `parse_cfg` no se puede eliminar nunca — descansaba enteramente en las filas históricas.

*Qué la invalidaría:* que alguien del equipo tenga trabajo apoyado en ETLs guardados. Ver verificaciones pendientes.

<a id="d4"></a>
### D4 — La compatibilidad hacia atrás no es requisito hasta nuevo aviso `[Fundamento]`

Cuando lo sea, se decide explícitamente acá y se revisa todo lo que dependa de esto.

<a id="d5"></a>
### D5 — Ante la duda entre tolerar y fallar, se falla `[Fundamento]`

Preferimos que un cambio rompa fuerte y visible antes que degrade en silencio.

*Por qué:* no es preferencia estilística. Es el mismo principio que motiva la fragmentación —evitar arreglos de KTR que fallen silenciosamente— aplicado al código que los genera.

*Consecuencia:* nada de degradar a valores vacíos dentro de un `except`. Un input inválido produce un error explícito con contexto suficiente para ubicarlo.

<a id="d6"></a>
### D6 — La fragmentación la decide el backend, de forma determinística `[F2]`

El LLM propone el ETL lógico. El backend decide la materialización física en N KTRs más el KJB.

*Por qué:* el refactor existe para reducir errores. Poner la decisión en el LLM le mete no-determinismo justo a la capa que existe para eliminarlo.

**Estado: confirmado, con evidencia en repo (re-verificado en frío, 2026-07-22).** Evidencia:

1. `_build_job_plan()` (`backend/app/services/etl_generator.py:224`) ya construye el `JobPlan` del KJB en Python puro — precedente de orquestación backend-owned.
2. Contracaso instructivo: el flujo `CreateJob` **sí** consulta al LLM, porque ahí los `.ktr` son de autoría externa y el backend no tiene grafo propio. La línea divisoria es *dónde ya vive la información*, no una preferencia general por determinismo.
3. `build_lineage()` (`backend/app/services/lineage_builder.py`) ya computa `in_deg`/`out_deg` y extrae tablas por step — exactamente la señal que necesita un algoritmo de corte.
4. `repair_ktr_steps()` (`backend/app/services/ktr_builder/repair.py:136`), `repair_integrity_gaps()` (`repair.py:230`) y `enforce_dimension_step_policy()` (`backend/app/services/ktr_builder/dimension_step_policy.py:72`) ya son mutaciones determinísticas post-LLM. El pase de fragmentación entra en ese mismo punto del pipeline.

*Qué la invalidaría:* si se diera vuelta, cambia el schema de salida entero, las reglas pasan a ser prompt engineering en vez de código testeable, y hay que revisar D1 y el plan completo. (Ya no es un riesgo abierto — queda documentado por si algo futuro lo pone en duda.)

<a id="d6-bis"></a>
### D6-bis — La fragmentación es un mecanismo de corrección, no de legibilidad `[F2]`

**La fragmentación responde únicamente a corrección estructural: races, fallas silenciosas, conflictos de lectura/escritura sobre la misma tabla. Un KTR largo pero correcto no se parte.**

*Por qué:* el proyecto acelera y busca que funcione. Está orientado a profesionales del área — si el usuario quiere reorganizar el KTR a su gusto, es su terreno y su responsabilidad, no del generador.

*Consecuencia:* **no se introducen umbrales hardcodeados** del tipo "partir si >15 steps". El backend corta por señal estructural o no corta. Esta regla frena el próximo "ya que estamos, partamos esto que es largo".

*Corolario bajo D6+D6-bis juntas:* crear una tabla nueva (ej. `dim_tiempo`), agregar una rama de validación de calidad, o reescribir SQL, nunca pudieron ser "fragmentación" — ningún análisis de grafo produce eso. Si aparecen mezclados con un corte real en algún caso histórico, son cambios que viajaron de polizón, no parte de la regla.

*Pendiente:* el material de fragmentación (`handoff_fragmentacion_y_errores.md`) ya contiene reglas de cuándo fragmentar escritas antes de esta decisión. Hay que releerlas y eliminar las que respondan a legibilidad o tamaño en vez de corrección estructural — ver `03-plan.md`, ítem bloqueante antes de diseñar el corte (Track F2).

<a id="d7"></a>
### D7 — Las reglas de fragmentación se derivan de casos reales de falla `[F2]`

No se diseñan desde una lista abstracta de buenas prácticas de Pentaho. Se derivan de los casos concretos donde forzar dos archivos produjo errores: qué ETL, qué steps, qué falló, cómo se resolvió separando.

*Por qué:* tenemos evidencia empírica. Sin ella, el motor de reglas se diseña contra un problema imaginado y va a partir de más o de menos.

*Consecuencia:* cada caso histórico de falla es también un caso de prueba: debe producir la partición correcta.

<a id="d8"></a>
### D8 — El conocimiento de dominio sobre steps tiene una sola casa `[F1.5]`

Qué tabla toca un step, con qué alias, y si lee o escribe: eso vive en un único lugar. Ningún código nuevo —incluido el motor de fragmentación— reimplementa esa noción por su cuenta.

*Por qué:* hoy está duplicado en al menos cuatro archivos y **ya divergió**. El motor de reglas sería el quinto y el más importante: construirlo sobre una base que diverge es garantizar particiones incorrectas.

*Consecuencia:* centralizamos el dato, no necesariamente la interfaz. Una sola fuente de verdad, y encima funciones separadas y finitas por cada proyección que los consumidores necesiten. No forzamos un accessor único que devuelva todo.

<a id="d9"></a>
### D9 — Criterio de verificación: delta declarado, no diff contra el pasado `[Fundamento]`

El prompt de Fase 5 (auditoría de arquitectura) pedía verificar cada paso "comparando el artefacto generado antes y después". D2 mata esa política de preservar comportamiento, pero no mata la necesidad de un criterio de verificación — solo cambia contra qué se compara.

**Contra qué se compara: contra el delta declarado, no contra el output viejo.** Antes de correr un paso se enumera qué va a cambiar. Después, cada diferencia observada tiene que mapear a un ítem declarado. Criterio de aprobación: **cero deltas sin explicar**. No exige que nada cambie; exige que nada cambie por sorpresa.

*Herramienta:* normalización canónica — aplanar todos los `.ktr` a una secuencia ordenada de steps con su config y hops, ignorando fronteras de archivo. Así se genera la lista de deltas de forma confiable.

*Cuatro clases de cambio, cada una con su línea base propia* (un solo "diff" mezclaba las cuatro, por eso el diff se volvía ilegible):

| Clase | Ejemplo | Se valida contra |
|---|---|---|
| Costura forzada por el corte | 2 `TableInput` para alimentar un `StreamLookup` que antes era 1 | Canónico invariante |
| Funcionalidad nueva | Un step nuevo que antes no existía | Requisito propio, explícito |
| Rediseño (sustitución de tipo de step) | `DimensionLookup` → `InsertUpdate` | Decisión explícita con su costo declarado |
| Corrección / supuesto | Fix de nombre/rename, dialecto SQL asumido | Bug fix vs. supuesto introducido, declarado como tal |

*Consecuencia sobre la Restricción 1 de Fase 5 (`fase-5-plan-remediacion.md`):* se parte en dos lecturas — A) "el artefacto sigue produciendo lo mismo": **eliminada**, es lo que D2 dice que no se protege. B) "el repo queda verde y cada paso es revertible por separado": **se mantiene**, es regla de tamaño de paso, no de preservación de comportamiento.

*Por qué:* sin este criterio, D2 se leía como "no verificamos nada", que no es lo que dice — dice que no usamos "distinto de antes" como señal de bug por sí sola.

<a id="d10"></a>
### D10 — Sin período de convivencia entre parseo viejo y nuevo `[Fundamento]`

Consecuencia directa de D3 verificado (ver Verificaciones pendientes): como nadie tiene trabajo apoyado en datos guardados, el requisito de compatibilidad no existe. El mecanismo de vuelta atrás ante un problema es revertir el commit, no sostener dos caminos en paralelo.

*Consecuencia:* la sección "Compatibilidad durante la transición" del prompt de Fase 5 (`fase-5-plan-remediacion.md`) queda sin motivo — el borde nuevo puede reemplazar el parseo viejo de una vez, sin ventana planeada de convivencia.

*Por qué importa dejarlo explícito acá:* si el resto del prompt de Fase 5 se retoma sin marcar esto, se reabre desde cero una pregunta que ya tiene evidencia (D3).

<a id="d11"></a>
### D11 — `dim_contracts` (commit `149b836`) no choca con el refactor de fragmentación `[dim_contracts]`

Eje distinto: `dim_contracts` decide **qué tipo de step** carga una dimensión (SCD1 vs SCD2); la fragmentación decide **cuántos archivos**. No se pisan.

Más importante: `dim_contracts` ya usa el patrón que D6 pide — el backend deriva determinísticamente, el modelo no rejuzga en cada corrida (`dimension_step_policy.derive_dimension_step_type`). Es **precedente, no obstáculo**. No hay que tocarlo ni revertirlo.

*Consecuencia menor:* toca en chico dos cosas ya documentadas para cambiar bajo D8, ambas dentro del PASO 1 planeado — `dimension_step_policy.py:53` (copia propia de `parse_cfg`, ver H3 en `01-hallazgos.md`) y `dimension_step_policy.py:107` (alias de tabla con `or` inline en vez de `contracts.STEP_CONTRACTS.key_aliases`, ver H4).

<a id="d12"></a>
### D12 — Dialecto SQL: Postgres por defecto, con notificación obligatoria `[F4]`

El SQL generado depende del motor que declara el usuario, y hasta ahora eso no estaba escrito en ningún lado — Postgres fue un supuesto implícito horneado en construcciones específicas de dialecto en el SQL generado (ej. `DISTINCT ON`) en salidas de sesiones anteriores. No hay ocurrencias de ese patrón en el backend actual (`backend/`) — el supuesto vive en el SQL que el LLM genera dentro de `config`, no en código Python.

**Decisión:** por defecto, toda query SQL se genera asumiendo PostgreSQL. Queda escrito como decisión, no como supuesto implícito.

**Punto de notificación obligatorio:** cuando el flujo llegue al momento de generar SQL con dependencia de dialecto, tiene que avisar y dar contexto en vez de asumir en silencio. Es información crítica que se fija antes de generar — cambiarla después implica retocar todo lo ya generado.

*Por qué:* mismo principio que D9 — declarar antes, no explicar después.

*Fuera de alcance de esta decisión:* el soporte real multi-motor (Postgres / SQL Server según la base final elegida) no tiene plan todavía. Requiere sesión y sub-plan propios — ver "Abiertos" más abajo.

**Segunda y tercera ocurrencia confirmada (2026-07-22, `bitacora_etl_ventas.md`):** `DISTINCT ON` (R12, dedup de staging por `DISTINCT ON (clave_negocio) ORDER BY stg_fecha_carga DESC`) y `generate_series` (R10, calendario contiguo de `dim_tiempo`) — ambas construcciones exclusivas de Postgres, ambas usadas y confirmadas en verde en la solución de contraste de la bitácora. Ya no es un patrón hipotético citado de sesiones anteriores — es un caso real, empírico, generado por un LLM sin que el prompt se lo pidiera explícitamente. Refuerza la necesidad del punto de notificación obligatorio que esta decisión ya fija. Ruteo: F4 (contenido generado) — ver `03-plan.md`.

<a id="d13"></a>
### D13 — Definición de terminado, obligatoria para toda fase del plan `[Fundamento]`

Ninguna fase de `03-plan.md` (Track A o Track F) se da por cerrada sin estas tres cosas:

1. **Dos tests:** uno que haga cumplir específicamente lo que esa fase trabajó, y uno que verifique que el contrato que esa fase *expone* se sostiene (lo que la fase siguiente va a consumir) — escrito como contrato expuesto, no como "conexión con la fase siguiente", para no desactualizarse si el orden de fases cambia.
2. **El registro de deltas de esa fase** (D9), emitido como *warnings del propio pase* en el mismo punto del pipeline donde ya viven `repair_ktr_steps`, `repair_integrity_gaps` y `enforce_dimension_step_policy` — automático en cada corrida, no un documento que depende de que alguien lo escriba y lo lea. Tiene que cubrir **las dos fuentes de cambio**: lo que el backend genera determinísticamente y lo que produce una sesión de generación con el LLM. Los tests no lo reemplazan — un test afirma lo que a alguien se le ocurrió afirmar; el registro expone lo que viajó sin que nadie lo pidiera (ver "SCD tipo 2" en `01-hallazgos.md`, H9 — así se perdió esa vez). **Mismo canal que usa D15** para notificar al usuario final cuando el backend emite con un problema marcado en vez de abortar — no es solo un registro interno de la sesión de refactor.
3. **`CLAUDE.md` y un archivo de progreso actualizados:** qué cambió a nivel de convenciones/arquitectura/decisiones vigentes, y qué fase se cerró, qué queda, qué se decidió en el camino. Objetivo: el plan es retomable por cualquiera, no solo por quien lo arrancó.

*Por qué:* sin esto, el tramo "rojo" de la migración no tiene final definido fase por fase — siempre se corre un cambio más antes de reconectar.

<a id="d14"></a>
### D14 — F2/F3 no dependen del borde tipado grande; dependían circularmente de sí mismas `[F1.5/F2.5]`

`03-plan.md` hacía depender F2 de "borde tipado + STEP_CONTRACTS centralizado" en su columna "Depende de", mientras la columna "Hallazgos que toca" de esa misma fila listaba H4 y H11 — los hallazgos que esa centralización requiere resolver. Mismo patrón en F3: "Depende de" pedía H7 resuelto, y "Hallazgos que toca" incluía H7. Las dos fases dependían de algo que ellas mismas producían — sin punto de entrada válido.

**Lo que el motor de corte necesita en concreto, sin preguntas abiertas:**
- H4 — alias de tabla resuelto vía `contracts.STEP_CONTRACTS.key_aliases`, no la copia divergente de `lineage_builder` (ni el `or` inline de `dimension_step_policy.py:107`).
- H11 — `DBLookup` cubierto en la matriz R/W (hoy invisible para el linaje).
- H6 — el parseo de `config` falla fuerte (D5) en vez de degradar a `{}`. Relevante para el corte porque una config rota leída como `{}` produce un corte silenciosamente equivocado.

Los tres tienen dirección ya decidida (D5, D8) y no dependen de ningún spike ni de ninguna pregunta listada en "Deliberadamente no decidido".

**Corrección 2026-07-22 — H6 lo cierra F1.5, no F5 (contradicción encontrada y resuelta entre este archivo y `03-plan.md`).** La redacción original decía que H6 "se resuelve solo cuando F5 deduplica los 4 copies", pero la fila de F1.5 en `03-plan.md` ya listaba a H6 como parte de su propio alcance — dos fases reclamando el mismo fix. Gana F1.5: dedup de `parse_cfg` (H3) y fail-fast (H6) son la misma pieza de trabajo (no tiene sentido arreglar el comportamiento de 4 copias por separado), y F1.5 es la fase que ya está tocando este archivo por H4/H11. F5 pierde ese ítem — ver su fila actualizada en `03-plan.md`. **H4 y H11 ya resueltos** en esta misma sesión (ver `01-hallazgos.md`) — como efecto colateral, la copia de `_parse_cfg` en `dimension_step_policy.py` ya desapareció (importa `contracts.parse_cfg`), así que el dedup restante de H3 pasó de 4 copias a 3 (`validate.py`, `ktr_default_validator.py`, `lineage_builder.py`). **H6 en sí (el fail-fast) sigue sin implementar** — pendiente de la pregunta abierta más abajo sobre si el fallback a `{}` puede llegar a ejecutarse de verdad y con qué severidad, antes de tocar el comportamiento.

**Lo que el motor de corte NO necesita:** el borde tipado grande tal como lo describe `00-objetivo.md` (cambio de schema `string → object`, H2; border único con tipo validado). Esa sigue siendo una pregunta de arquitectura de entrada completa, abierta, sin fecha porque depende de Track A (pospuesto) y de un spike empírico. El corte puede construirse sobre el `dict` que ya devuelve `parse_cfg` hoy, siempre que tenga los tres puntos de arriba resueltos primero.

**Consecuencia — desdoblamiento de fases (ver `03-plan.md`):** H4+H11+H6 pasan a una fase previa chica (F1.5), separada de F2. H7 pasa a una fase previa propia (F2.5), separada de F3. Ninguna fase queda dependiendo de sí misma.

*Por qué:* mismo principio que D8 — el conocimiento de dominio tiene una sola casa, y esa casa se construye antes de que el consumidor (el corte) la dé por hecha, no como parte del mismo paso que la consume.

<a id="d15"></a>
### D15 — Fail-fast en detección, no fail-hard en emisión: el backend emite mejor esfuerzo y notifica `[Fundamento]`

Ajuste de alcance sobre D5, motivado por el modelo de producto: el sistema es un acelerador para profesionales de Spoon, no un generador que garantiza corrección por sí solo. Un `.ktr` emitido con un problema señalado es menos costo para el usuario que un backend que se niega a generar — el costo de la alternativa estricta (tocar backend, regenerar steps, mecanismos de descarga de steps armados solo para mitigar ese costo) ya se pagó una vez.

**D5 se parte en dos mitades — no se revierte, se acota:**

- **Fail-fast en detección/parseo — sigue igual, sin cambios.** Un `except: return {}` que traga un error de parseo (H6) sigue prohibido: un error tragado no se puede notificar después. Esta mitad de D5 no se toca.
- **Fail-hard en emisión — se retira.** El backend ya no se niega a emitir un `.ktr`/`.kjb` porque un chequeo de integridad (V2 — ver corrección abajo sobre qué rol juega cada validador — o cualquier check de `error_catalog_checks.py`) encontró un problema en un input malformado o patológico. Emite el mejor esfuerzo posible y marca el archivo.

**Mecanismo de notificación — reutiliza D13, no uno nuevo.** Todo error detectado se documenta en el registro de deltas de D13 (los `warnings` que ya recorren el pipeline en el mismo punto que `repair_ktr_steps`/`repair_integrity_gaps`/`enforce_dimension_step_policy`, y que ya vuelven al caller como tercer elemento de la tupla de `build_ktr`). D13 ya declaraba ese canal como automático y ligado a la corrida — esta decisión fija que además es el canal que llega al usuario final, no solo un registro para quien audita la sesión de refactor.

**Requisito de forma — accionable, no genérico.** Cada notificación dice: qué archivo, qué se infirió (ej. "orden asumido: STG antes que DWH, no verificado contra grafo de FK"), y qué revisar antes de correr en Spoon. Un warning genérico ("hubo un problema") no cumple esta decisión.

**Consecuencia concreta sobre código ya escrito, no solo sobre diseño futuro:**
- `ktr_xml_validator.py:100-117` (`validate_ktr_xml`, `raise KtrXmlValidationError`) está wireado siempre en `build.py:401` y hoy aborta la emisión — es exactamente el comportamiento que esta decisión retira. Pasa a alcance de **F3** (que ya toca este archivo, ver `03-plan.md`): convertir el `raise` en un finding anotado + notificación accionable por el canal de D13.
- `error_catalog_checks.py` (V4-V13) verificado sin callers en el backend — no está wireado a nada todavía, no hereda el problema, pero cuando se conecte nace directo con el patrón "anota, no aborta".
- `00-objetivo.md` describía los validadores V1/V2/V3 como gate que "aborta... nunca emite un artefacto incoherente" — corregido en ese archivo para reflejar esta decisión.

**H5 (linaje acoplado por orden de ejecución, `01-hallazgos.md`) — resuelto bajo esta decisión.** Opción elegida: riesgo documentado y notificado, no prerrequisito bloqueante. F1.5 mantiene su alcance original (H4 + H11 + H6, sin H5). F2 diseña el corte apoyándose en `build_lineage()` tal como está — con el acoplamiento R10 (`arquitectura-objetivo.md`) todavía presente — siempre que emita el aviso accionable cuando no pueda garantizar el orden inferido.

**Corrección (2026-07-22) — el corte no es una compuerta que falla, es separación constructiva.** La redacción original de este punto preguntaba "qué hace F2 cuando el corte no puede satisfacer V1/V2/V3 limpio" — presuponía un estado de fallo que un ETL válido no produce. Un ETL válido es un DAG; separarlo en KTR ordenados por un KJB, siguiendo la señal estructural, produce un resultado válido por construcción. No existe "no se pudo cortar" para un input válido.

Consecuencia sobre el rol de cada validador — **V1 y V3 no son gates, son las reglas que guían dónde separar:**
- **V1** (ninguna tabla W y R en el mismo KTR) y **V3** (un solo escritor por tabla por KTR) son señal estructural de corte (consistente con C.2 y D6-bis): tabla escrita y leída por steps distintos, o doble escritor, marcan frontera. Separar exactamente ahí satisface V1/V3 por construcción — no se validan después, se usan para decidir el corte.
- **V2** (todo lookup tiene productor en el job) es distinto: no dice dónde separar, dice si el ETL está completo. Un lookup sin productor es un dato faltante — error a notificar bajo esta misma D15, no una señal de fragmentación.

Lo que sí sigue bajo D15 (generar-y-notificar, no bloquear): el caso genuinamente patológico — ciclo real en el grafo, `config` malformado que ni H6 pudo salvar, lookup sin productor (V2). Ninguno de esos es una rama del algoritmo de corte; son el mismo mejor-esfuerzo que D15 ya cubre para cualquier otro fallo de generación. F2 no diseña un plan B para el corte — diseña la separación constructiva. Detalle de las reglas concretas en el Reporte F2 (`03b-reportes.md`).

*Por qué separado de D5 en vez de reescribirla:* mismo criterio que D6/D6-bis — D5 sigue siendo la doctrina general (ante la duda, fallar visible). D15 fija dónde se traza la línea entre "fallar" (detección, sigue firme) y "bloquear" (emisión, se retira), que D5 dejaba ambigua y que `00-objetivo.md` había resuelto para el lado que esta decisión ahora corrige.

<a id="d16"></a>
### D16 — El corte tiene una dependencia externa real (eje `dim_contracts`), no una que Track F resuelva `[F3]`

Disparada por el análisis de `bitacora_etl_ventas.md`/`extracto_corte_F2.md` (2026-07-22): el `extracto` preguntó si C1-bis (doble escritor sobre `dim_producto` en `err1.ktr`/`err2.ktr`, H21) era un **fantasma** — un artefacto de que el step estaba mal elegido, no un problema estructural real. Verificado contra el código (no contra memoria):

- `enforce_dimension_step_policy` (`dimension_step_policy.py:41-50`, `derive_dimension_step_type`) **sí** corre antes del punto de inserción del corte (H20) — orden confirmado: `repair_ktr_steps → repair_integrity_gaps → enforce_dimension_step_policy → [corte] → build_ktr` (`etl_generator.py:800-818`). El orden no es el problema.
- Pero su vocabulario de salida es binario y no cubre el caso real: deriva únicamente `DimensionLookup` (scd_type==2) o `CombinationLookup` (cualquier otro caso) — **nunca** `Insert/Update`, `Table Output` ni `StreamLookup`. La bitácora (R1, confirmado por log en `L2-E01`/`L3-E01`) prueba que para una dimensión simple (sin `version`/fechas) el step correcto es `Insert/Update` (o el patrón `Table Output` insert-new-only), no `CombinationLookup` — combinación nunca ejercitada ni por la bitácora ni por el repo.
- Más grave: **ninguno de los dos tipos derivables hoy es de solo lectura.** `DimensionLookup` y `CombinationLookup` son R+W siempre (H19: el builder hardcodea `update=Y` / la semántica del step no tiene modo solo-lectura). `enforce_dimension_step_policy` tampoco distingue "este step carga la dimensión" de "este step solo busca la FK para el hecho" — corrige el *tipo* de cualquier step que matchee una tabla de `dim_contracts`, sin importar su rol. Consecuencia: aunque el tipo derivado sea "correcto" según SCD, el step usado como lookup del lado del hecho sigue siendo R+W por construcción — exactamente el patrón que dispara C1/C1-bis en `err1.ktr`/`err2.ktr` (H21) y que la bitácora reprodujo de forma independiente en `dim_producto` (L1-G1/L2-E01).

**Conclusión: C1-bis no es un fantasma — es una señal real que se va a seguir disparando sobre ETLs legítimos** hasta que exista un tipo de step genuinamente de solo lectura para el lookup del lado del hecho. La bitácora ya lo resolvió empíricamente dos veces por caminos independientes: R2 (lookup de dimensión en el hecho siempre de solo lectura) + R9, refinado por log (`DBLookup` falla la introspección de metadata contra el pooler de Supabase — `getTableFields`, ver H23 en `01-hallazgos.md`; el sustituto que funcionó es `StreamLookup`, que además no toca tabla en la matriz R/W — H19 — así que un lookup de hecho implementado como `StreamLookup` nunca dispara el corte, por diseño, no por parche).

**Ubicación de la corrección — eje `dim_contracts`, NO el motor de corte (D6-bis, D11):** esto no es fragmentación — es selección de step por forma de tabla/rol, mismo eje que ya decide SCD1 vs SCD2 (`dimension_step_policy.py`, serie `dim_contracts`, D11). Track F no lo implementa; Track F **depende** de que se implemente. Es la misma relación de dependencia externa que D14 ya nombró para el borde tipado grande (H2) — con una diferencia importante: el borde tipado grande **no** bloqueaba a Track F (D14). Esto **sí** lo hace, aunque viva en otro eje.

**Consecuencia sobre el plan:** F3 (implementación del corte) tiene un prerrequisito externo a Track F, no solo F1.5/F2.5 (D14). Dos caminos, a decidir por el usuario antes de F3, no algo que esta sesión resuelva unilateralmente:
1. Ampliar el vocabulario de `derive_dimension_step_type` (agregar `Insert/Update`/`Table Output` para el loader cuando la forma de la tabla lo pide, y forzar `StreamLookup` — no `DimensionLookup`/`CombinationLookup`/`DBLookup` — para cualquier step que solo busca la FK del lado del hecho) **antes** de que F3 arranque.
2. F3 arranca igual, con el riesgo documentado y notificado (D15): el corte puede sobre-disparar C1-bis sobre ETLs donde el "doble escritor" es en realidad un lookup mal tipado, no un conflicto real — y el usuario revisa esos casos a mano hasta que el camino 1 se resuelva.

*Por qué D16 y no una fila más en `03-plan.md`:* cambia qué puede prometer F3 sin trabajo externo, igual que D14 — nivel de decisión de scope, no de tarea.

**Resuelto 2026-07-23 — camino 1, elegido por el usuario.** Ampliar `derive_dimension_step_type`/`enforce_dimension_step_policy` (`dimension_step_policy.py`) antes de que F3 arranque. **No implementado todavía — y no es un cambio chico de enum:**

- Hoy `DIMENSION_STEP_TYPES = {"DimensionLookup", "CombinationLookup"}` (`dimension_step_policy.py:39`) y `derive_dimension_step_type` (`:42-51`) no tienen ningún concepto de **rol** — `enforce_dimension_step_policy` corrige el tipo de *cualquier* step que toque una tabla de `dim_contracts`, sea el step que carga la dimensión o el que solo busca la FK del lado del hecho (exactamente el gap que documenta H22). Agregar `Insert/Update`/`Table Output` al vocabulario del loader no alcanza solo: hace falta **detectar el rol** (loader vs. lookup-de-hecho) antes de poder aplicar una regla distinta a cada uno.
- Señal disponible para esa detección: R2/R9 de la bitácora ya validan que el lookup del lado del hecho es siempre de solo lectura — un candidato es reusar el rol que `lineage_builder._classify_layer` ya deriva por step (in_deg/out_deg + tabla), o el mismo insumo de H19 (matriz R/W) que F2 construye para el corte. Confirmar cuál antes de escribir código — esto es una mini-decisión de diseño propia, del mismo tamaño que la que F2 necesitó, no una edición de una línea.
- Una vez detectado el rol: loader puede derivar `DimensionLookup`/`CombinationLookup`/`Insert-Update` según `scd_type` + forma de tabla; lookup-de-hecho se fuerza a `StreamLookup` (nunca `DimensionLookup`/`CombinationLookup`/`DBLookup` — `DBLookup` además falla contra el pooler de Supabase, H23/R9).

Sigue bloqueando F3 hasta que esto esté en código, no solo decidido.

**Código aplicado 2026-07-24 (parcial, ver residual abajo).** `dimension_step_policy.py`:
- `role_of_dimension_step(step_name, table, ktr_data, step_type_aliases)` — BFS hacia adelante sobre los hops habilitados, ancla el predicado "escritor" en `_UNAMBIGUOUS_WRITER_TYPES = {TableOutput, InsertUpdate, Update, Delete}` (nunca en DimensionLookup/CombinationLookup, cuyo status de escritura es exactamente lo que se está resolviendo para la misma tabla — evita el chicken-and-egg). Si alcanza un escritor de tabla DISTINTA de `table` → `"fact_lookup"`; si no (termina en la propia tabla, o en sinks sin tabla como WriteToLog/checkpoints) → `"loader"`.
- `enforce_dimension_step_policy` (Paso 4): rol `fact_lookup` con `scd_type==2` → fuerza `DimensionLookup` + `cfg["update"]="N"` (warning). Respeta `OVERRIDE_STEP_PREFIX` igual que el resto de la función.
- `lookups.py::_step_DimensionLookup` (Paso 5): dejó de hardcodear `<update>Y</update>` — ahora lee `cfg.get("update", "Y")`.

**Residual `scd_type` 0/1 (dimensión sin versionar) — cerrado 2026-07-24, camino prompt, no auto-repair.** El contrato deriva `CombinationLookup`, que no tiene modo de solo-lectura (a diferencia de `DimensionLookup`, no expone flag `update`). Forzar `DimensionLookup+update=N` sin `date_from`/`date_to` conocidas seguía descartado por el mismo riesgo de siempre (referenciar columnas de vigencia que la tabla no declara).

Antes de cerrar se evaluó — y se descartó — la opción obvia: `DatabaseLookup` puro para "clave natural sin necesidad de generar surrogate". Dos motivos, no uno:
1. **Ya excluido por H23/R9** — `DBLookup` falla la introspección de metadata contra el pooler de Supabase en este entorno, motivo por el que D16 (arriba) ya lo excluye explícito del rol `fact_lookup` junto con `DimensionLookup`/`CombinationLookup` con escritura.
2. **Estructural, no solo de entorno:** una vez que `compute_cut()` separa el loader de la dimensión en su propio `.ktr` (F2/F3), el step de lookup del lado del hecho vive en OTRO archivo — no hay stream en memoria que compartir entre archivos Kettle. `StreamLookup` (el sustituto que sí funciona, H23) necesita su propio `TableInput` que relea la dimensión ya cargada, DENTRO del mismo archivo que el lookup — no puede apuntar a un step de un `.ktr` distinto.

Sintetizar ese `TableInput`+hop nuevos automáticamente en `enforce_dimension_step_policy()` se evaluó y se descartó — sería la primera vez que esa función muta topología (steps/hops) en vez de solo config de un step existente, sin precedente en el archivo y con más superficie de bug que beneficio. **Camino elegido: mismo patrón que cerró H23/R9 (D22) — guía de generación, no reparación automática:**
- `system_etl.txt` — nueva sección "LOOKUP DE FK DEL LADO DEL HECHO — CUÁNDO ESTE STEP NO PUEDE VOLVER A ESCRIBIR [D16]" (junto a "STEP DE DIMENSIONES") instruye al LLM: `scd_type==2` → `DimensionLookup` solo-lectura (sin cambios); `scd_type` 0/1 → `TableInput` (relee la dimensión ya cargada) + `StreamLookup` (match por clave natural), nunca `CombinationLookup`/`DimensionLookup` con escritura ni `DBLookup`. Checklist ítem 24 nuevo.
- `dimension_step_policy.py` (`enforce_dimension_step_policy`, Paso 4) sigue "reporta, no repara" para este caso — sin cambio de comportamiento — pero el mensaje de error ahora apunta al fix concreto (TableInput+StreamLookup, referencia a `system_etl.txt` y a esta decisión) en vez de "revisar a mano (D16, residual)" genérico.

No bloquea F3 (nunca bloqueó, D15). Cierre completo: la ambigüedad de "no hay mecanismo seguro" quedó resuelta — el mecanismo existe (TableInput+StreamLookup), vive en la capa de generación, con el backend como red de seguridad si el LLM no lo sigue.

Tests: `tests/test_dimension_step_policy.py` (6 casos de la sesión original, incluida la reproducción de `err1.ktr`/`err2.ktr`, + 2 asserts nuevos sobre el contenido del mensaje de error del caso scd 0/1).

<a id="d17"></a>
### D17 — F2 (diseño del corte) aprobado por el usuario `[F2]`

**Aprobado 2026-07-23.** El diseño de F2 (Reporte F2 en `03b-reportes.md`, 2026-07-22: matriz R/W, disparadores C1/C1-bis, componentes conexos, excepción self-lookup, orden topológico, validado contra `err1.ktr`/`err2.ktr`) queda aprobado tal como está documentado. Desbloquea uno de los tres prerrequisitos de F3 (los otros dos: F2.5 en código, D16 camino 1 en código — ninguno de los dos escrito todavía).

<a id="d18"></a>
### D18 — H2 (config `string`→`object`) propuesto para adelantarse como fix de raíz de H6, no decidido — requiere spike antes de tocar `ETL_OUTPUT_SCHEMA` `[F1.5]`

**Contexto (2026-07-23):** en vez de parchear H6 (fail-fast en `parse_cfg`) como venía planeado en F1.5, se propuso ir a la raíz — cambiar `config` de string a object en `ETL_OUTPUT_SCHEMA` para que el parseo deje de existir (no hay JSON que fallar al parsear si nunca fue string). Coherente con D2 (no protegemos el string actual porque "hoy funciona").

**Por qué no se implementa todavía, aunque D2 lo permita en principio:**
- `ETL_OUTPUT_SCHEMA` (`etl_output.py:1-13`) ya documenta por qué se descartó: un `config` object abierto sin `oneOf` por tipo de step "would either require a massive oneOf discriminator or would reject valid configs".
- Verificado en código, no en teoría: `AnthropicLLM._sanitize_for_anthropic`/`_enforce_adp` (`anthropic_llm.py:36-57`) fuerza `additionalProperties:false` + `properties:{}` en cualquier nodo `object` sin properties declaradas — un `config` object abierto ya colapsa a `{}` siempre para Anthropic, hoy. No es un riesgo, es un hecho ya reproducible en el código tal como está.
- Arreglarlo bien (no solo evitar el colapso) exige un `oneOf`/`anyOf` discriminado por los ~35 tipos de step que documenta `system_etl.txt:170-414`, cada uno con su propio schema cerrado. Si Gemini (`response_json_schema`) y Anthropic (`input_schema` de tool-use) soportan de forma confiable un discriminador de ese tamaño **no está verificado** — es exactamente el "spike empírico contra Gemini y Anthropic" que este mismo archivo ya tenía anotado en "Deliberadamente no decidido" para H2, antes de esta sesión.
- Si el spike falla para alguno de los dos proveedores, el fallback existente es modo texto + `extract_first_json` (regex) — estrictamente peor que el string tipado actual, no mejor. Cambiar la raíz sin confirmar primero puede empeorar la confiabilidad de generación en producción, no solo fallar en desarrollo.

**Estado: no decidido.** Camino recomendado, no ejecutado todavía: spike acotado (1-2 tipos de step, ej. `TableOutput`) contra Gemini y Anthropic reales antes de tocar el schema completo — confirmar que un object cerrado con properties explícitas no colapsa y valida bien, antes de escribir las ~35 variantes. Mientras el spike no corra, **F1.5 mantiene su alcance original**: fail-fast simple en `parse_cfg` + dedup de las 3 copias (H6), no bloqueado por esta propuesta.

*Por qué D18 y no una edición directa de H2:* cambia si H2 se adelanta o se mantiene pospuesto — decisión de scope y de secuencia, no un dato nuevo sobre el hallazgo en sí.

<a id="d19"></a>
### D19 — F3 punto 1-3 (wiring del corte) cerrado a nivel de servicio; el flujo HTTP en vivo se queda en modo notificación hasta extender `ETLGenerateResponse` `[F3]`

**Contexto (2026-07-24):** al arrancar F3 punto 1 (wiring de `compute_cut()` a `etl_generator.py`, ver `03-plan.md`), apareció un hueco no listado en la sección "Archivos a tocar" del reporte F2: `ETLGenerateResponse` (`backend/app/schemas/etl_schemas.py:119-136`) y el ZIP del frontend (commit `338bff2`) están cableados a exactamente 1 KTR por etapa + 1 `.kjb` (2 archivos + 1 job). Si `compute_cut()` devuelve `groups>1` en una etapa real — exactamente el patrón de `err1.ktr`/`err2.ktr` (H21), el caso que motivó todo el refactor — no hay dónde poner los archivos extra en la respuesta HTTP.

**Decisión (confirmada por el usuario, alcance de sesión):** separar "capacidad de servicio" de "entrega por HTTP". Esta sesión implementó y probó a nivel de servicio (`etl_generator.py`/`lineage_builder.py`) la partición real: `split_ktr_by_cut()`, `_build_ktr_stage()` (llama `build_ktr()` una vez por grupo), `_build_job_plan()` generalizado a N por etapa (jerarquía de 3 niveles, F2.5/H7), `stitch_lineage_many()` generalizado a M archivos. Todo esto es código-listo y probado (`test_fragmentation_wiring.py`, 13 tests) pero el flujo HTTP en vivo (`_build_response_from_two_ktr_data`/`_build_response_from_data`) **no** invoca `_build_ktr_stage()` para partir de verdad — solo llama `compute_cut()` para sus notificaciones. Si detecta `groups>1`, entrega el `.ktr` sin partir + un `Validacion(tipo="error")` explícito señalando la tabla y los steps en conflicto, en vez de fallar en silencio o dropear archivos.

**Por qué no se resolvió el hueco de `ETLGenerateResponse`/frontend en la misma sesión:** es un cambio de contrato público (schema de respuesta + consumidor del ZIP en el frontend), de otro orden de magnitud que "llamar `build_ktr()` una vez por grupo" — amerita su propio diseño (¿lista de KTRs? ¿mantener los 2 slots históricos + un array de "extras"?) y su propia sesión, no una decisión de paso mientras se wireaba el corte.

**Efecto inmediato, sin esperar la extensión del schema:** todo pipeline de generación real ahora corre `compute_cut()` (antes no corría en absoluto) — un ETL que hoy dispara C1/C1-bis (carrera/doble-escritor, el bug de origen del refactor) sale con un `Validacion(tipo="error")` explícito en vez de silencioso. Es una mejora de diagnóstico entregada ya, independiente de cuándo se resuelva el hueco.

**Estado: F3 sigue "EN CURSO"**, no cierra hasta que el hueco de arriba se resuelva (ver "Estado F3" en `03b-reportes.md`) y corra un test de integración end-to-end contra el pipeline HTTP completo con un caso que dispare un corte real.

<a id="d20"></a>
### D20 — Forma de la respuesta con N archivos (diseño, cierra el hueco de D19) `[F3]`

**Contexto (2026-07-24):** D19 dejó abierto cómo extender `ETLGenerateResponse` (hoy fija a `ktr_xml`/`ktr2_xml`/`kjb_xml`) para entregar N archivos por etapa cuando `compute_cut()` devuelve `groups>1`. Esta sesión cierra el diseño; implementación (backend) y consumo (frontend, ZIP) quedan para sesiones separadas — ver punto 5.

**Respuestas del usuario que fijan el diseño:**

1. **No hay más casos conocidos de N>1, y no hacen falta.** El criterio ya es estructural, no un catálogo de casos: "si un step escribe una tabla y otro step la lee, no pueden vivir en la misma transformación." Esto **ya es exactamente C1/C1-bis** (F2, `03-plan.md`), no una regla nueva. Confirma que D7 (reglas derivadas de casos reales) y D6-bis (señal estructural, no legibilidad) alcanzan por sí solas para cualquier N futuro — el algoritmo generaliza porque la señal es la misma sin importar cuántas veces dispare, no hace falta enumerar escenarios.

2. **Sin compatibilidad hacia atrás que preservar (refuerza D4).** Único consumidor de `ktr_xml`/`ktr2_xml`/`kjb_xml` es el frontend de este mismo repo. Se puede romper el schema de respuesta sin período de convivencia — el frontend se arregla después, en su propia sesión (punto 5).

3. **Forma de la respuesta — jerarquía de 2 a 4 niveles, no lista plana.** El usuario describe 4 combinaciones, una por cada etapa (Origen→Staging, Staging→DWH) siendo simple o partida:
   - (a) ambas partidas: 1 KJB maestro → 2 sub-KJB (uno por etapa) → cada sub-KJB orquesta 1+ KTR.
   - (b) solo Origen→Staging partida: 1 KJB maestro → 1 sub-KJB (orquesta 1+ KTR) + 1 KTR directo (Staging→DWH).
   - (c) solo Staging→DWH partida: simétrico a (b).
   - (d) ninguna partida (caso vigente hoy): 1 KJB maestro → 2 KTR directos. La response no cambia de forma en este caso.

   Mapea 1:1 con lo que el backend ya construye a nivel de servicio (`_build_job_plan` N-ario, D19): cada etapa es o bien un KTR único (`entry_type="trans"` directo) o un KJB intermedio + N KTR (`entry_type="job"`). **La respuesta debe reflejar esa estructura, no aplanarla.** Diseño concreto para `ETLGenerateResponse`: reemplazar los slots fijos `ktr_xml`/`ktr2_xml` por una lista de 2 `EtapaOutput` (una por fase lógica, orden fijo Origen→Staging / Staging→DWH), cada una con forma:
   - `{tipo: "ktr", archivo: {xml, filename}}` — caso simple.
   - `{tipo: "kjb", kjb: {xml, filename}, archivos: [{xml, filename}, ...]}` — caso partido.

   Más `kjb_master: {xml, filename}` al tope, sin cambios respecto a hoy. Esto es diseño, **no implementado todavía** — próxima sesión de backend.

4. **UX del multi-archivo — confirma agrupación por carpeta, convención de nombres ya vigente.** El nombre de archivo ya codifica tipo/tabla/etapa (`ktr_builder`, existente). Cuando una etapa es `tipo:"kjb"`, sus KTR van agrupados en una carpeta nombrada por esa etapa/sub-job dentro del ZIP; el sub-KJB queda expuesto junto al maestro, no escondido en la carpeta. Caso (d) — el vigente hoy — el ZIP se mantiene plano, sin carpetas, sin cambio de UX percibido. Trabajo de ZIP/frontend (`etlCardActions.js`, JSZip) — **no entra en esta sesión** (punto 5).

5. **Alcance de sesión — entregas separadas.** Esta sesión cierra el diseño de la respuesta (arriba). Implementación en dos tandas futuras, no en la misma sesión: primero backend (`ETLGenerateResponse` + conectar `_build_ktr_stage()` de verdad en `_build_response_from_two_ktr_data`/`_build_response_from_data` en vez de solo notificar), después frontend (consumo del nuevo shape + ZIP con carpetas).

**Consecuencia sobre D19 y `03-plan.md`:** el hueco que D19 dejaba abierto (qué forma tiene la respuesta) queda **diseñado, no implementado**. F3 sigue "EN CURSO" — no cierra hasta que la implementación backend del punto 5 esté en código y probada end-to-end (ver "Estado F3" en `03b-reportes.md`; esos puntos no cambian de contenido, solo se resuelve la pregunta de diseño que bloqueaba empezarlos).

*Por qué D20 y no una edición directa de D19:* D19 documentó el hueco cuando apareció, a mitad de sesión, sin la información para cerrarlo. D20 es la sesión siguiente cerrando esa pregunta con datos del usuario — mismo patrón que D16→"resuelto 2026-07-23", se separa para que quede trazable qué se sabía en cada momento.

**Backend implementado 2026-07-24 (sesión 3).** `ETLGenerateResponse` (`etl_schemas.py`) reemplazó `ktr_xml`/`ktr_filename`/`ktr2_xml`/`ktr2_filename`/`kjb_xml`/`kjb_filename` por `etapas: list[EtapaOutput]` (`ArchivoKtr{xml,filename}`, `EtapaOutput{tipo:"ktr"|"kjb", archivo?, kjb?, archivos[]}`) + `kjb_master: ArchivoKtr|None`, exactamente como quedó diseñado arriba. `_build_response_from_two_ktr_data`/`_build_response_from_data` (`etl_generator.py`) dejaron de llamar `build_ktr()` directo y ahora pasan por `_build_ktr_stage()` → cuando `compute_cut()` detecta `groups>1` en una etapa, esa etapa sale como `tipo="kjb"` con sus N archivos reales, no como un `.ktr` sin partir con una advertencia (el hueco que D19 dejaba). Sin período de convivencia (D4/D20-punto2): el shape viejo desapareció del todo — **el frontend actual no puede leer una respuesta nueva hasta su propia sesión** (D20-punto5, no tocado acá).

Dos bugs reales encontrados y corregidos al conectar el corte de verdad (invisibles mientras `compute_cut()` solo generaba notificaciones, D19):
1. **`build_ktr()` prioriza `ktr_data["name"]` por sobre el nombre pasado por parámetro** (`build.py:188`). `split_ktr_by_cut()` copia `{**ktr_data, "steps":..., "hops":...}` preservando `"name"` sin cambios en cada sub-dict — sin fix, los N archivos de un corte real comparten el mismo `<name>` interno y el mismo filename (el modelo siempre manda `ktr.name`, `ETL_OUTPUT_SCHEMA` lo exige). Fix en `_build_ktr_stage()` (`etl_generator.py`): pisa `sub["name"]` con el nombre por-grupo antes de llamar a `build_ktr()`, solo cuando hay más de 1 grupo.
2. **`compute_cut()` separaba en archivos distintos cualquier par de componentes de hop desconectados, incluso sin ninguna señal estructural entre ellos** — contradecía la doctrina que el propio docstring del módulo ya declaraba (D6-bis: "componentes sin tabla-disparadora se agrupan todos juntos"), pero el código no lo implementaba: cada componente conexo se devolvía como su propio grupo sin condición. Invisible mientras el corte no se aplicaba de verdad. Caso real que lo dispara: 2 tablas de origen independientes cargando 2 tablas de staging independientes (sin ningún hop entre las dos ramas) — el caso más común de un ETL con más de una tabla de origen. Fix en `compute_cut()` (`fragmentation.py`): los componentes sin ninguna `trigger_edge` se fusionan en un único grupo adicional; solo los componentes conectados por una relación de tabla real (C1/C1-bis) se ordenan y separan.

Tests: `test_etl_generate_response_shape.py` (nuevo, 5 casos — split real en `_build_response_from_two_ktr_data`/`_build_response_from_data`, round-trip JSON del contrato, rechazo de `tipo` inválido, end-to-end HTTP contra `/api/v1/etl/generate-from-inference` con un caso que dispara corte real) + 2 casos nuevos en `test_fragmentation.py`/`test_fragmentation_wiring.py` cubriendo el bug de componentes desconectados sin señal. Suite completa corrida en frío: mismos 45 fallos preexistentes de antes de esta sesión (2 bugs no relacionados en `test_ktr_xml_validator.py`/`test_structured_outputs.py`, 6 en `test_ktr_build_job_api.py` por un bug preexistente y no relacionado de `ConnectionsMapRequest`/`InlineConnection` — el test manda un `connection_id` string donde el schema espera un objeto `InlineConnection`, sin tocar en esta sesión —, y 37 en `test_api.py` por apuntar a un servidor real en `localhost:8000` que no corre en CI), cero fallos nuevos.

**F3 sigue "EN CURSO"** — falta D20-punto5 (frontend: consumir el nuevo shape + ZIP con carpetas), sesión aparte.

<a id="d21"></a>
### D21 — C.6 resuelta: política ante FK no resuelta = miembro inferido, implementado sin reabrir D16 `[F4]`

**Contexto (2026-07-24):** el usuario trajo la práctica estándar de Kimball para este caso (`fact_venta.fk_producto` NOT NULL, `id_producto` de la venta ausente del maestro en el momento de la carga) — tres políticas posibles, con criterio explícito de cuándo usar cada una.

**Decisión — miembro inferido (inferred member) como política de negocio para R5-b/R11/C.6:**
- El lookup nunca devuelve NULL. Si `id_producto` no matchea, se crea al vuelo una fila placeholder en `dim_producto`: `sk_producto` nuevo, la clave natural real (`id_producto`, ya conocida desde el hecho), atributos con default ("Pendiente"/"Desconocido"), flag `inferred_member='Y'`. El hecho inserta con esa FK válida — sin pérdida de fila, NOT NULL satisfecho.
- Cuando el producto real llega en un batch futuro, overwrite tipo 1 sobre esa misma fila: el `sk` no cambia, los hechos ya cargados quedan enlazados retroactivamente sin reproceso.
- Criterio de cuándo aplica cada política (de negocio, no técnico): **miembro inferido** es el default para hechos que deben reportarse aunque la dimensión no exista todavía (caso normal de ventas). **Miembro desconocido único** (`sk=-1`/`sk=0`) se reserva para claves genuinamente nulas/inválidas en el origen, no para "todavía no llegó" — pierde la clave natural, no se puede reconectar después. **Rechazo/cuarentena** (R11, ya validado en la bitácora vía Sol02) solo si la política de negocio prohíbe explícitamente hechos con dimensión incompleta.

**Choque encontrado con D16 (cerrada, código ya shippeado) — resuelto sin reabrirla:** la implementación nativa de Pentaho para este patrón (step único `Dimension Lookup/Update` en modo `update=Y`, directo en el stream del hecho) es exactamente el step/rol que D16 prohíbe:
- `dimension_step_policy.py:190-227` fuerza cualquier step en rol `fact_lookup` a `DimensionLookup` + `update="N"` — lo reescribiría de vuelta a solo-lectura, neutralizando el placeholder en silencio.
- `fragmentation.py:46-47` clasifica `DimensionLookup` con `update="Y"` como `"RW"` — combinado con el loader dedicado de `dim_producto` (otro step, otro writer), dispara C1-bis (doble escritor), la señal que el propio refactor existe para eliminar.

**Camino de implementación — corregido en la misma sesión (steps separados descartado, ver abajo por qué).** Primer intento (`StreamLookup` → `FilterRows sk IS NULL` → Insert dedicado en el lado del hecho → merge) quedó descartado tras revisar `compute_cut` en detalle: el Insert dedicado es un **segundo writer real** de `dim_producto` (el loader ya es el primero). `compute_cut` (`fragmentation.py:149-188`) sí detecta esto como C1-bis, pero:
- Si loader e Insert-dedicado caen en componentes de hop distintos (caso esperado, igual que `err1.ktr`/`err2.ktr`), el edge de orden entre ambos (`fragmentation.py:183-188`) se arma en el orden de `enumerate(writers)` — orden de aparición en la lista `ktr_data["steps"]` del JSON, **no** el orden de ejecución real (eso lo da `hops`). Nada garantiza que el loader aparezca antes que el Insert-dedicado ahí — si el LLM los emite al revés, el topo-sort fuerza fact-antes-que-loader en silencio, exactamente al revés de lo que necesita miembro inferido.
- Si por algún motivo caen en el mismo componente, la excepción self-lookup (`fragmentation.py:158-174`) tampoco lo cubre: exige que el lector (`Lookup Dim Producto`) tenga camino dirigido hacia **todo** writer, y no lo tiene hacia el loader dedicado (rama distinta) — cae a "revisar a mano", bloqueando el corte automático.

Ninguna rama de `compute_cut` deja esta versión blindada — relocaliza C1-bis en vez de resolverlo, tal como se identificó al revisar la decisión.

**Camino corregido — pasada previa, un único writer de `dim_producto`:** antes del loader, un step de anti-join contra `dim_producto` (SQL directo — `TableInput`/`ExecSQL` sin `table` propia en `cfg`, ya excluido de la matriz R/W por diseño, mismo trato que cualquier SQL arbitrario, D15) obtiene las claves naturales de `staging_ventas` que todavía no están en la dimensión. Esas filas (clave natural real + atributos default/"Pendiente" + `inferred_member='Y'`) se unen (`Union`) al stream real de `staging_productos`, y **ambos alimentan el mismo step único "Cargar Dim Producto"**. Resultado:
- `dim_producto` tiene exactamente un writer en todo el KTR — `len(writers)==1`, C1-bis no puede disparar para esa tabla, sin depender de ningún orden incidental.
- Solo dispara C1 (loader W, `Lookup Dim Producto` R) — el mismo split de siempre, ya validado contra `err1.ktr`/`err2.ktr`: loader antes que el hecho.
- El lookup del lado del hecho (`StreamLookup`) queda R puro — D16 satisfecho sin excepciones ni casos de borde. Como el loader ya garantiza (por construcción, antes de que el hecho corra) que toda clave natural de la venta está en `dim_producto`, ese lookup nunca debería fallar por match — no hace falta ningún patrón de filtro/insert del lado del hecho.

**Detección implementada 2026-07-24 (F4/D22) — la parte que el backend puede resolver determinísticamente.** `etl_generator.py`: `_dims_with_inferred_member(dwh_ddl, dim_contracts)` reusa `ddl_adapter.parse_ddl()` (mismo parser que `_dim_contracts_anomaly_warning`, cero parsing nuevo) para cruzar columnas `is_foreign_key AND constraints.required AND references` de `dwh_ddl` contra `dim_contracts[].table` — sin código de detección propio de FK que escribir, ya vivía en `CanonicalField`. Resultado inyectado en el prompt STG→DWH (`_build_prompt_from_inference`, único punto de armado, sin duplicación) como sección nueva `## DIMENSIONES CON MIEMBRO INFERIDO OBLIGATORIO`, hermana de `## CONTRATOS DE DIMENSION` — vacía y sin efecto en el caso común (ninguna FK NOT NULL hacia una dimensión del contrato). `_inferred_member_notifications()` agrega un warning accionable por dimensión afectada al registro de deltas (D13/D15), en los dos call sites (`generate_etl_from_inference`, `generate_etl_async`).

**Emisión del step (anti-join + Union) — resuelta como regla de prompt, no código backend.** Criterio de F4/D22 (ver esa decisión): sintetizar en Python un `TableInput` con SQL de anti-join + un `Union rows` + rewiring de hops es una síntesis de grafo desde cero — más riesgoso que lo que `enforce_dimension_step_policy` hace hoy (que solo corrige tipo/flags de un step YA existente, nunca inventa steps nuevos). El LLM ya arma el resto del grafo del KTR; describirle el patrón exacto (`system_etl.txt`, bloque "PATRÓN MIEMBRO INFERIDO" — anti-join `NOT EXISTS`/`LEFT JOIN`, atributos default + `inferred_member='Y'`, `Union` hacia el ÚNICO loader, checklist ítem 23) es consistente con cómo se resuelve todo el resto del contenido SQL/config (D12). **Red de seguridad sin trabajo nuevo:** si el LLM arma mal el patrón y deja un segundo writer real sobre la dimensión, `compute_cut()`/C1-bis (F2/F3, ya en producción) lo detecta igual que cualquier doble-escritor — separa en 2 KTR+KJB o emite `Validacion(tipo="error")` (D19/D20). No se escribió un validador nuevo para este caso: la fragmentación ya es el backstop.

Tests: `tests/test_inferred_member.py` (13 casos — detección con FK NOT NULL/nullable/fuera de contrato/dim_contracts vacío/DDL vacío/DDL inválido; formato de sección y notificaciones vacío-vs-poblado; contrato expuesto hacia el prompt en los 3 modos, incluida ausencia en `origen_stg`).

**Sigue sin cubrir, fuera de alcance de esta detección:**
- Confirmar que el loader dedicado de la dimensión (SCD1/upsert por clave natural) sobrescribe correctamente la fila placeholder cuando el producto real llega — depende de que ese loader sea upsert, no insert-only; verificar contra `scd_type` de cada dimensión en `dim_contracts`. Sin código nuevo identificado — a confirmar con una corrida real.
- No cubre dimensiones sin FK NOT NULL del lado del hecho (ej. `dim_tiempo`, ya tratada por V2/D15 como caso de integridad distinto, no de política de default).

*Por qué D21 y no una edición directa de C.6:* mismo patrón que D16→"resuelto"/D19→D20 — la pregunta se registró en `Abiertos` cuando apareció sin la información para cerrarla; esta sesión la cierra con datos concretos (la práctica de Kimball que trajo el usuario + la verificación contra el código ya shippeado). Se separa para que quede trazable qué se sabía en cada momento.

<a id="d22"></a>
### D22 — F4 arranca: "estrategia de fix" no es una elección única, se resuelve por ítem; triage completo, 3 gaps reales cerrados por prompt `[F4]`

**Contexto (2026-07-24):** F4 (`03-plan.md`) tenía como parte de su propio objetivo "decidir estrategia de fix (derivación determinista desde `dim_contracts` vs. parche de prompt)" — a diferencia de F2/F3/D16/D21, esa pregunta nunca se cerró con una regla. Arrancar F4 sin cerrarla primero significaba tocar código a ciegas en 8 frentes con naturaleza distinta (contenido SQL, código backend nuevo, verificación pendiente de ejecución, alcance sin definir).

**Resuelto — no es una sola estrategia, es un criterio de ruteo por ítem, ya implícito en cómo se resolvió todo lo anterior (D6 vs. D12):**
- Si el fix depende de información que YA vive determinística en el backend (`dim_contracts`, DDL parseado, grafo de hops) y previene un error estructural (race, doble escritor, violación de `NOT NULL`) → código backend, mismo patrón que D16/D21.
- Si el fix es contenido SQL/config que hoy arma el LLM dentro de lo que el catálogo permite (dialecto, patrón de dedup, elección de step por comportamiento de entorno) → prompt (`system_etl.txt`), reforzado por el checklist de verificación que ya existe ahí.

**Triage de los 8 ítems de intake de F4 (R4/R6/R8/R10/R12/H23/R5-b/R11) + los 6 puntos originales del handoff, contra el prompt real (no contra memoria):**

| Ítem | Resultado | Evidencia |
|---|---|---|
| R4 — default de `COALESCE` tipado igual que la columna | **Ya cubierto, cerrado sin cambio.** | `system_etl.txt` K17/checklist-20 ya exige literal del mismo tipo (string/numérico) al envolver en `COALESCE` — la regla ya existía antes de que F4 arrancara. |
| R6 — alinear tipos de clave en lookups contra el DDL | **Ya cubierto, cerrado sin cambio.** | `system_etl.txt` regla (e) + checklist-16 ya exigen `SelectValues.cast` explícito antes de cualquier `keys`/`stream_field` con tipo distinto entre capas. |
| R10 — `dim_tiempo` como calendario contiguo vía `generate_series` | **Ya cubierto, cerrado sin cambio.** | `system_etl.txt` K18 ya instruye el patrón completo (no cargar automáticamente, warning con `generate_series`, fila "unknown" sk=0, default en el `DBLookup`). |
| R8 — clave natural también como `value` (`update=N`) en `InsertUpdate` de dimensión | **Gap real, cerrado esta sesión (prompt).** Extiende H16. | Regla B16 + ejemplo + checklist-21 agregados a `system_etl.txt` (bloque `InsertUpdate`). |
| R12 — dedup de staging vía `DISTINCT ON (...) ORDER BY ... DESC` | **Gap real, cerrado esta sesión (prompt).** | K19 + checklist-22 agregados a `system_etl.txt`. |
| H23 — `DBLookup` falla introspección contra pooler de Supabase, preferir `StreamLookup` | **Gap real, cerrado esta sesión (prompt).** | Nota agregada junto al bloque `DBLookup` de `system_etl.txt`: preferir `StreamLookup` para la FK de una dimensión cargada por el mismo `ktr`; reservar `DBLookup` para tablas que este `ktr` no carga. |
| D12 (dialecto) — punto de notificación obligatorio | **Gap encontrado y cerrado de paso.** D12 exige notificar cuando se emite SQL dialecto-dependiente desde 2026-07-22, pero `system_etl.txt` no tenía ninguna regla pidiéndolo — verificado por grep, cero ocurrencias de "dialecto"/"Postgres" en el prompt antes de esta sesión. | K19 (nueva) fija Postgres como default, cross-referencia R4/R10 (ya cubiertos) + R12 (nuevo), y exige `validaciones` tipo `"info"` declarando la construcción dialecto-específica. |
| R5-b/R11 (D21) — anti-join + `Union` hacia el loader único (miembro inferido) | **No implementado — el ítem grande de F4.** Diseño ya cerrado por D21, pero es código backend nuevo (detectar FK NOT NULL de un hecho contra una dimensión desde `dwh_ddl`, emitir 3 steps + rewire), no una corrección de prompt ni de una línea. Requiere su propia sesión de diseño de implementación antes de tocar código — mismo criterio que exigió F2 antes de F3. | Sin código todavía — ver D21. |
| E3 (mapeo invertido `sk_producto`/`sk_tiempo`), key vacía en `CombinationLookup`, E14 (`Number` vs `BigNumber`) | **Desbloqueado y verificado 2026-07-25.** E3 no era bug de contenido del LLM — causa raíz real en `output.py` (`_step_InsertUpdate`/`_step_Update`, `<value><name>`/`<rename>` invertidos vs. formato real de Kettle), **corregida en código** + test de regresión, sin depender de ninguna corrida puntual. Key vacía — no reproducida en corrida fresca. E14 — **confirmado vivo**, queda como gap de prompt (contenido del LLM, no backend), mismo criterio de ruteo de esta decisión. | Ver H9, `01-hallazgos.md` (sección actualizada 2026-07-25). Test: `backend/tests_manual_llm/test_h9_h10_live_scenario.py` (manual, fuera de `tests/`, consume API — no correr en CI). |
| E1/E2 (SelectValues solo-cast no ejercitado, SCD2 declarado no ejercitado) | **Desbloqueado y verificado 2026-07-25.** Ambos ejercitados en corrida fresca (forzando `dim_producto` a `scd_type=2` sobre `categoria`) sin encontrar defecto asociado. | Ver H10, `01-hallazgos.md` (sección actualizada 2026-07-25). Mismo test que la fila de arriba. |
| Validador de contrato staging→DWH | **Alcance cerrado 2026-07-25 — ver D23.** No implementado todavía. | — |

**Consecuencia sobre el plan:** F4 pasa a "EN CURSO" — 3 gaps reales cerrados (R8, R12, H23) + 1 gap transversal cerrado (D12/K19), 3 ítems confirmados ya resueltos antes de esta sesión (R4, R6, R10) sin necesidad de tocarlos. **Actualizado 2026-07-25:** E3/key-vacía/E1/E2 verificados con corrida fresca — E3 tenía causa raíz real de código (`output.py`), ya corregida; key vacía no reprodujo; E1/E2 quedaron ejercitados sin defecto. E14 recibió regla de prompt (B17, `system_etl.txt` — checklist ítem 25) + `MONEY_FIELD_HINTS` extendido en `error_catalog_checks.py` para que el checker automático alcance el mismo vocabulario que la regla — **queda en debe: la regla NO se re-verificó con una corrida real todavía** (la corrida que confirmó E14 vivo fue ANTES de agregar B17). Validador de contrato con alcance cerrado mas no implementado (D23). Queda abierto, bloqueado por diseño pendiente: R5-b/R11 (necesita sesión de diseño de implementación, sin cambios esta sesión).

**B17 no implica retrabajo de fases anteriores:** es contenido de prompt puro (mismo ruteo que R8/R12/H23 arriba — "contenido SQL/config que arma el LLM dentro de lo que el catálogo permite → prompt"), no toca fragmentación (F1-F3), `compute_cut()`, derivación de `dim_contracts` ni ninguna estructura de backend. El fix de E3 (`output.py`) y la extensión de `MONEY_FIELD_HINTS` tampoco — son correcciones de builder/checker aisladas, sin relación con las fases de corte.

**Deuda técnica nueva registrada por el cierre de E14 — H27/H28 (`01-hallazgos.md`):** B17 asume, sin verificar contra código/documentación real de Kettle, que (a) los operandos de un `Calculator`/`Formula` deben ser todos `BigNumber` para que el resultado sea confiable (H27 — inferencia de punto flotante general, no confirmada contra el motor real), y (b) que `FIELD_TYPE_SOURCES` (`error_catalog_checks.py`) es el catálogo completo y correcto de steps que declaran `type`/`value_type` por campo (H28 — ya se encontró un hueco concreto: `Constant` no está incluido pese a tener el mismo shape que steps que sí lo están). Ninguno de los dos bloquea B17 tal como quedó escrito (la regla es conservadora, no genera falsos negativos conocidos) — quedan como investigación pendiente, no como fix urgente.

*Por qué D22 y no una fila más en `03-plan.md`:* fija el criterio de ruteo que la fila de F4 dejaba como pregunta abierta ("decidir estrategia de fix") — nivel de decisión de scope, mismo motivo que D14/D16/D20.

<a id="d23"></a>
### D23 — Alcance del validador de contrato entre KTR (writer→reader); cierra el ítem "sin definir" de D22 `[F4]`

**Contexto:** D22 (fila "Validador de contrato staging→DWH") dejó el ítem sin `archivo:línea` ni alcance propio — la frase venía del objetivo original de F4 en `03-plan.md`, sin que ninguna sesión anterior precisara qué compara exactamente. Esta sesión lo cierra.

**Resuelto (2026-07-25):**

1. **Qué compara.** No usa `stg_definition`/`dwh_model` (lo que el usuario declaró) como tercera fuente de verdad. Compara las dos salidas reales del LLM entre sí: lo que el KTR escritor realmente produce sobre una tabla vs. lo que el KTR lector realmente espera leer de esa misma tabla. Corre por cada relación escritor→lector real entre los `.ktr` generados — si hubo fragmentación (F2/F3), no queda atado al par legacy KTR_1/KTR_2: se adapta a N archivos, una comparación por cada arista escritor→lector del grafo de corte.

2. **Qué necesita cada lado — no simétrico.** El KTR productor (ej. Origen→STG) no necesita el DDL del lado que no escribe (DWH) para su parte de la validación; el KTR consumidor (ej. STG→DWH) sí necesita el DDL del lado que lee, además de lo que el productor realmente escribió. Extiende — no reemplaza — K15/checklist-3c (`fields_validate.py`) y V1-V6 (`ddl_validation.py`/`prompt_validacion_src.txt`): esas validaciones existentes se adaptan para correr por-KTR-generado, reusando su lógica en vez de reimplementarla.

3. **Qué valida, mínimo.** Columnas + nombres + tipos entre lo que un KTR escribe y lo que el siguiente lee. NO valida que las reglas de negocio (`business_rules`) se hayan aplicado — hoy nada en el pipeline valida eso: `business_rules` solo entra como texto libre al prompt de `structure_inferrer.py` (líneas 81/135) para dar forma a `stg_ddl`/`dwh_ddl`/`dim_contracts` en el momento de inferir; ningún validador post-generación comprueba que un step implemente efectivamente una regla de negocio. Gap real, distinto, no cerrado por esta decisión.

   **Punto de enganche creado 2026-07-25** (sin implementación real todavía): `validate_business_rules()` (`backend/app/services/validate_business_rules.py`) — stub deliberado, pase libre siempre (lista vacía). Wireado en `etl_generator.py::generate_etl_from_inference`, una llamada por etapa (KTR_1 contra `stg_definition`, KTR_2 contra `dwh_ddl`), ambas contra `reglasNegocio` y los steps ya generados de esa etapa. El enganche existe para que la lógica real se sume después sin tener que volver a decidir dónde ni con qué firma se llama — implementarla sigue siendo trabajo futuro, no de esta sesión.

4. **Severidad — D15 uniforme, sin caso especial.** Todo mismatch detectado (desde un campo puntual con tipo distinto hasta una tabla STG completa sin productor real) se anota como `Validacion` tipo="error"/severidad máxima, mismo canal que V1/V2/K15 ya usan. El `.ktr`/`.kjb` se emite siempre — nunca se bloquea la emisión por esto, tampoco en el caso de corte totalmente descosido. Elegido explícitamente por el usuario en vez de abrir una categoría de bloqueo nueva: consistente con el patrón ya establecido, sin precedente de excepción en el código hoy.

**Consecuencia sobre el plan:** cierra el ítem pendiente de la fila "Validador de contrato staging→DWH" en D22. Diseño de alcance cerrado — implementación no escrita todavía, queda como trabajo de F4.

*Por qué D23 y no una fila más en `03-plan.md`:* mismo criterio que D14/D16/D20/D22 — fija scope que una sesión anterior dejó abierto, antes de tocar código.

<a id="d24"></a>
### D24 — Track A retomada; A0 (inventario) ejecutada `[Track A]`

**Contexto (2026-07-25):** `03-plan.md` tenía a Track A pospuesta desde 2026-07-22, con la condición "se retoma cuando Track F esté suficientemente asentado" — sin criterio numérico, juicio a tomar en el momento.

**Decisión:** Track F llegó a ese punto — F1, C.2, F1.5, F2, F2.5 y F5 cerrados; F3 con el algoritmo de corte y el wiring de servicio cerrados y probados end-to-end (D19/D20), solo pendiente el consumo de frontend (D20-punto5, sesión aparte); F4 con triage completo de los 8 ítems de intake y 3 gaps reales cerrados (D22). Lo que queda abierto de Track F (frontend F3, emisión de miembro inferido R5-b/R11, implementación del validador de contrato de D23, y los 9 residuales de `04-deuda-abierta.md`) es trabajo de código aislado y ortogonal a un inventario de arquitectura — sin conflicto de tocar los mismos archivos en la misma sesión, y `04-deuda-abierta.md` ya deja explícito que ninguno de esos residuales bloquea seguir con las fases.

**Ejecutado:** A0 (Fase 0 — inventario), prompt `fase-0-inventario.md` (`Contexto Cambios/Arquitectura/`). Salida en `docs/auditoria/00-inventario.md` — árbol de directorios de `backend/app/`, tabla de endpoints con cadena de llamadas, recorrido completo del flujo de un step (incluida la lista exhaustiva de las 35 call-sites que leen/parsean/mutan `config`, sección 3.3), fuentes de datos externas, estructuras de datos que representan un step o su config (6 representaciones distintas coexistiendo, hallazgo central), e inventario de tests con sus dependencias externas. Sin modificación de código, según manda la fase.

*Consecuencia sobre el plan:* A0.5 (censo de fallos silenciosos) queda desbloqueada — depende solo de A0 (`03-plan.md`).

*Por qué D24 y no solo una nota en `03-plan.md`:* mismo criterio que D16/D19/D20/D22/D23 — la condición de reanudación era un juicio pendiente sin fecha ni dato; esta sesión lo cierra con la evidencia concreta de qué estado tenía Track F al momento de decidirlo.

<a id="d25"></a>
### D25 — A0.5 (censo de fallos silenciosos) ejecutada; hallazgo derivado (H29) toca Track F, no solo Track A `[Track A]`

**Ejecutado (2026-07-25):** A0.5 (Fase 0.5 — censo de fallos silenciosos), sin prompt propio en `Contexto Cambios/Arquitectura/` (no existe ese archivo — confirmado por búsqueda en el repo y en `Escritorio`; alcance definido en esta sesión contra la doctrina ya vigente: D5, D15, D9/D13, R11 de `arquitectura-objetivo.md:70`). Salida en `docs/auditoria/00b-fallos-silenciosos.md` — grep sistemático de `except`/`continue` sobre `backend/app/` (114 + ~60 ocurrencias), clasificado en silencio total / logueado-sin-canal-de-usuario / notificado-correctamente, cruzado contra `01-hallazgos.md` para no reabrir H6/H12/H26. Sin modificación de código, según manda la fase.

**Resultado más relevante — no es un hallazgo de Track A, es uno de Track F, en la pieza más nueva del propio refactor.** `services/ktr_builder/fragmentation.py` (escrito 2026-07-24 para resolver races/dobles-escritores, F3) tiene en su propia función central (`build_rw_matrix()`) el mismo defecto de fondo que motivó H6: un step puede volverse invisible para la matriz R/W sin dejar rastro — por una vía distinta a la que H6 cerró (acá el `config` sí parsea; el campo `table` específicamente viene vacío). Contradice el propio docstring del módulo, que promete notificación (D15) para ese caso y no la implementa. Mismo gap duplicado, de forma independiente, en `dimension_step_policy.py` y `fields_validate.py` — los tres módulos reaccionan cada uno por su cuenta ante "tabla no resuelta", sin avisar. Catalogado como **H29** en `01-hallazgos.md` — detalle completo ahí, no repetido acá.

**Por qué se registra acá como decisión y no solo como hallazgo:** a diferencia de H24-H28 (triage de tests, hallazgos aislados), H29 nace directamente de una fase de Track A (A0.5) pero su remedio cae en Track F (mismo mecanismo de `notifications` que ya usa `compute_cut()`, mismo archivo que F3 todavía tiene abierto por el pendiente de frontend, D20-punto5). Se dejaría fuera de foco si solo viviera como una entrada más de hallazgos — esta decisión fija que **no bloquea F3** (D15 ya cubre "genera y notifica" como comportamiento por defecto; lo que falta es que ese "notifica" se cumpla en este caso puntual) y que no tiene dueño de track asignado todavía — a decidir junto con el resto de lo pendiente de F3.

*Por qué D25 y no solo una entrada de hallazgo:* mismo criterio que D24 — deja explícito que A0.5 se ejecutó, y evita que el cruce Track A → Track F de H29 quede implícito solo en el hallazgo.

<a id="d26"></a>
### D26 — Suite roja no es "ruido aceptado": marcar known failures (xfail strict) + adelantar en chico un test de arquitectura ejecutable + separar tests por naturaleza `[Fundamento]`

**Contexto (2026-07-27):** revisión del plan fuera de esta sesión (el usuario, con otra sesión de Claude) encontró un hueco en D13. D13 exige "dos tests verdes" para cerrar cualquier fase, pero la suite tiene una base de **45 fallos ya identificados y explicados** (D20: 2 en `test_ktr_xml_validator.py`/`test_structured_outputs.py`, 6 en `test_ktr_build_job_api.py` — H24 —, 37 en `test_api.py` por requerir servidor real en `localhost:8000`) que nadie marca como tal en el código — viven como texto explicativo en `02-decisiones.md`/`01-hallazgos.md`, no como estado ejecutable. Mientras esos 45 sigan rojos sin distinguirse del resto, una regresión nueva se esconde entre ellos. **Ya pasó una vez:** D19/D20 registra que conectar el corte de verdad encontró 2 bugs reales — invisibles mientras `compute_cut()` solo notificaba en vez de ejecutar — prueba de que "sabemos por qué estos tests fallan" no protege nada si el rojo no se distingue del rojo nuevo.

**Decisión, en tres partes:**

**1. Known failures marcados explícitos en el código, no solo documentados en prosa.**
- Los 6 de `test_ktr_build_job_api.py` (H24, bug real y confirmado: `ConnectionsMapRequest` más estricto que `resolve_real_connections()`) y los 2 de `test_ktr_xml_validator.py`/`test_structured_outputs.py` (D20: "2 bugs no relacionados", sin H-number propio todavía — asignar uno al aplicar esto) se marcan `@pytest.mark.xfail(reason="H24", strict=True)` (o el H-number que corresponda). `strict=True` es la pieza que importa: si el test empieza a pasar sin que nadie haya tocado el fix, xfail-strict falla — fuerza a actualizar la decisión en vez de dejar un xfail obsoleto mintiendo sobre el estado real.
- Los 37 de `test_api.py` **no son la misma categoría** — no son bug conocido, son "requiere un servidor HTTP real que CI no levanta". Marcarlos `xfail` sería incorrecto (xfail dice "código roto, se va a arreglar"; esto dice "entorno que este runner no tiene"). Reusar el patrón que ya existe en el repo: `@pytest.mark.integration` (ya usado en `test_structured_outputs.py` para llamadas reales al LLM, ver `00-inventario.md` sección 6) o un skip condicional equivalente, excluido de la corrida default de CI.
- Resultado: suite en CI queda verde (pass + xfail esperado + skip documentado). Cualquier rojo nuevo, en cualquier archivo, es señal real — no hay que releer 45 explicaciones para saber si algo cambió.
- Costo estimado por el usuario: una sesión. Protege D13 en todas las fases que quedan (Track A completo, F3 frontend, F4 validador de contrato).

**2. Test de arquitectura ejecutable — versión aplicable HOY, acotada; no la versión completa de Track A.**
- El pedido original ("20 líneas de pytest que caminan los imports y fallan si `domain`/`services` importan `infrastructure`") es literalmente **R1** de `arquitectura-objetivo.md:50` ("Ningún módulo de `domain` o `services` importa `infrastructure`. La conexión se hace por `ports` + inyección"), doctrina de Track A sobre la estructura de capas objetivo (`api/schemas/services/domain/ports/infrastructure/core`). Esa estructura **no existe en el código actual** — `CLAUDE.md` ya lo dice explícito: "No aplicada todavía — nada del código actual respeta esta estructura de carpetas". Un test que camine `domain/` y `infrastructure/` no tiene qué caminar todavía; escribirlo ahora sería un test que pasa trivialmente por ausencia de sujeto, falso verde.
- **Lo que sí es ejecutable hoy, contra la estructura real** (`backend/app/routers|services|models|schemas|core`, ver estructura en `CLAUDE.md`): la versión reducida de **R3** (`arquitectura-objetivo.md:54`, "el service no importa `fastapi`. Si necesita fallar, lanza una excepción de dominio; `core` la traduce a HTTP") — chequeo AST/import estático: ningún módulo bajo `app/services/` importa `fastapi` ni `app.routers.*`. Es la pieza de R3 ya implícita en cómo están escritos D19/D20/D22/D23 (servicios devuelven `Validacion`/warnings, nunca `HTTPException`), pero sin señal automática que la sostenga si alguien la rompe sin querer.
- **R1/R4 completos (`domain`/`infrastructure`/`ports`, no saltear capas) quedan atados a cuando Track A ejecute la migración de estructura de carpetas (A7-PASO1)** — no se adelantan acá, sería inventar carpetas vacías solo para que el test tenga contra qué correr. Cuando A7 mueva código a esa estructura, este test se reemplaza/extiende, no se duplica.
- Convierte R3 (chico) de doctrina a señal automática ahora, sin esperar a A2 (Track A, "Cumplimiento por capas", no iniciada) — pero no reemplaza A2: A2 sigue siendo el audit completo y manual contra las 7 capas objetivo cuando Track A la ejecute. Esto es un adelanto parcial y barato, no un sustituto.

**3. Tests separados por naturaleza, para que "dónde vive un test" sea obvio sin abrir el archivo.**
- Hoy `backend/tests/` tiene 34 archivos `test_*.py` planos, sin `conftest.py`, sin agrupación (`00-inventario.md` sección 6 ya los clasificó por dependencia externa: HTTP-real / LLM-real-cuota / SQLite-en-memoria / unitarios-mock / filesystem-real / ZIP-mockeado — la taxonomía ya existe en prosa, no en la estructura de carpetas).
- El test de arquitectura (punto 2) y los known-failures marcados (punto 1) necesitan vivir en un lugar predecible, no sumarse como archivo 35 sin criterio.
- **Alcance de esta decisión:** fija el criterio de separación (la taxonomía que `00-inventario.md` ya usa: `unit/` mock-only, `integration/` DB-real o servidor-real, `manual/` — ya existe como `backend/tests_manual_llm/`, fuera de la colección de `pytest.ini` —), y que el test nuevo de arquitectura entra como archivo propio nombrado por lo que hace (`test_architecture_boundaries.py`), no mezclado en un archivo existente. **No decide todavía** si los 34 archivos existentes se mueven a esa estructura de subcarpetas — mover 34 archivos con imports relativos y sin `conftest.py` es trabajo de código con riesgo de romper la colección de `pytest.ini` sin necesidad, y no es lo que esta sesión de revisión de plan pidió resolver. Migrar los 34 queda como tarea aparte, candidata natural a Track A (A2/A3, que ya tocan bordes de test) o a una fase de testing propia si el usuario la quiere antes.

**Consecuencia sobre D13 (`02-decisiones.md`) y el "Requisito transversal — D13" de `03-plan.md`:** "dos tests verdes" ahora presupone una suite donde verde es informativo — D13 no se reescribe, se apoya en que D26 exista. Ninguna fase que cierre de acá en adelante puede apoyarse en "ya sabíamos que esos fallan" sin que el fallo esté marcado por el mecanismo de punto 1.

**No implementado todavía — solo decidido.** El usuario eligió cerrar el diseño primero (ver pregunta de esta sesión); código (marcar los 8 xfail/integration, escribir `test_architecture_boundaries.py`, mover el nuevo test a su carpeta) queda para una sesión de implementación aparte, con Track F o Track A activo en paralelo sin conflicto — es trabajo de test, no toca `backend/app/`.

*Por qué D26 y no una fila más en `03-plan.md`:* mismo criterio que D14/D16/D20/D22/D23/D24/D25 — fija un criterio de scope (qué es "verde" para D13, qué versión de R1/R3 corre antes de Track A) que quedaba implícito y a punto de discutirse dos veces.

---

### D27 — Split `registry.py` en `step_types.py`(domain)/`step_emitters.py`(infra); `KNOWN_PDI_STEP_TYPES` borrado, no movido; `CanonicalType`/`FieldFormat`/`ColumnRole` a `domain/`; criterio "vocabulario PDI es dominio" `[Track A]`

**Contexto (2026-07-27):** intercambio de dos sesiones fuera de esta conversación (`Contexto Cambios/deicsion-arq-refacto.md` → análisis → `Contexto Cambios/prompt-a-code-cierre.md` → decisión), aplicado en esta sesión. Punto de partida: la sesión de arquitectura previa (D26 parte 2, `arquitectura-objetivo.md` mapa E1) había etiquetado `registry.py` como "partido" (mitad `domain`, mitad `infrastructure/pentaho`) sin ejecutar el corte. Este intercambio decidió el corte real, verificó contra código (no contra hipótesis) y lo ejecutó.

**Decisión, en cinco partes:**

**1. `registry.py` se parte en dos módulos, dentro de `services/ktr_builder/` (sin mover a una carpeta `domain/` física para esta parte — ver punto 3 para la excepción).**
- `step_types.py` (domain): `STEP_TYPE_ALIASES` (identidad de tipo) + `_CRITICAL_FIELDS` (completitud mínima — gate real en `build.py:194-219`, `raise KtrBuilderError`). Cero imports de proyecto, verificado.
- `step_emitters.py` (infra): imports de `steps/*` + `STEP_BUILDERS` (tipo canónico → función XML) + `STEP_CONFIG_KEYS`/`unmapped_config_keys` — **reclasificados a infra en este mismo cierre** (sesión de arquitectura previa los había puesto en domain; verificado que auditan capacidad presente del builder — "qué claves SÍ mapea a XML" — no un invariante de dominio).
- Migración en 4 pasos, cada uno con suite verde: (a) `registry.py` como shim de reexport mientras se actualizan consumidores, (b) `build.py`/`__init__.py`/`repair.py`/`validate.py` apuntan a los módulos nuevos, (c) los 4 tests que importaban `.registry` directo (`test_dimension_step_policy.py`, `test_fragmentation.py`, `test_fragmentation_wiring.py`, `test_ktr_integrity_repair.py`) se actualizan, (d) shim borrado. Verificado con grep antes de borrar: cero consumidores restantes.
- Consecuencia real cerrada, no solo relocada: `validate.py` (domain) importaba `STEP_TYPE_ALIASES` de `registry.py` (etiquetado infra) — excepción congelada en `test_architecture_layers.py::FROZEN_R1`. Tras el split, `validate.py` importa `step_types.py` (domain→domain) — `FROZEN_R1` queda vacío (ver punto 4).

**2. `KNOWN_PDI_STEP_TYPES` se borra. No se traslada a `step_types.py` ni a ningún lado.**
- Verificado por grep exhaustivo: cero consumidores en todo el repo fuera de `registry.py` y su reexport en `__init__.py`. El gate real contra un `type` sin builder es `STEP_BUILDERS.get(canonical_type) is None → raise KtrBuilderError` (`build.py:347-351`), que no consulta la whitelist. El mecanismo que el docstring de la whitelist describía (degradar a `Dummy`) tampoco existe en el código — `contracts.py:1-3` lo lista como uno de los defectos que ese módulo fue escrito para cerrar. Ver **H30**.
- El conocimiento que la whitelist pretendía capturar (coherencia entre lo que `system_etl.txt` promete al LLM y lo que el paquete puede construir) se re-expresa como `backend/tests/test_pdi_step_coherence.py` — tres direcciones verificadas por separado (prompt→builder, bloqueante, hoy vacía; alias→builder y builder→prompt, informativas, listas congeladas — ver **H31**/**H32**). Reemplaza documentación-sin-verificar por test ejecutado.
- Lectura de `system_etl.txt` desde el test: sin tocar el archivo (es el system prompt real, cualquier marcador se lo mandaríamos al modelo). Se usa la estructura de párrafos que ya tiene (línea en blanco antes/después del bloque de nombres), con un assert de forma (`regex` de identifier) que falla explícito si la prosa se cuela adentro del bloque — no un parser que se rompe en silencio.

**3. `CanonicalType`, `FieldFormat`, `ColumnRole` se mueven a `backend/app/domain/canonical_types.py` — primer archivo físico de la capa `domain/` en este repo.**
- Los tres son value objects puros de stdlib (`str, Enum` / `Literal`), verificado leyendo `schemas/canonical.py` completo — cero dependencia de Pydantic.
- `schemas/canonical.py` los reexporta con **excepción nombrada por símbolo, no por paquete** (mismo criterio que ya regía la dirección opuesta, domain→schemas): la fachada existe para no romper a los 16 consumidores existentes de `from app.schemas.canonical import CanonicalType`, no para que código nuevo la use — código de dominio nuevo importa `domain/canonical_types.py` directo.
- Asimetría explícita sobre por qué esto no es "ampliar la regla" de forma insegura: la propiedad que sostiene la doctrina es que `domain` sea hoja (no dependa de nada del proyecto), no que `schemas` lo sea — `schemas/` importando un `Enum` de stdlib desde `domain/` no compromete esa propiedad.
- `backend/tests/test_architecture_layers.py::DOMAIN_MODULES` gana `domain.canonical_types` y `services.ktr_builder.step_types`; documentado en comentario junto al set el motivo por el que un módulo de dominio futuro no puede colarse por la fachada de `schemas/canonical.py` sin que el test lo marque (nada de lo que hay en `DOMAIN_MODULES` es `schemas.*`, y ningún par de `FROZEN_R1` nombra `schemas.canonical` de forma genérica).

**4. `type_mappings.py` se reclasifica de `domain/` a `infrastructure/db_inspection/`.**
- Verificado: único consumidor real de `map_sql_type()` es `db_adapter.py` (otro adaptador); su input documentado (`type_mappings.py:4`) es `db_connector._format_type()`. Traduce vocabulario de un vendor concreto (Postgres/SQL Server) — es la definición de adaptador, no dominio, aunque sea código puro.
- Import actualizado: `type_mappings.py` pasa a importar `CanonicalType`/`FieldFormat` directo de `domain/canonical_types.py` (no a través de la fachada de `schemas/`) — infra puede importar todo, sin necesidad de pasar por la fachada pensada para no romper compatibilidad.
- `FROZEN_R1` pierde el par `("services.type_mappings", "schemas.canonical")` — no se relocaliza, se resuelve: `type_mappings.py` nunca estuvo en `DOMAIN_MODULES` (era una imprecisión del mapa anterior, no una excepción activa en el test R1), y ahora tampoco importa `schemas.canonical` en absoluto.

**5. Criterio nuevo, explicitado por escrito (faltaba, quedaba implícito): "el dominio de esta aplicación es la generación de KTR."**
- Vocabulario/reglas de PDI (`STEP_TYPE_ALIASES`, `_CRITICAL_FIELDS`, `STEP_CONTRACTS`) son dominio — son ciertos independientemente de qué DB origen o qué proveedor de LLM esté detrás. Lo que traduce desde un sistema externo *distinto de PDI* (BD origen vía `type_mappings.py`, proveedor de LLM vía `models/*_llm.py`) es infraestructura. Dentro de PDI: vocabulario y reglas son dominio, formato de serialización a XML es infraestructura.
- Resuelve la aparente inconsistencia entre `STEP_TYPE_ALIASES` (domain, "traduce" nombres display de Spoon) y `type_mappings.py` (infra, "traduce" tipos SQL de vendor) — misma forma superficial, conclusión distinta, correcta bajo este criterio.
- Documentado en `CLAUDE.md` junto a la regla marco direccional ("¿al importar este módulo en un intérprete limpio se carga algo que hable con el mundo exterior?" — el "solo stdlib" de la tabla de Capas es un proxy conservador de esa regla, no la regla misma; cuando difieren, gana la regla real, documentada como excepción razonada, nunca como ampliación silenciosa).
- Consecuencia registrada, no resuelta: parte de `STEP_TYPE_ALIASES` no son nombres reales de Spoon sino patrones de alucinación conocidos del modelo (`AddConstants`, `SystemInfo`, `CSVInput`) — conocimiento de infra (comportamiento del LLM) mezclado en un símbolo de dominio. No se separa ahora (no vale la complejidad); es el criterio para partirlo si el archivo sigue creciendo por ese lado.

**Verificación:** suite completa verde en cada uno de los 3 checkpoints de la migración (antes/durante/después del split), sin ningún cambio de comportamiento observable de `build_ktr()` — refactor puro, confirmado corriendo la suite contra el HEAD anterior a los cambios (mismos 8 fallos preexistentes, no relacionados, en ambos). Tests nuevos: `test_pdi_step_coherence.py` (3), `test_architecture_layers.py` actualizado (sin regresión).

**Sesión de origen:** análisis en dos turnos (`deicsion-arq-refacto.md`, `prompt-a-code-cierre.md`) + ejecución en esta sesión, 2026-07-27.

**Estado:** ejecutado. `H30` cerrado; `H31`/`H32` quedan abiertos (inofensivos, registrados). `D26` parte 2 queda parcialmente ampliada por este split (el test de arquitectura que D26 adelantó ahora cubre también `step_types.py`/`domain/canonical_types.py`).

<a id="d28"></a>
### D28 — D20-punto5 cerrado: frontend consume `etapas`/`kjb_master`; linaje recalculado se borra; datos viejos se rechazan explícitos; `EtapaOutput` gana `nombre`; Superset fuera de alcance `[F3]`

**Contexto (2026-07-27):** D20 cerró el diseño y el backend del contrato N-ario (`etapas`/`kjb_master`) en 2026-07-24, dejando explícitamente D20-punto5 (frontend) para una sesión aparte. Al retomarla, 4 preguntas no estaban decididas en ningún D anterior — se resuelven acá.

**1. Linaje — se borra el recálculo del front, no se generaliza el endpoint.** El backend ya manda `result.lineage` calculado N-ario (`stitch_lineage_many`, `etl_generator.py:658`/`:552`) en toda respuesta de generación. El único consumidor del recálculo del lado front, `frontend/src/api/lineage.js` → `POST /api/ai/lineage-from-ktr`, seguía cableado a exactamente 2 XML (`_KtrXmlBody`, `routers/ai.py:403-420`) y no tenía variante N-aria — `stitch_lineage_many_from_xml` nunca existió. Generalizar ese endpoint hubiera sido trabajo de contrato HTTP extra para un camino que el front no necesita (el backend ya entrega el linaje resuelto). Se borra `api/lineage.js` y el `useEffect` de recálculo en `EtlDetail.jsx`. El endpoint `/api/ai/lineage-from-ktr` **queda en el backend sin consumidores en este repo** — no se borra (fuera de alcance de esta sesión, podría tener otro consumidor futuro), pero se anota en `04-verificacion.md`.

**2. Datos viejos (shape sin `etapas`) — rechazo explícito, sin shim de traducción.** Antes de esta sesión, un `result` en el shape viejo (`ktr_xml`/`ktr2_xml`/`kjb_xml`) producía fallos silenciosos: botón de descarga ausente sin explicación, items de menú deshabilitados sin tooltip, ZIP que nunca se generaba. Coherente con D4/D20-punto2 (sin período de convivencia) y con la doctrina de A0.5/D25 (fallos silenciosos son la clase de bug que este refactor existe para eliminar), se decide **no** escribir un traductor viejo→nuevo — sería reintroducir la convivencia que D20-punto2 descartó — sino detectar el shape viejo explícitamente y mostrar un mensaje accionable ("generado con un formato anterior, regenerar"). Aplica tanto a ETLs ya persistidos en la DB como a archivos `etl_full` exportados e importados de vuelta.

**3. `EtapaOutput` gana el campo `nombre: str`.** D20-punto4 especificó que los KTR de una etapa partida van "en una carpeta nombrada por esa etapa/sub-job", pero el schema (`etl_schemas.py:77-89`) nunca expuso ese nombre — el backend lo conoce internamente (las etiquetas `"origen_stg"`/`"stg_dwh"`/`"proceso"` que ya usa `_build_job_plan`, `etl_generator.py:646`) pero lo descartaba al construir la respuesta. Se agrega el campo en vez de que el frontend infiera el nombre de carpeta por índice (acoplaría UI a un orden implícito) o del filename del `.kjb` (acoplaría a una convención de nomenclatura ajena).

**4. Superset queda fuera de alcance del proyecto — ya no se lo considera al tocar el flujo de generación de ETL.** No se modifica `superset_client/`, `superset_export/` ni `utils/supersetExport.js`. Se corrigen únicamente los gates rotos que dependían del shape viejo (`EtlDetail.jsx` tenía su bloque de UI de Superset ya comentado desde antes de esta sesión — se terminó de retirar el código muerto asociado, `canExportSuperset`/`handleExportSuperset`/`supersetBusy`/el import; `EtlCardMenu.jsx` tenía el item **activo** gateado por `ktr_xml` — se corrigió el gate a `supersetBusy`, sin quitar la función, porque el pedido fue sacar la dependencia rota, no retirar la feature).

**Implementación (esta sesión):**
- Backend: `nombre` en `EtapaOutput` (`etl_schemas.py`), poblado en `_etapa_output()`/`etl_generator.py`. Único cambio de backend de esta sesión.
- Frontend: módulo nuevo `frontend/src/utils/etlArtifacts.js` (`readEtlArtifacts`/`buildZipEntries`) — único punto de lectura de `result.etapas`/`kjb_master` o del shape viejo; normaliza a 3 estados (`ok`/`legacy`/`none`) con mensaje accionable en los dos últimos. Migrados sobre este módulo: `etlCardActions.js`, `EtlDetail.jsx`, `EtlCardMenu.jsx`, `etlImport.js` (rechazo en el import). Nueva sección "Archivos generados" en `ResultView.jsx` para el caso de etapa partida.
- Tests (D13): infraestructura de test de frontend inexistente hasta esta sesión — se agregó vitest (`frontend/package.json`, script `test`), sin jsdom/testing-library (los dos tests exigidos apuntan al módulo puro). `etlArtifacts.test.js`: 12 casos, con fixtures espejo de `backend/tests/test_etl_generate_response_shape.py` para que el test del front falle si el backend cambia el shape.

**Verificación:** `pytest backend/tests/test_etl_generate_response_shape.py` (5/5) + suite completa sin regresión (mismos 8 fallos preexistentes de D20/D26, cero nuevos). `npm run test` (12/12), `npm run lint` (sin errores nuevos en archivos tocados), `npm run build` limpio.

**Estado:** ejecutado. **F3 cierra** con esta sesión — ver `ESTADO.md`.

<a id="d29"></a>
### D29 — Progreso observable del job async: bitácora persistida + polling existente, no SSE `[F4]`

**Contexto (2026-07-27):** el pedido del usuario es ver progreso real durante `generate_etl_async` (5+ llamadas
al LLM, minutos de duración) — hoy solo hay "Esperando respuesta" y al final "completo"/"error", incluidos los
reintentos con backoff en 429/503 que hoy solo se ven en la terminal del backend. Ninguna D anterior decide esto
(verificado por grep sobre este archivo).

**Decisión:** el canal es el `GET /{job_id}/status` que el frontend ya polea cada 1.2 s
(`CreateETL.jsx:367-401`) — no el endpoint SSE `/generate-from-inference/stream` (`ai.py:283-349`), que existe
en el repo pero no tiene ningún consumidor en el frontend hoy y se corta con un F5. El progreso se persiste en
una columna nueva `progress_json` en `ktr_build_jobs` (dict `{next_seq, truncated, events[]}`), escrita por un
único módulo, `services/job_progress.py`, con sesión de DB propia y corta — nunca por la sesión larga de
`generate_etl_async` (evita clobber entre columnas). `ProgressEvent` trae `seq/ts/stage/code/level/message`, con
`code` de vocabulario cerrado (documentado en el módulo, no texto libre) para poder assertarlo en tests. Tope de
120 eventos / 240 caracteres por mensaje.

Los reintentos del modelo (`gemini_llm.py:131-135`, `anthropic_llm.py:120-124`) se capturan **sin tocar esos dos
archivos**: un `logging.Handler` con whitelist de 3 loggers (`app.models.gemini_llm`, `app.models.anthropic_llm`,
`app.services.ktr_builder.repair`), ruteado por un `contextvars.ContextVar` que `generate_etl_async` setea al
arrancar. `ddl_validation` queda fuera de la whitelist — su información (cambios aplicados, conflictos) ya sale
por los eventos explícitos `ddl.audit.started`/`.done` que `generate_etl_async` emite alrededor de la llamada a
`validate_and_correct_ddl`; interceptar también su logger hubiera duplicado la misma información por dos
caminos. Verificado antes de decidir: `gemini_llm.py:109` corre el backoff dentro de `asyncio.to_thread`, que
copia el `contextvars.Context` al worker thread — el retry sincrónico de Gemini queda cubierto igual, sin
bloquear el event loop (no era el riesgo que parecía). El handler nunca reenvía `record.getMessage()` crudo del
proveedor (puede traer fragmentos de prompt); arma el mensaje en español a mano matcheando el template exacto de
`record.msg` (no su render con `args`) contra un vocabulario cerrado, y lleva su propio `PasswordFilter` — ver
el hallazgo nuevo sobre por qué no alcanza con el filtro del logger root.

**Por qué no SSE:** ya existe una implementación (`_KtrLogHandler`, `ai.py:57-67`) y nadie la usa. Adoptarla
ahora agrega un segundo canal a mantener, no sobrevive un refresh de página, y no deja historial — el usuario
que vuelve a `REVIEW` tras un fallo pierde lo que pasó. El polling ya resuelve las tres cosas gratis.

**Estado:** diseño cerrado, implementación en curso en esta misma sesión.

<a id="d30"></a>
### D30 — Checkpoint por etapa de la salida del modelo; tensión con D3 resuelta a favor del checkpoint `[F4]`

**Contexto:** `generate_etl_async` hace las dos llamadas al modelo (origen→STG, STG→DWH) bajo un solo `try` con
un único commit al final (`etl_generator.py:1095-1177`, antes de esta sesión). Si la segunda falla, el `except`
descarta también la primera — el usuario reintenta desde cero y vuelve a pagar tokens y tiempo de una etapa que
ya había salido bien.

**Decisión:** commitear `raw_data_1` (con sus warnings y el `dwh_ddl` post-auditoría) apenas la etapa 1 termina
sus tres pasos (llamada + repair + integrity), con `model_status` todavía en `pending` — `_try_build` no se
dispara con un checkpoint parcial porque exige `model_status == done`. Si la etapa 2 falla, el `except` hace
**merge** sobre `model_json` en vez de reemplazo, así que `raw_data_1` sobrevive. Esto exige reordenar
`generate_etl_async` de "por operación" (las dos llamadas, después las dos normalizaciones, después los dos
repairs...) a "pipeline por etapa" — se declara acá como reordenamiento intencional, no como refactor incidental
colado en el mismo commit.

**Tensión con D3** ("los datos guardados son descartables, regenerar desde datos base es preferible"): D3 asume
que regenerar es barato. Acá no lo es — `origen_stg` cuesta tokens y minutos reales, y el dato base (el DDL) no
cambió entre el primer intento y el reintento. El checkpoint no viola el espíritu de D3: sigue siendo
descartable (muere con el TTL de 30 min del job, no se promueve a ninguna tabla nueva ni tiene backfill,
no persiste nada que sobreviva al job). Lo que cambia es *cuándo* se descarta — no en el primer error de la
etapa siguiente, sino cuando el job expira.

**Trampa documentada:** `enforce_dimension_step_policy` muta `data_2` in-place *después* del checkpoint de la
etapa 2 (el comentario ya existente en `etl_generator.py:1149-1151` lo advertía antes de esta sesión). El commit
final reescribe `raw_data_2` con la versión post-policy — el checkpoint 2 y el `model_json` final pueden diferir
en ese campo, y eso es correcto.

**Estado:** diseño cerrado, implementación en curso en esta misma sesión.

<a id="d31"></a>
### D31 — Reanudación de la etapa 2 sin endpoint ni estado servidor nuevos `[F4]`

**Decisión:** `ETLFromInferenceRequest` gana un campo opcional `reuse_stage_1: dict | None`. Si el cliente lo
manda, `generate_etl_async` saltea la llamada al modelo de origen→STG y sus dos repairs, y arranca directo en la
auditoría de DDL + etapa 2 (`validate_and_correct_ddl` **no** se saltea: su `dwh_ddl` alimenta `prompt_2`,
`_required_columns_from_ddl` y `ddl_conflictos` — se ahorran 3 llamadas de 5, no todas). Corre igual
`normalize_step_configs` sobre el dato reusado como red defensiva barata (determinística, sin LLM), porque puede
venir de un archivo importado por el usuario — misma superficie de confianza que `build-from-raw`, que ya acepta
salida de modelo desde el cliente.

**Alternativas descartadas:**
- **`POST /{job_id}/resume` server-side**, persistiendo el request original: pierde contra el TTL de 30 min del
  job (`_JOB_TTL_MINUTES`, `ai.py:159`) — el usuario que revisa el fallo en el drawer y decide reintentar puede
  tardar más que eso, y en ese momento el job ya no existe. Además persiste una superficie de entrada nueva sin
  necesidad, en tensión con D3.
- **Persistir el request completo en la fila:** mismo problema de D3, sin ganar nada sobre reenviar el payload
  que el propio `/status` ya le entregó al cliente.

Los tokens de la etapa reusada no se cuentan en `MetadataResponse`; se emite una advertencia (`stage.reused`)
que lo dice explícito, para que el total de tokens mostrado no read como "toda la generación costó esto" cuando
en realidad una etapa no se pagó de nuevo.

**Estado:** diseño cerrado, implementación en curso en esta misma sesión.

<a id="d32"></a>
### D32 — Contrato del status extendido: `raw_llm_data` inmutable, lo parcial va en `stages` `[F4]`

**Motivo técnico, no solo de estilo:** `build_etl_from_raw` (`etl_generator.py:758`, verificado antes de
decidir) discrimina el shape con `if "ktr_1" in raw_llm_data and "ktr_2" in raw_llm_data` — chequeo de
**presencia de clave**, no de valor. Si `/status` devolviera `{"ktr_1": {...}, "ktr_2": null}` (natural si se
quisiera exponer ahí mismo el checkpoint parcial de D30), ese dict entra en la rama y explota con
`TypeError: 'NoneType' object is not subscriptable`, que sube como 500 genérico.

**Decisión:** `raw_llm_data` no cambia de forma ni de condición de aparición respecto de antes de esta sesión
(`{ktr_1, ktr_2}` completo, o `None` — misma regla de `ai.py:205-209`). Lo parcial viaja en un campo **nuevo y
separado**, `stages: List[StageRawInfo]`, con `nombre` en el vocabulario canónico de **D28**
(`origen_stg`/`stg_dwh`). Ningún consumidor existente mira `stages` — `build_etl_from_raw`,
`POST /api/etls/{id}/connections`, `_finishEtl → form_data.rawLlmData` y el envelope `etl_llm_raw` de
`etlExport`/`etlImport` quedan sin tocar.

`stages[].data` se puebla **solo en estado terminal** del job (`build_status in (built, failed)` o
`model_status == failed`) — con `POLL_INTERVAL_MS = 1200` y payloads de cientos de KB, mandarlo en cada tick del
polling activo serían del orden de 10 MB por generación.

**Estado:** diseño cerrado, implementación en curso en esta misma sesión.

<a id="d33"></a>
### D33 — Superficie de acceso a las respuestas del modelo: botón de header + drawer, dos acciones distintas `[F4]`

**Contexto:** hoy el acceso a la respuesta cruda guardada es un banner y un botón pegados al textarea de
correcciones (`InferenceReview.jsx:108-127` y `:149-158`, antes de esta sesión), sin distinguir de qué etapa es
cada cosa, y con una sola acción ("Reutilizar respuesta") que solo tiene sentido cuando las dos etapas están
completas.

**Decisión:** botón en el header de `InferenceReview` (`Respuestas del modelo · N/2`) que abre un drawer lateral
— mismo patrón que `BusinessRulesDrawer` (`components/BussinesRules/BusinessRules.jsx`) — con una tarjeta por
etapa. El banner y el botón viejos se borran; el bloque de corrección queda solo con el textarea y "Aplicar
corrección".

El drawer expone **dos acciones distintas, no una deshabilitada**, porque son operaciones semánticamente
distintas (D31 las separó del lado del backend): con las dos etapas completas, "Reutilizar ambas y armar el
.ktr" no llama al modelo (`build-from-raw`); con solo `origen_stg`, "Reintentar reusando Origen → STG" sí llama
al modelo (DDL + etapa 2, vía `reuse_stage_1`). Colapsarlas en un solo botón con `disabled` habría escondido
justo la funcionalidad pedida — reintentar sin perder lo que ya se generó.

**Estado:** diseño cerrado, implementación en curso en esta misma sesión.

<a id="d34"></a>
### D34 — D15 ejecutado para conexiones: conexión sin resolver ya no aborta el build; `conn_origen` acepta metadata inline `[F3]`

**Contexto:** un ETL con origen por CSV/Excel/DDL/formulario (sin `connection_id` de una `Connection` guardada)
tumbaba el build entero al final, ya con el modelo respondido bien: `KtrXmlValidationError` — *"Conexión
'conn_origen': quedó sin resolver... no se puede entregar un .ktr final"*. Dos causas encadenadas, reportadas por
el usuario en sesión:

1. `conn_origen` nunca se preguntaba — se auto-derivaba (`CreateETL.jsx:_deriveOrigenConnectionId`) solo si
   TODAS las tablas de origen compartían un `connection_id`; si no, quedaba `null` y la clave nunca viajaba en
   `connections_map`. El formulario que sí aparece durante el procesamiento (`DestinationConnections.jsx`) solo
   pedía staging/DWH.
2. `ktr_xml_validator._check_generic_connections` metía la conexión placeholder en la misma lista de `issues`
   fatales que un `GENERIC` sin driver o un hop huérfano — línea 291 (arriba, D15) ya nombraba este `raise`
   exacto como el comportamiento que D15 retira, alcance F3, pendiente en `03b-reportes.md`. Esta D lo ejecuta
   para el caso de conexiones.

**Decisión:**

- **`validate_ktr_xml(strict_connections=True)` ya no aborta por conexión sin resolver.** Pasa de `-> None` a
  `-> list[str]`: la conexión con host/database placeholder sale como warning (mensaje accionable: qué capa, qué
  completar en Spoon), no como `issue`. `GENERIC` sin `CUSTOM_DRIVER_CLASS`/`CUSTOM_URL`, step vacío y hop
  huérfano **siguen fatales** — eso abre roto en Spoon, no hay nada que "completar" ahí. Alcance acotado a
  propósito: D15 completo (los otros dos chequeos) queda sin ejecutar, decisión explícita para no ampliar el
  cambio más allá de lo pedido.
- **`missing_layer_warnings()` nuevo** (`ktr_builder/connection.py`) cubre el caso que `resolve_real_connections`
  no cubría: una capa (`conn_origen`/`conn_staging`/`conn_dwh`) que ni siquiera llegó en `connections_map` — la
  causa raíz de este bug puntual. `_try_build` (`etl_generator.py`) y el rebuild (`routers/etl.py`) lo usan tras
  `resolve_real_connections`, y emiten cada warning como evento de progreso `build.connection_unresolved` /
  `level="warning"` (visible en la pantalla de generación sin cambios de frontend — `progressLog.js` nunca
  desvanece `warning`/`error`) además de sumarlo a `advertencias_buenas_practicas` (canal ya existente, D13).
- **`ConnectionsMapRequest.conn_origen` pasa a `Union[str, InlineConnection]`** (antes `Optional[str]`).
  `resolve_real_connections` ya resolvía la rama dict de forma genérica por nombre lógico — no hizo falta tocar
  el service. Frontend: `DestinationConnections.jsx` gana una sección "Conexión de Origen" (checkbox "Completar
  en Spoon" + `DestinationConnectionForm`, igual que staging/DWH) que solo se muestra cuando
  `_deriveOrigenConnectionId()` devuelve `null`; si devuelve un id, sigue sin preguntarse. `ConnectionView.jsx`
  (EtlDetail) gana el mismo patrón para editar el origen de un ETL ya generado — antes era texto fijo.
- **`conn_staging`/`conn_dwh` NO ganan la rama string** (aceptar `connection_id` reusado ahí) — eso es H24/C.7
  (`01-hallazgos.md:433-441`, `02-decisiones.md` § C.7), decisión de producto aparte, no tocada acá.

**Estado:** ejecutado, implementación en esta misma sesión. `docs/refactor/03b-reportes.md` pendiente
correspondiente marcado como parcialmente cerrado (conexiones sí; `SystemInfo`/hop huérfano del validator,
resto de D15, siguen sin ejecutar).

<a id="d35"></a>
### D35 — El mapa de conexiones es por-ETL y se aplica en todo camino de build; `conn_origen` derivado se valida antes de usarse `[F3]`

**Contexto:** usuario reportó que un ETL recién generado salió con **todas** las conexiones (staging y DWH,
completadas a mano en el formulario, misma base para ambas) en `type=GENERIC`/`PLACEHOLDER_HOST`/`port=0` — tuvo
que reescribir todo en Spoon. Diagnóstico verificado con lectura read-only contra la DB real (no hipótesis):

1. `form_data.connectionsMap` del ETL estaba bien guardado (`db_type`, host, port, database, username completos
   para staging y DWH).
2. `resolve_real_connections()` sobre ese mismo mapa, en replay directo, resuelve perfecto — `type: POSTGRESQL`
   + metadata real. El backend de resolución (D34) no tiene el bug.
3. El `.ktr` guardado no tenía ni un warning de conexión ni `dwh_ddl` — dos marcas que `_try_build()` siempre
   deja. El resultado no lo construyó `_try_build()`: se construyó por **"Reutilizar respuesta del modelo"**
   (`handleReuseResponse` → `POST /api/v1/etl/build-from-raw`), camino que **nunca tuvo campo de conexiones** —
   `BuildFromRawRequest` no lo tenía, `build_etl_from_raw()` no lo aceptaba, y el frontend hacía
   `setJobId(null)` explícito, lo que ocultaba el panel de `DestinationConnections` por completo.

<a id="d36"></a>
### D36 — H27/H28 cerrados con evidencia real (código fuente de Kettle + auditoría del universo real de steps); B17 reescrita, `FIELD_TYPE_SOURCES` gana 6 entradas nuevas además de `Constant` `[F4]`

**Contexto:** H27 y H28 (`01-hallazgos.md`, sesión 2026-07-25) dejaron dos puntos de la regla B17 (`system_etl.txt`, campos monetarios mal tipados en Kettle, catálogo E14/`v11_monetario_sin_bignumber`) sin verificar contra fuente real — escritos por inferencia. El usuario aportó, en esta sesión, un documento con investigación externa contra `pentaho/pentaho-kettle` (GitHub, branch `master`) que responde ambos puntos con archivo:línea real. Regla del proyecto respetada: no se copió código del documento a ciegas — se contrastó cada afirmación contra el estado actual de `system_etl.txt`/`error_catalog_checks.py`/`steps/*.py` antes de aplicar nada (ver H35/H36 para el detalle verificado).

**Decisión:**

- **B17 (`system_etl.txt`) reescrita**, no solo confirmada. La conclusión práctica no cambia — "todos los operandos y la salida en `BigNumber`" seguía siendo la regla segura — pero la explicación del mecanismo estaba mal: el texto viejo atribuía la misma causa ("el cálculo pierde precisión en la operación misma") a `Calculator` y a `Formula` por igual. Verificado que son mecanismos distintos: en `Calculator` el tipo de la operación lo fija el primer operando (`field_a`, vía `switch(metaA.getType())` en `ValueDataUtil.java`) — asimétrico, depende del orden; en `Formula` el cálculo ya se hace en `BigDecimal` sin importar el orden (motor libformula), y la fuga está en el `value_type` de salida y en campos de origen ya `Number` (garbage-in). Se agregó además una nota nueva, sin código E asignado: `Calculator` con `DIVIDE` en `BigNumber` sin `value_precision` puede lanzar `ArithmeticException` en runtime (`MathContext.UNLIMITED` por defecto en divisiones no exactas).
- **`FIELD_TYPE_SOURCES` (`error_catalog_checks.py`) gana 7 entradas** (`Constant` — ya conocida desde H28 — más `FieldSplitter`, `Denormaliser`, `RegexEval`, `DBLookup`, `StreamLookup`, `DataValidator`), encontradas auditando los `steps/*.py` reales de este proyecto, no la lista de Kettle completo que traía el documento del usuario (la mayoría de sus ~24 steps sugeridos — User Defined Java Class, LDAP/YAML/SAP/etc. — no existen en `STEP_BUILDERS` de este proyecto; auditarlos habría sido trabajo sin efecto). El criterio de inclusión/exclusión (qué es un value-type real de Kettle vs. otro vocabulario bajo el mismo nombre de tag — `GroupBy`/`AnalyticQuery`/`FilterRows`/`GetSystemInfo`/`DimensionLookup` punch-through quedan afuera a propósito) quedó documentado como comentario en el propio archivo, al lado de la tupla, para que la próxima sesión no vuelva a investigar lo mismo.
- **Alcance de "exhaustividad" redefinido**: ya no es "cubrir Kettle completo" (pregunta sin límite natural, la razón de que H28(b) quedara abierta) sino "cubrir `STEP_BUILDERS` de este proyecto" (~45 entradas, `step_emitters.py:88-149`), que sí es una lista cerrada y verificable. Riesgo residual aceptado explícitamente: si `STEP_BUILDERS` gana un step nuevo con value-type por campo, `FIELD_TYPE_SOURCES` no lo detecta solo — hace falta una auditoría manual nueva, no hay mecanismo automático que los mantenga sincronizados. No se decide acá cerrar ese riesgo (ej. un test de coherencia como `test_pdi_step_coherence.py` pero para `FIELD_TYPE_SOURCES` vs. `STEP_BUILDERS`) — queda como candidato a hallazgo futuro si se justifica.
- Verificado con los tests existentes (`test_error_catalog_checks.py` 13/13, `test_pdi_step_coherence.py` 3/3) que el cambio no rompió nada — no se agregaron tests nuevos para las 7 entradas (fuera de alcance de esta sesión, que fue verificación + corrección de documentación/prompt/catálogo, no una tarea de cobertura de tests).

**Estado:** ejecutado, esta misma sesión (2026-07-28). Cierra H27/H28 vía H35/H36.

Causa independiente, misma sesión: `origenTables[].connection_id` de ese ETL apuntaba a un UUID que ya no existe
en `connections` — `resolve_real_connections` ya avisaba ("no encontrada", D34), pero el frontend **ocultaba**
el formulario de origen apenas derivaba un id, sin verificar que resolviera, dejando el origen sin forma de
corregirse desde ninguna pantalla.

**Decisión:**
- `ConnectionsMapRequest`/`InlineConnection` se mueven antes de `BuildFromRawRequest` en `etl_schemas.py` (sin
  cambio de forma) para que `BuildFromRawRequest` gane un campo opcional `connections_map`. `build_etl_from_raw()`
  gana `real_connections`/`connection_warnings` y los propaga a `_build_response_from_two_ktr_data`/
  `_build_response_from_data` con `strict_connections=bool(real_connections)` — mismo criterio que `_try_build`
  (D34): revisa placeholder sin resolver, nunca aborta. `_build_response_from_data` (flujo monolítico legacy)
  gana el parámetro `strict_connections` que no tenía. `POST /api/v1/etl/build-from-raw` resuelve el mapa con
  el mismo par `resolve_real_connections` + `missing_layer_warnings` que ya usan `_try_build` y
  `POST /api/etls/{id}/connections` — reusado, no reescrito.
- Frontend (`CreateETL.jsx`): `handleReuseResponse` ahora pide conexiones (mismo panel `DestinationConnections`,
  gate de render `jobId || pendingRebuild`) si todavía no se decidieron en la sesión (`connectionsDecidedRef`);
  si ya se decidieron, reconstruye directo con `connectionsMapRef.current`. `handleFinalizeConnections` despacha
  a `submitJobConnections` (con `jobId`) o a `buildFromRaw` (con `pendingRebuild === "raw"`).
- `_deriveOrigenConnectionId()` ya no se usa cruda: `_resolveOrigenConnection()` la verifica contra
  `listConnections()` antes de escribirla en `connectionsMapRef.current.conn_origen` — un id que no resuelve
  (o que la verificación no pudo confirmar) cae a `null`, lo que hace que `DestinationConnections` muestre el
  formulario inline en vez de darlo por bueno en silencio. Mismo criterio en `ConnectionView.jsx` (ETL ya
  generado): `origenIsSavedId` ya no confía ciegamente en el string guardado, lo valida en un efecto y cae al
  formulario editable si no resuelve — es lo que permite reparar un ETL ya generado sin regenerarlo (ese
  endpoint ya resolvía bien, solo faltaba poder reemplazar el id muerto).

**No se crean filas `Connection` reusables para staging/DWH** — sigue valiendo D34/decisión original: no son
conexiones reusables, es la metadata de destino de *ese* ETL puntual.

**Fuera de alcance, registrado:** el prompt (`system_etl.txt` K7) permite al modelo declarar una sola conexión
cuando dos capas comparten base — si lo hace, la capa colapsada no recibe metadata (el match es por nombre
lógico declarado). No se reprodujo en esta sesión; no se toca el prompt acá.

**Estado:** ejecutado, implementación en esta misma sesión.

<a id="d37"></a>
### D37 — Criterio determinista de SCD1 vs SCD2: pre-check en `domain/scd.py` + criterio escrito en `system_inference.txt`

**Contexto:** el usuario reportó errores recurrentes en la decisión SCD1/SCD2, con la expectativa de que ya existiera un criterio claro. No existía. `system_inference.txt` mencionaba SCD nueve veces, pero todas eran consecuencias de un `scd_type` ya elegido (contrato DDL D4, índice D3, `fecha_fin` NULLABLE I6) — ninguna decía **cuándo** elegir 1 vs 2. Lo único que le llegaba al modelo sobre el significado era la descripción del JSON Schema (`inference_output.py`): define *qué es* cada valor, nunca *cuándo* corresponde. El único texto con criterio real del repo vivía en `promptfoo/prompts/inference.yaml` — una copia congelada que no corre.

Esto no es una omisión menor: un `scd_type` mal elegido no queda como advertencia, destruye trabajo correcto río abajo. `dimension_step_policy.py::enforce_dimension_step_policy` hace downgrade `DimensionLookup`→`CombinationLookup` **reescribiendo el config entero**, tirando `fields`/`date_from`/`date_to` — historización legítima borrada en silencio (H9, "así se perdió esa vez").

**No hay una fuente autorizada que el prompt estuviera omitiendo por descuido.** Ni Pentaho tiene criterio propio: adopta Kimball y delega. Su única prescripción propia es negativa y sobre volatilidad de *esquema*, no de datos:

> "Introducing changes to the dimensional model in Type 2 could be very expensive database operation so it is not recommended to use it in dimensions where a new attribute could be added in the future." — Pentaho Academy, *SCDs* [F1]

Ver H37 para el hallazgo completo.

**Decisión — dos decisiones distintas que se trataban como una sola:**

| | Decisión | Dueño | Estado antes de D37 |
|---|---|---|---|
| A | `scd_type` (0/1/2) por dimensión | LLM, etapa inferencia | sin criterio escrito |
| B | Qué step PDI la implementa | Backend, `derive_dimension_step_type` (D11) | ya resuelto |

D37 ataca A sin tocar B. SCD2 vs SCD1 es un requisito de negocio ("¿un reporte del pasado debe mostrar el atributo como era entonces?"), no una propiedad derivable de datos crudos — el backend no puede inventar esa intención sola (D6: "la línea divisoria es dónde ya vive la información"). Lo que sí puede es descartar los casos donde SCD2 es mecánicamente imposible o ya está declarado por evidencia estructural, y acotar el residuo de juicio de negocio — mismo patrón que D16/D21 (backend acota, el modelo decide el resto y justifica).

**Qué se construyó:**

1. **`backend/app/domain/scd.py`** (nuevo, capa `domain`, solo stdlib — R1): `classify_scd_candidates()` con precedencia fija:
   - **Regla 0** — sin clave natural durable *confirmada* → `NO_HISTORY_POSSIBLE`, forzado a 1. Mecánica de la herramienta, no criterio de modelado: *"Both the prior and new rows contain as attributes the natural key (or another durable identifier)"* [F1]. **Vinculante incluso sobre una declaración explícita del usuario.**
   - **Regla 1** — sin atributos mutables (todo lo no-clave es la propia clave) → `NO_HISTORY_POSSIBLE`, forzado a 1.
   - **Regla 2** — dimensión de calendario (nombre + única clave de tipo fecha) → `NO_HISTORY_POSSIBLE`, forzado a **0** (Type 0 de Kimball, "Design Tip #152": atributo fijo).
   - **Regla 3** — intención declarada explícitamente (`TableSemantics.dwh_intent.scd_type`, forma ya reservada en `canonical.py`, hoy sin lógica) → `HISTORY_DECLARED` si pide 2.
   - **Regla 3-bis** — el propio origen ya trae columnas de historial (`valid_from`/`fecha_desde`/`current_flag`/`version`/...) → `HISTORY_DECLARED`. D6 puro: la información ya vive en el origen, es lectura, no inferencia. Respaldo: *"Also 'effective date' and 'current indicator' columns are used in this method"* [F1].
   - Resto → `UNDECIDED`, con `scd2_candidates` (atributos mutables ni casi-únicos por fila ni constantes — proxy de churn, declarado como tal) como techo de lo que el modelo puede versionar.
   - `derive_dimension_step_type()` (la pieza de D11) se **movió** acá desde `dimension_step_policy.py`, que la reexporta — vocabulario SCD compartido entre inferencia y KTR, R7.

2. **Corrección de alcance, decidida antes de escribir código** (ver `respuesta-code-scd-d37.md` del usuario, revisión externa con fuentes citables): `business_rules`/`process_goal` son texto de **proyecto**; el veredicto de `classify_scd_candidates` es **por entidad**. Si la señal de prosa alimentara directamente el veredicto por entidad, una sola aparición de "histórico" inclinaría *toda* dimensión del modelo hacia SCD2 — y "histórico" es de las palabras más sobrecargadas del dominio ("carga histórica de 5 años" es volumen de hechos, no versionado de un atributo). Por eso `detect_history_intent()` devuelve un `ProjectHistorySignal` separado, de alcance de proyecto, y el prompt instruye al modelo a decidir a qué dimensión específica aplica — nunca a todas por default. Ese residuo de asignación es exactamente el juicio que le corresponde al modelo bajo D16/D21.

3. **Bug encontrado durante la verificación end-to-end, no en el diseño:** la regla 0, tal como se implementó primero, leía `key_columns=[]` (sin metadata de PK/UNIQUE) como "confirmado que no hay clave". Pero Formulario/CSV/Excel (el camino más común) **nunca** declaran esa metadata — solo BD (`db_adapter`) y DDL (`ddl_adapter`) la resuelven de verdad. Sin distinguir "confirmado sin clave" de "no se sabe", la regla 0 forzaba `scd_type=1` en casi cualquier ETL armado a mano. Se encontró porque `test_refine_untouched_dimension_preserves_dim_contracts` (real, contra LLM) empezó a fallar: el modelo, correctamente instruido por el nuevo criterio, degradó un `dim_contract` legítimo `scd_type=2` a 1 con `"CONTRATO MODIFICADO"` porque el fixture de la prueba usa entrada tipo Formulario. Fix: `classify_scd_candidates` gana `key_columns_trusted: bool`, `True` solo cuando todos los campos de la tabla tienen `inferred_by` en `{"database", "ddl"}`; con `False`, la regla 0 se salta y el veredicto cae a `UNDECIDED` sin forzar nada. Registrado acá porque es la clase de error que D37 mismo previene en el resto del sistema — un default determinista que confunde "sin evidencia" con "evidencia de ausencia".

4. **`scd_rationale`** — nuevo campo en `DimContract` (default `""`, no rompe contratos ya persistidos) y **required** en `INFERENCE_OUTPUT_SCHEMA`: la razón del `scd_type` elegido queda como artefacto persistido, no prosa suelta (R12 — la razón es entidad de dominio).

5. **`attributes_scd1`/`attributes_scd2` ahora llegan al prompt de ETL** (`etl_generator._format_dim_contracts`) — se le exigían al LLM de inferencia y llegaban al validador de DDL, pero la fase que arma los steps nunca los veía. El juicio "qué atributos versionan" se calculaba y se tiraba.

**Limitación registrada, no arreglada — la forma binaria es provisoria.** `attributes_scd1`/`attributes_scd2` es binario; el step de Pentaho es **ternario por campo**: `Insert` / `Update` (Type 1) / `Punch through` —

> "**Punch through:** [...] instead of only updating the matched dimension row, it will update all versions of the row in a Type II slowly changing dimension." — Pentaho Academy, *SCDs* [F1]

— y mezclarlos está soportado explícitamente ("If you mix Insert, Punch Through and Update options in this step, this algorithm acts like a Hybrid Slowly Changing Dimension" [F1]). `punch_through` es cómo se corrige un error en un atributo de una dimensión **ya historizada** — el uso propio de Type 1 según Pentaho. Con la forma binaria ese caso no tiene cómo expresarse. Se registra ahora porque el punto 5 de arriba es el que hace que estos campos empiecen a alimentar generación real de steps — el momento en que la forma binaria deja de ser decorativa. No bloquea (el binario es un subconjunto válido) pero no se cierra en silencio.

**Por qué D37 y no ampliar D11:** D11 fijó que el **step** se deriva de `scd_type` — asumía que `scd_type` ya estaba decidido. D37 fija de dónde sale `scd_type`, que D11 daba por dado. Son capas distintas de la misma cadena de decisión; ampliar D11 habría mezclado "cómo deriva el step" con "cómo se elige el tipo", que es exactamente la confusión que motivó esta sesión.

**Verificado:** `backend/tests/test_scd_policy.py` (nuevo, puro/sin LLM/sin DB) cubre las 5 reglas + `key_columns_trusted` + `detect_history_intent` como señal de proyecto (nunca veredicto por entidad). `test_architecture_layers.py` verde con `domain.scd` en `DOMAIN_MODULES`, `FROZEN_R1` sin crecer. Suite completa corrida contra el repo real (no solo unitarios): la única regresión real que apareció fue el bug de `key_columns_trusted` de arriba, encontrada y cerrada en la misma sesión — el resto de las fallas preexistentes (`test_api.py` sin servidor vivo, `test_ktr_build_job_api.py`, `test_ktr_xml_validator.py::test_build_ktr_get_system_info_without_fields_gets_default_field`, `test_etl_schema_validates_minimal`) se confirmaron independientes de este cambio vía `git stash` antes/después.

**Estado:** ejecutado, esta misma sesión (2026-07-28).

**Fuentes** (citas textuales, verificadas — no juicio propio):

| ID | Documento | URL |
|---|---|---|
| F1 | Pentaho Academy — *SCDs* (Dimension Lookup/Update, workshop oficial) | https://academy.pentaho.com/pentaho-data-integration/data-integration/data-sources/databases/scds/scds |
| F2 | Kimball Group — *Slowly Changing Dimensions* (Type 1, Ralph Kimball, 2008) | https://www.kimballgroup.com/2008/08/slowly-changing-dimensions/ |
| F3 | Kimball Group — *Design Tip #152: Slowly Changing Dimension Types 0, 4, 5, 6, 7* | https://www.kimballgroup.com/2013/02/design-tip-152-slowly-changing-dimension-types-0-4-5-6-7/ |

Default SCD1 respaldado por F2: *"most data warehouses start out with Type 1 as the default"*. Excepción incorporada al prompt: F2 marca el único caso donde SCD1 está prohibido, no solo desaconsejado — *"In financial reporting environments with month end close processes and in any environment subject to regulatory or legal compliance, Type 1 changes may be outlawed. In these cases, the Type 2 technique must be used."*

<a id="d38"></a>
### D38 — Validador de contrato entre KTR (D23) implementado: nombres, tipos como gap documentado `[F4]`

**Contexto:** D23 cerró el alcance (qué compara, qué no, severidad) sin código. Esta sesión lo implementó.

**Decisiones tomadas durante la implementación, no cubiertas por D23:**

1. **Fuente de aristas escritor→lector: `build_rw_matrix()` (`fragmentation.py`), no `stitch_lineage_many()`.** `stitch_lineage_many` (usada para el diagrama de linaje) solo matchea `TableOutput`/`TableInput` terminales — un lector vía `DBLookup`/`DimensionLookup` no-terminal le es invisible. `build_rw_matrix` ya clasifica ese universo más amplio (mismo que usa `validate_dimension_lookup_races`). El matching de linaje se extrajo igual a `_resolve_table_endpoints()` (`lineage_builder.py`) por si otro caller lo necesita — `stitch_lineage_many` lo reusa sin cambio de comportamiento (33 tests de regresión verdes antes de tocar nada más).

2. **Bug encontrado en `build_rw_matrix()` durante la implementación, corregido localmente (no en `fragmentation.py`):** no resuelve tabla para `TableInput` con SQL crudo — mira únicamente `cfg["table"]`, vacío para un `TableInput` (el nombre vive en `cfg["sql"]`). Es el caso de lectura más común del pipeline (KTR_2 leyendo STG vía `SELECT * FROM stg_x`); sin el fix, el validador nunca disparaba en el caso típico (confirmado con un test end-to-end que daba 0 en vez de 1 antes del fix). Corregido en `contract_validate.py::_per_file_table_roles()`, reusando el regex que ya usa `lineage_builder._extract_table` — no se tocó `build_rw_matrix` ni `fragmentation.py` porque esa matriz también alimenta `compute_cut()` (F3): ampliarla ahí habría cambiado decisiones de corte, fuera de alcance de D23.

3. **Alcance entregado — nombres, no tipos.** D23 punto 3 pedía "columnas + nombres + tipos". Se entregan columnas NOT NULL sin default (DDL) vs. columnas de tabla realmente escritas (`column_name`/`table_field` del config del step, no del stream — distinto de lo que ya usa `contracts.py::consumes`, que es intra-archivo y del lado stream). Tipos quedan sin implementar: un step escritor no declara tipo propio, y el único tipo "real" del lado escritor requeriría inferencia de expresión cross-file (fuera de `contracts.py` por diseño). Implementarlo iguala al chequeo DDL-vs-DDL que ya hace `etl_generator._type_mismatch_warnings()` — que D23 punto 1 excluye explícitamente como fuente de verdad de este validador (compara declarado contra declarado, no lo que el KTR realmente produjo). Gap documentado en el docstring de `contract_validate.py`, no simulado.

4. **Cobertura de extracción de columnas escritas — 3 tipos de step, no todos los que build_rw_matrix marca "W".** `TableOutput`/`InsertUpdate`/`Update` tienen shape de config conocido y mapeado (`_WRITER_TABLE_FIELD_SOURCES`). `DimensionLookup`/`CombinationLookup` (también W/RW en `build_rw_matrix`) tienen shape de atributos de dimensión distinto, no mapeado — un archivo cuya única escritura a una tabla sea por esos dos steps no se valida por nombre (conservador: `_table_columns_written` devuelve `None`, el validador salta esa arista sin falso positivo).

**Qué se construyó:**
- `lineage_builder.py`: `_resolve_table_endpoints()` extraído de `stitch_lineage_many` (fase 1, sin cambio de comportamiento). Import de `STEP_TYPE_ALIASES` corregido de `app.services.ktr_builder` (paquete) a `app.services.ktr_builder.step_types` (submódulo) — el paquete import causaba ciclo contra `contract_validate.py`, que ahora se re-exporta desde `ktr_builder/__init__.py`.
- `services/ktr_builder/contract_validate.py` (nuevo): `validate_ktr_contracts()` + helpers, ver puntos 1-4 arriba.
- `etl_generator.py`: wireado en el mismo punto que `type_warnings`/`dim_contract_warnings` (los dos ya presentes en ambos flujos) — sync (`generate_etl_from_inference`) y async (`generate_etl_async`, checkpoint de etapa `stg_dwh`). `_split_integrity_warnings()` extendido para reconocer `CONTRACT_PREFIX` y promover a `Validacion(tipo="error", campo="contrato_ktr")` — mismo canal de severidad que `FIELD_INTEGRITY_PREFIX` (D15/D23 punto 4), campo distinto para no confundir en la UI un gap cross-archivo con uno intra-archivo.

**Verificado (D13):** `backend/tests/test_contract_validate.py` — 2 tests del validador en sí (detecta el hueco incluso leído por `DBLookup`, no falsea cuando todo está escrito) + 1 test end-to-end HTTP (LLM mockeado) confirmando que el mismatch llega a `ETLGenerateResponse.validaciones` como `tipo="error"`/`campo="contrato_ktr"`. Suite completa corrida antes/después (`git stash`): 8 fallos preexistentes confirmados independientes de este cambio (los 6 de `test_ktr_build_job_api.py`, H24/D26; los 2 de `test_ktr_xml_validator.py`/`test_structured_outputs.py`, D20/D26) — cero regresión nueva, 580 tests verdes incluidos los 3 nuevos.

**Estado:** ejecutado, esta misma sesión (2026-07-28).

<a id="d39"></a>
### D39 — `validate_business_rules()` (D23) removido: responsabilidad se traslada a DDL + futura herramienta Data Validator (PDI) `[F4]`

**Contexto:** D23 punto 3 dejó un segundo enganche, distinto del validador de contrato (cerrado por D38): `validate_business_rules()` — stub, pase libre siempre, wireado 2x en `etl_generator.py` (una llamada por etapa, KTR_1 contra `stg_definition`, KTR_2 contra `dwh_ddl`), pendiente de lógica real que comparara `business_rules` (texto libre del usuario) contra los steps ya generados (`config`, fórmulas, filtros).

**Decisión (2026-07-28), tomada por el usuario tras investigación propia:** validar reglas de negocio inspeccionando steps/config de un `.ktr` ya generado es mala práctica — el KTR es la salida serializada, no el lugar donde una regla de negocio debería hacerse cumplir. El enganche se remueve sin reemplazo equivalente dentro del backend:

- `backend/app/services/validate_business_rules.py` — borrado (era stub puro, cero lógica real que preservar).
- `etl_generator.py` — desenganchado: import, las 2 llamadas (`business_rule_warnings`) y su inclusión en `extra_warnings` de `generate_etl_from_inference`. Sin equivalente en el flujo async (`generate_etl_async`) — nunca estuvo wireado ahí, no había nada que sacar.
- `backend/tests/test_architecture_layers.py` — entrada `"services.validate_business_rules"` sacada de `DOMAIN_MODULES` (módulo ya no existe).
- Referencias a `validate_business_rules.py` en `backend/app/services/README.md` y `docs/arquitectura-objetivo.md` corregidas (eran mapa de capas objetivo, vivo — no snapshot fechado). `docs/auditoria/00-inventario.md` queda sin tocar: es salida fechada de A0 (2026-07-25), descriptiva de un momento, no un mapa que deba seguir sincronizado.

**Dónde queda la responsabilidad — gap real, abierto, con dueño de superficie distinto:**
1. **DDL** — constraints declarados en `stg_definition`/`dwh_model` (NOT NULL, tipos, FK) siguen siendo la única garantía estructural verificada por el backend hoy (validador de contrato D23/D38, `_type_mismatch_warnings`, etc.). Reglas de negocio que se puedan expresar como constraint de DDL quedan cubiertas por ese camino existente — no es un mecanismo nuevo, es delimitar que ahí es donde ya vive lo verificable.
2. **Data Validator (PDI)** — herramienta nativa de Pentaho Data Integration para validar datos en tiempo de ejecución del `.ktr`, todavía sin investigar en este proyecto (nombre, alcance y forma de integración quedan para una sesión futura). Candidato natural para reglas de negocio que no se reducen a un constraint de esquema (ej. "el monto no puede superar X cuando la categoría es Y") — se aplicarían corriendo el ETL, no auditando el XML generado.

**Qué NO resuelve esta decisión:** sigue sin existir, en ningún punto del pipeline, una verificación de que `reglasNegocio` (texto libre que hoy solo entra al prompt del LLM) se haya aplicado. D23 lo marcó como gap real; D39 lo deja igual de abierto, solo saca el enganche que fingía ser el lugar donde eventualmente se resolvería — el lugar correcto es DDL (ya cubierto parcialmente) + Data Validator (por investigar), no el backend inspeccionando steps.

**Consecuencia sobre el plan:** cierra el pendiente `validate_business_rules()` de la lista de F4 en `03-plan.md` (sin implementación equivalente). Agrega un pendiente nuevo, sin dueño hasta que se investigue: "investigar Data Validator de PDI para reglas de negocio en runtime".

*Por qué D39 y no solo borrar el archivo:* mismo criterio que D14/D16/D20/D22/D23/D24/D25/D26 — cambia el alcance que D23 había dejado fijado (punto de enganche futuro), antes de tocar código.

**Estado:** ejecutado, esta misma sesión (2026-07-28).

<a id="d40"></a>
### D40 — H29: recuperación determinista de `table` por contenido; `TABLE_BEARING_STEPS` explícito en vez de `required_keys`; nace `ktr_builder/validators/` `[F3/F4]`

**Contexto:** H29 (`01-hallazgos.md`) — cuando el LLM declara la tabla física de un step bajo una clave no cubierta por `contracts.STEP_CONTRACTS.key_aliases` (ej. `schema_table` en vez de `table`), `cfg.get("table")` da vacío y tres módulos independientes (`fragmentation.build_rw_matrix`, `dimension_step_policy.enforce_dimension_step_policy`, `fields_validate.validate_dimension_lookup_races`) hacen `if not table: continue` sin avisar — el step queda invisible para el motor de corte, el enforcement SCD1/SCD2 (D37) y el chequeo de carrera, contradiciendo el propio docstring de `fragmentation.py` ("D15: notifica, no bloquea" — "no bloquea" cumple, "notifica" no estaba implementado).

**Decisión — tres partes:**

1. **Prevención en el prompt, no solo recuperación en código.** `system_etl.txt` gana REGLA CRÍTICA B18: la clave de tabla física siempre es `table`, nunca una variante. Reduce la tasa, no la elimina — de ahí las dos partes siguientes.

2. **`table` NO entra a `required_keys` de `contracts.py`.** Se evaluó y se descartó — `required_keys` desemboca en `raise KtrBuilderError` (`build.py:132-133`), hard-abort que D15/D34 ya vienen descartando sistemáticamente (conexión sin resolver tampoco aborta). En cambio, `TABLE_BEARING_STEPS` (frozenset explícito en `contracts.py`, junto a `STEP_CONTRACTS`) declara qué tipos tienen tabla física — dato propio, sin colgarse del mecanismo que aborta. Un test de coherencia (`test_pdi_step_coherence.py::test_table_bearing_steps_matches_key_aliases_targeting_table`) verifica que no diverja de los `key_aliases` reales.

3. **Recuperación por CONTENIDO, no por posición.** Se descartó la heurística "el primer campo del config es la tabla" — no todo step con tabla la declara primero, y el orden de claves de un dict JSON no es garantía semántica del LLM. En cambio: si `table` sigue vacío tras `normalize_config()`, se busca entre los valores string top-level del config cuál coincide (case-insensitive, sin prefijo de schema) con una tabla física real conocida del ETL (`known_tables` — staging+DWH vía DDL parseado, o `dim_contracts` cuando no hay DDL, ej. `build_etl_from_raw`). Exactamente un match → se renombra esa clave a `table` (warning). Cero o varios matches → no se adivina, error explícito, el `.ktr` sale igual (D15).

**Dónde vive — nace `backend/app/services/ktr_builder/validators/`** (`base.py` con el contrato `ValidationContext`/`Finding`/`KtrPass`, `table_key_recovery.py` con el pass, `__init__.py` con `PRE_EMIT_PASSES`/`run_passes`). Deliberadamente separado de `fragmentation.py`/`dimension_step_policy.py`/`fields_validate.py` — no se migran de arrastre, el paquete nace con un solo pass y queda listo para sumar validadores nuevos sin que cada uno reinvente su propio canal de retorno (hoy conviven `list[str]`, `list[dict]` y mutación in-place sin retorno entre los módulos existentes).

**Punto de wiring — descubierto en implementación, corrige la premisa inicial del plan:** `enforce_dimension_step_policy` y `fragmentation.build_rw_matrix` (vía `split_ktr_by_cut`) corren en `etl_generator.py` **antes** de `build_ktr()` — cablear el pass solo dentro de `build.py` habría dejado 2 de los 3 puntos ciegos de H29 sin cubrir. El pass corre temprano, junto a `normalize_step_configs()`, en los 4 puntos de entrada (`build_etl_from_raw` ×2, `generate_etl_from_inference` sync, `_stage_pipeline` del flujo async) — y de nuevo, defensivamente, dentro de `build_ktr()` (idempotente, no-op si ya resolvió) para callers que lo invocan directo (tests, flujos que no pasan por el pipeline completo).

**Alcance de esta sesión:** solo `fragmentation.py` queda efectivamente cerrado para el caso H29 (su matriz R/W ahora ve el step recuperado). `dimension_step_policy.py` y `fields_validate.py` **también** se benefician porque corren después del punto de wiring temprano — pero el patrón triplicado `if not table: continue` en sí (la duplicación de "qué hacer cuando la tabla no resuelve") no se centralizó ahí; solo se cerró el síntoma (la tabla ahora suele estar cuando esos módulos preguntan). H29 pasa a **cerrado parcial** en `01-hallazgos.md` — ver esa entrada para el detalle de qué queda.

**Verificado (D13):** `backend/tests/test_table_key_recovery.py` (7 tests: recuperación exitosa, no-op con `table` ya presente, idempotencia, sin match, match ambiguo, step fuera de `TABLE_BEARING_STEPS`, contrato `repaired=True` ↔ mutación real) + `test_pdi_step_coherence.py::test_table_bearing_steps_matches_key_aliases_targeting_table`. Suite completa corrida antes/después (`git stash`): mismos 45 fallos preexistentes confirmados independientes (36 de `test_api.py` sin servidor vivo, 6 de `test_ktr_build_job_api.py`/D26/C.7, 1 de `test_ktr_xml_validator.py`, 1 de `test_structured_outputs.py`) — cero regresión nueva, 588 tests verdes + 11 nuevos.

**Estado:** ejecutado, esta misma sesión (2026-07-29).

<a id="d41"></a>
### D41 — H40: pass `flag_dead_computed_fields` (warning) + fix de wiring de `TABLE_KEY_PREFIX` en D40 `[F4]`

**Contexto:** H40 (`01-hallazgos.md`) — un `Calculator` puede declarar un campo nuevo (`calculations[].field_name`) que ningún step aguas abajo consume ni se mapea a ninguna columna de tabla destino. No rompe el build (Spoon corre igual, el campo queda flotando en el stream) — es cómputo del LLM sin efecto en el resultado, invisible hoy para cualquier validador. Hallazgo menor, sin fix aplicado por el usuario en el reporte original.

**Decisión — alcance acotado a `Calculator`, no a todo tipo "productor" de `contracts.STEP_CONTRACTS`:** generalizar a `Formula`/`NumberRange`/`GroupBy` exige reconstruir el stream real por step (qué campos ya venían del upstream vs. cuáles agrega ESE step puntual — el mecanismo que ya usa `fields_validate._topo_order`/`_step_output_fields`) para distinguir "campo nuevo" de "campo que ya estaba". `Calculator` es el único tipo donde el nombre del campo agregado se lee directo del config (`calculations[].field_name`) sin esa reconstrucción — encaja con el alcance "menor" que `01-hallazgos.md` le asignó a H40. Si el gap se confirma real en los otros tipos, es H nueva, no una ampliación silenciosa de este pass.

**Detección, no reparación:** severidad `"warning"` siempre, nunca mutación (`repaired=False`) — a diferencia de `recover_table_key` (D40), acá no hay nada seguro para auto-completar: el campo podría ser necesario a futuro (columna que el usuario todavía no agregó al destino) o directamente sobrar. Mismo criterio D15 (notifica, no bloquea/decide por el usuario).

**Algoritmo — conservador a propósito, mismo sesgo que `fields_validate.py` ("preferimos no detectar un hueco real antes que marcar mal un `.ktr` válido"):** el pass camina TODO el subgrafo alcanzable aguas abajo del `Calculator` (BFS por hops habilitados) y cuenta el campo como usado si CUALQUIER step ahí lo consume por nombre (`contracts.STEP_CONTRACTS[...].consumes`, que ya cubre `TableOutput`/`InsertUpdate`/`DimensionLookup`/`DBLookup`/`StreamLookup`/`SortRows`/`Unique`) — no distingue si un narrowing intermedio (`SelectValues` sin incluirlo, `GroupBy`) lo habría descartado del stream antes de llegar a ese consumidor real. `_consumed_names()` suma dos casos que `STEP_CONTRACTS` todavía no modela como `consumes` (gap propio, no de este pass, documentado en el docstring del módulo): `SelectValues` (consume por `select[].name` antes de un posible rename) y `GroupBy`/`MemoryGroupBy` (consume por `aggregates[].subject_field`) — sin esto, cualquier campo calculado que sólo alimentara un rename o un agregado daría falso positivo.

**Bug de wiring encontrado y corregido en el camino (no era el alcance original de esta sesión, pero bloqueaba sumar el pass sin introducir una regresión):** `etl_generator.py::_recover_table_keys` y `build.py::build_ktr` llamaban `run_passes(ctx)` (que corre TODOS los passes de `PRE_EMIT_PASSES`) y después prefijaban CADA finding con `TABLE_KEY_PREFIX = "[Clave de tabla] "` a ciegas — correcto mientras `PRE_EMIT_PASSES` tenía un solo pass (D40), pero con un segundo pass (`flag_dead_computed_fields`) etiquetaría sus warnings como si fueran de recuperación de tabla, silenciosamente. Fix: `TABLE_KEY_PREFIX` pasa a vivir DENTRO de `Finding.message` en `table_key_recovery.py` (cada pass es dueño de su propio prefijo, ahora `DEAD_FIELD_PREFIX = "[Cómputo sin consumidor] "` para el nuevo); los dos call-sites usan `f.message` sin agregar nada. Ningún consumidor externo comparaba el string `TABLE_KEY_PREFIX` fuera de estos dos puntos (verificado por grep) — cambio seguro.

**Dónde vive:** `backend/app/services/ktr_builder/validators/dead_computed_fields.py`, sumado a `PRE_EMIT_PASSES` (mismo punto de wiring temprano que D40 ya dejó armado — `etl_generator.py` + red de seguridad en `build.py`, sin cambios ahí más allá del fix de prefijo).

**Verificado:** `backend/tests/test_dead_computed_fields.py` (7 tests: warning cuando no hay consumidor, sin warning si mapea a `TableOutput`, sin warning si lo consume un `DBLookup` más adelante en la cadena, sin warning si `removed_from_result=Y`, tipos no-`Calculator` ignorados, hop deshabilitado no cuenta como alcanzable, `run_passes()` corre ambos passes sin que uno pise el prefijo del otro) + `test_table_key_recovery.py` (7, sin cambios de comportamiento tras el fix de prefijo). Suite completa corrida (excluyendo `test_api.py`/`test_ktr_build_job_api.py`, que ya requerían servidor vivo antes de esta sesión): 587 verdes, 2 fallos preexistentes sin relación (`test_ktr_xml_validator.py`, `test_structured_outputs.py` — mismos que documenta D40), cero regresión nueva.

**Estado:** ejecutado, esta misma sesión (2026-07-29).

<a id="d42"></a>
### D42 — H39: staging deja de recibir reglas de negocio en el prompt; causa raíz más profunda que el gap de `system_etl.txt` original `[F4]`

**Contexto:** H39 (`01-hallazgos.md`) — el LLM generó un `FilterRows` de validación de negocio duplicado, con condición distinta e incompleta, tanto en KTR_1 (origen→staging) como en KTR_2 (staging→DWH). El resultado final coincidió con lo esperado de casualidad (2+2 productos filtrados por separado sumando los 4 esperados) — un cambio futuro de reglas en el DWH hubiera dejado esos productos inalcanzables porque nunca llegaban a staging, rompiendo en silencio el contrato documentado de esa tabla ("Truncate y Load", copia completa).

**Causa raíz real, encontrada al investigar el hallazgo — más profunda que el gap de `system_etl.txt` regla 6 (línea 143) / checklist ítem 4 (línea 598) con el que abre H39:** `etl_generator.py::_build_prompt_from_inference` arma 2 prompts distintos por `mode` (`origen_stg`/`stg_dwh`, flujo 2-KTR de D20), pero el bloque `## REGLAS DE NEGOCIO {reglas}` se pegaba **verbatim, texto completo, en las dos llamadas**. El bloque `## ALCANCE DE ESTA LLAMADA` de `origen_stg` ya restringía tablas/steps de DWH explícitamente — pero no decía nada sobre reglas de negocio. El LLM veía la regla completa en ambas llamadas, sin ningún fence que le dijera que en KTR_1 no aplica, y la aplicó (mal, parcial) en las dos.

**Decisión:** en vez de agregar una prohibición más al lado de un texto que el modelo igual ve y puede razonar mal sobre — **se saca el bloque `## REGLAS DE NEGOCIO` del prompt `origen_stg` directamente.** Nada que leer, nada que razonar, nada que materializar en el KTR equivocado. Alternativa descartada: dejar el texto y solo agregar una prohibición explícita (era el plan original, caminos (a)/(b) del hallazgo) — el usuario pidió ir más allá y remover la necesidad de razonar sobre reglas de negocio en esta etapa, no solo prohibirlo con una frase que compite con el resto del prompt por atención del modelo.

**Alcance — solo `origen_stg`, no toca `mode=None` (legacy monolítico) ni `stg_dwh`:** `stg_dwh` sigue recibiendo `## REGLAS DE NEGOCIO` sin cambios — es la única llamada donde corresponde materializarlas. El bloque `## ALCANCE DE ESTA LLAMADA` de `origen_stg` gana texto reforzando el rol de staging como "contenedor FIEL del origen (truncate + load, copia estructural)" y prohibiendo explícito `FilterRows`/steps de validación de negocio ahí — defensa adicional por si el modelo infiere una regla de negocio del esquema mismo (nombres de columna, tipos) sin que el texto se la haya dado.

**Camino (b) de H39 (pase validador nuevo en `ktr_builder/validators/`, mismo paquete que D40/D41) queda descartado, no pospuesto:** con la causa raíz cerrada en el prompt, no hay nada que detectar post-hoc — el modelo ya no tiene con qué razonar mal en `origen_stg`. Si en el futuro se observa un `FilterRows` de negocio en KTR_1 pese a este fix (el modelo lo infiere del esquema sin que el prompt se lo haya dado), es hallazgo nuevo, no reapertura de H39.

**No tocado — `system_etl.txt` regla 6/checklist ítem 4 siguen sin nombrar la capa:** siguen siendo texto genérico, compartido por las dos llamadas vía `system` prompt. Se dejan así a propósito: con `origen_stg` sin bloque de reglas, esas líneas del checklist no tienen contra qué materializar nada en esa llamada. No se tocan para no acumular cambios fuera del alcance decidido esta sesión.

**Verificado:** cambio de prompt puro, sin lógica nueva — `python -m ast` sobre `etl_generator.py` sin errores de sintaxis. Sin test existente que fije el contenido de `_build_prompt_from_inference(mode="origen_stg")` (grep de `REGLAS DE NEGOCIO`/`origen_stg` en `backend/tests/` no encontró ninguno acoplado a este prompt específico) — no hay regresión de suite que correr. Pendiente de verificación real: correr el flujo 2-KTR completo contra el caso de `fixes_flujo_completo_stg_dwh.md` (mismo insumo que originó H38/H39/H40) y confirmar que KTR_1 ya no genera el `FilterRows` duplicado — no se hizo en esta sesión, no hay conexión/DDL real a mano. Anotado en `04-verificacion.md` si corresponde.

**Estado:** ejecutado, esta misma sesión (2026-07-29).

<a id="d43"></a>
### D43 — H38: CHECK del DDL (`col OP lit`, `BETWEEN`, `IN`) se extrae a `minimum`/`maximum`/`enum`; incluye fix de PK/FK con `CONSTRAINT` nombrado, más hondo que el alcance original `[F4]`

**Contexto:** H38 (`01-hallazgos.md`) — `ddl_adapter.py` nunca reconocía un `CHECK` (tabla o columna), y `FieldConstraints.minimum`/`maximum` existían en el schema sin un solo escritor en todo el backend. Investigando con `sqlglot` en vivo (postgres + tsql) para basar el fix en cómo la librería realmente entrega el AST, no en supuestos:

**Hallazgo que amplió el alcance antes de decidir el fix:** un `CONSTRAINT nombre PRIMARY KEY/FOREIGN KEY/CHECK(...)` llega envuelto en `exp.Constraint`, no en el tipo directo (`exp.PrimaryKey`/`exp.ForeignKey`/`CheckColumnConstraint`) — sin desenvolverlo, PK/FK/CHECK **nombrados** se pierden en silencio igual que un CHECK sin nombre. Probado contra un DDL real de DWH del usuario (`dim_producto`, `fact_inventario`, constraints 100% nombrados): **0 primary keys y 0 foreign keys detectadas en las 5 tablas**, no solo el CHECK. El usuario confirmó sumar este fix al mismo cambio — no es H38 tal como se escribió originalmente, pero comparte la causa (`exp.Constraint` nunca se desenvuelve) y el usuario lo autorizó explícitamente en la misma sesión.

**Decisión — alcance de patrones CHECK soportados en `_collect_condition_constraints` (`ddl_adapter.py`):**
- `col OP lit` (`>=`/`<=`/`>`/`<`, cualquier orden de operandos) → `minimum`/`maximum`. `And` recursivo (multi-columna, cualquier profundidad).
- `BETWEEN` → `minimum`/`maximum` directo (sqlglot ya lo da separado en `.args["low"]`/`.args["high"]`, sin partirlo a mano).
- `IN (...)` → `FieldConstraints.enum` (campo que también existía muerto, cero escritores — mismo patrón que `minimum`/`maximum`). Decisión explícita del usuario: no descartar `IN`, tratarlo como su propio campo de schema en vez de forzarlo a un rango.
- Operadores estrictos (`>`/`<`): ajuste `+1`/`-1` **solo para `CanonicalType.INTEGER`** (decisión explícita del usuario, acotando mi propuesta original). Para `NUMBER` no hay "próximo valor" sin conocer la escala del tipo (`NUMERIC(p,s)` sí la tiene, `FLOAT`/`DOUBLE` no) — se descarta y se loggea, **diferido a otra sesión** (queda la ruta trazada: `Decimal(1).scaleb(-scale)` como unidad exacta cuando `scale` está declarado).
- Descartado y loggeado, no levanta excepción: `OR`, funciones (`LENGTH(...)`), comparaciones columna-vs-columna, subqueries.

**Diferido, no decidido en esta sesión (pedido explícito del usuario):** rangos sobre fecha/texto (`CHECK (fecha >= '2020-01-01')`) — falta más información del usuario antes de diseñar el enfoque.

**Propagación (hueco 3 del hallazgo original) — sin esto, `minimum`/`maximum`/`enum` quedaban poblados pero invisibles para el LLM igual:** `ColumnProfile` (`context_schemas.py`) gana los 2 campos + `enum`; `schema_to_context.py::_field_to_minimal_profile` los pasa; `context_builder.py::format_model_context_for_prompt` los renderiza (`"rango válido (CHECK del DDL): ..."` / `"valores válidos (CHECK del DDL): ..."`) — whitelist del docstring actualizada explícitamente, es el único exit point al prompt.

**Hallazgo lateral, registrado aparte, no resuelto acá:** durante la misma investigación se confirmó que la responsabilidad de "cuál es la key de una tabla" vive partida en 2 lugares que nunca se comparan — `ddl_adapter` (parseo del DDL declarado) y `dim_contracts[i].natural_keys` (declarado por el LLM en inferencia, canal independiente — por eso los `.ktr` generados escribían bien en las dimensiones pese al bug de PK/FK). Candidato a unificación futura de Track A, no una decisión de esta sesión — ver `docs/arquitectura-objetivo-candidatos.md` § C1.

**Verificado:** `backend/tests/test_ddl_adapter.py` — 28 tests nuevos (`TestNamedConstraints`, `TestCheckConstraints`, + 2 en `TestFromDDLEndpoint`), incluyendo los 2 dialectos parametrizados y el DDL real del usuario probado manualmente antes de escribir los tests. Suite completa corrida con `git stash` de los archivos tocados (`ddl_adapter.py`, `schema_to_context.py`, `context_builder.py`, `context_schemas.py`, `test_ddl_adapter.py`) para aislar: los 54 fallos son idénticos con y sin el cambio (36 de `test_api.py` sin servidor vivo, 6 de `test_ktr_build_job_api.py`, 1 de `test_ktr_xml_validator.py`, ~11 de `test_structured_outputs.py` por cuota de Gemini agotada — `429 RESOURCE_EXHAUSTED`) — cero regresión nueva, 603 verdes + 28 tests nuevos.

**Estado:** ejecutado, esta misma sesión (2026-07-29).

<a id="d44"></a>
### D44 — Vocabulario de dimensión uniforme por rol; retira el residual `scd_type` 0/1 de D16 `[F4]`

**Contexto:** D16 dejó resuelto el camino 1 (`dim_contracts`) solo para `scd_type==2` (`DimensionLookup`); para 0/1 quedó `CombinationLookup`, con dos defectos independientes verificados en código (H41/H42): no mantiene atributos no-clave (A-2, dimensiones inutilizables para reporting) y es matemáticamente incortable (`_ALWAYS_RW` + un solo writer, inmune a C1/C1-bis). D16 rechazó en su momento usar `DimensionLookup(update=N)` para 0/1 porque "sin `date_from`/`date_to` reales, referenciarlas rompe en runtime" — ese argumento quedó obsoleto por `prompt_validacion_src.txt:24-26` (V1/V3, posterior a D16), que exige esas columnas en toda dimensión sin excepción por tipo. Bloqueaba confirmar que el step realmente resuelve bien contra esas columnas degeneradas — la investigación Fase 1 de `03c-investigacion-vocabulario-dimension-kettle.md` (R-K1, R-K1b, R-K2, R-K3, R-K3b) cierra esa pregunta contra el fuente real de Kettle.

**Decisión — vocabulario por rol, no por `scd_type`:**

1. `derive_dimension_loader_step(scd_type) -> "DimensionLookup"` (`update="Y"`) para **todo** `scd_type` (0, 1, 2). `CombinationLookup` sale de la derivación por defecto — sigue disponible solo vía override registrado (`OVERRIDE_STEP_PREFIX`), correcto únicamente para junk/technical dimension (R-K3, documentación oficial Pentaho: "will maintain the key information only").
2. `derive_fact_lookup_step(scd_type) -> "DimensionLookup"` (`update="N"`) para **todo** `scd_type`. Habilitado por R-K2: el matching por rango `[date_from, date_to)` resuelve bien el caso degenerado — pero no por la razón que D16 hubiera esperado. **El supuesto de D16 era incorrecto sobre el mecanismo, no solo obsoleto:** Kettle nunca deja `date_to` NULL en el loader — escribe `max_date` (`2199-12-31 23:59:59.999`, `Const.MAX_YEAR`). El rango real de una dimensión SCD0/SCD1 cargada así es `[1900-01-01, 2199-12-31 23:59:59.999)`, degenerado pero cerrado, no `[fecha_carga, NULL)`. Se conserva la exclusión de `DBLookup` (H23/R9 — falla introspección contra el pooler de Supabase, evidencia de log, no tocada por esta investigación).
3. **El modo de actualización es propiedad del atributo, no de la dimensión (S-8):** `attributes_scd2 → Insert` (nueva versión); `attributes_scd1 → Update` (R-K1b: `Update` reescribe solo la versión vigente por `tk`, `Punch through` reescribe todas las versiones por clave natural — no son intercambiables en general, pero con una sola versión por clave son indistinguibles en efecto; se elige `Update` porque describe la intención declarada). **SCD0 no lo soporta `Dimension lookup/update` con ningún modo** (R-K3b: los 3 modos con valor — `Insert`/`Update`/`Punch through` — versionan o sobrescriben, ninguno tiene semántica "no tocar si ya existe"). Para SCD0 real: `InsertUpdate` con todos los `<value>` no-clave en `update="N"` y la SK del DDL — con una trampa documentada que el emisor debe evitar: si **todos** los `<value>` quedan en `update="N"` y `update_bypassed` sigue en `"N"`, Kettle arma un `UPDATE ... SET` vacío y revienta en runtime (`prepareStatement` con SQL inválido); los dos flags se mueven juntos.
4. `f.get("type", "Insert")` (`steps/lookups.py:70`) pasa de default silencioso a **error de validación** — todo atributo del contrato sale con `type` explícito. Reforzado por R-K1b: `Insert` es exactamente el default real de Kettle (`TYPE_UPDATE_DIM_INSERT`, comentario `// INSERT is the default: don't lose information.`), heredado en silencio sin que nadie lo viera.
5. `ktr_builder/dimension_step_policy.py` invierte su única rama de auto-fix segura: hoy es `DimensionLookup → CombinationLookup`; pasa a sintetizar `fields`/`date_from`/`date_to`/`version_field` desde `DimContract` para reparar en la dirección contraria. Sigue siendo config de un step existente, no topología — no cruza la línea que D16 fijó.

**Supersede parcialmente D16:** el criterio de rol (loader vs. lookup del lado del hecho) y la exclusión de `DBLookup` se conservan sin cambio; el residual "0/1 sigue en `CombinationLookup`" queda superseded. Marcar D16 en el índice.

**No cerrado por esta decisión — bloqueante nuevo, ver C.12/H47:** la investigación encontró un corolario de R-K2 no contemplado en el checklist original: `checkDimZero` (Kettle) inserta la fila técnica "unknown" con solo 2 columnas (`tk`, `version`) — choca de frente con `date_from TIMESTAMP NOT NULL` sin DEFAULT que `prompt_validacion_src.txt` exige a toda dimensión. Generalizar el loader a `DimensionLookup(update=Y)` para todo `scd_type` (punto 1 de esta decisión) expande el radio de este choque de solo `scd_type==2` a **toda** dimensión del sistema. D44 es diseño cerrado, pero **no ejecuta limpio contra el DDL actual sobre una dimensión vacía** hasta que C.12 se resuelva — no bloquea escribir la Fase 2 del plan, sí bloquea darla por cerrada en código sin ese fix.

**Riesgo que esta decisión abre y no cierra por sí sola (S-15, ver H44):** medido con evidencia dura (diff byte a byte entre dos corridas del mismo caso, mismo backend, sin mano humana) que `scd_type` es no determinista sobre la misma entrada. Hoy la misinferencia se nota porque la rama 0/1 producía una dimensión visiblemente rota (H41/H42); D44 la deja impecable y silenciosamente equivocada si se implementa sola, sin la Fase 2-bis (finding informativo por dimensión + regla dura sobre columnas monetarias en `attributes_scd2` + confirmación explícita del usuario + medición de varianza en la corrida real). La Fase 2-bis no es opcional respecto de esta decisión.

**Verificación:** contra fuente real de Kettle (`DimensionLookup.java`/`DimensionLookupMeta.java`/`InsertUpdateMeta.java`/`InsertUpdate.java`, rama `master` de `pentaho/pentaho-kettle`, consultada 2026-07-30) y documentación oficial Pentaho — mismo estándar que D36 usó para cerrar H27/H28. Detalle completo en `investigacion-kettle-RK1-RK6.md` (adjunto), consolidado en `03c-investigacion-vocabulario-dimension-kettle.md`.

**Estado:** diseño cerrado. No implementado en código todavía — bloqueado en ejecución por C.12 (H47). Tests nuevos a escribir cuando se implemente: reproducción del caso Set A (loader `dim_categoria` + lookup FK del hecho, `scd_type` 1) debe producir `groups == 2` (caso de regresión de D7); `test_dimension_step_policy.py` — reparación `CombinationLookup → DimensionLookup` con `fields`/fechas sintetizadas, `type` explícito por atributo como error de validación, override registrado respetado.

**Nota de ejecución (2026-07-30):** implementado en código, misma sesión que R-K7/D51 (ver esa entrada para la resolución de `scd_type==0`, que D44 dejaba entre sus puntos 1 y 3). `derive_dimension_step_type()` se elimina (no queda alias) y se reemplaza por `derive_dimension_loader_step()`/`derive_fact_lookup_step()`/`derive_attribute_update_mode()` (`domain/scd.py`) — mismo criterio de excepción nombrada que el resto del módulo. `dimension_step_policy.py` invierte su única rama de auto-fix segura (`CombinationLookup → DimensionLookup`, sintetizando `fields`/`date_from`/`date_to`/`version_field` desde `DimContract`) y la rama `fact_lookup` con `scd_type` sin versionar pasa de "reporta, no repara" a reparar igual que `scd_type==2` (cerrado por R-K2 positivo). `steps/lookups.py` no cambia sus defaults (siguen como red de contención del emisor) — el hueco se cierra con un pass pre-emisión nuevo, `validators/dimension_lookup_fields.py` (`date_from`/`date_to` ausentes, `fields[].type` fuera de la tabla `typeCodes` real de Kettle → severidad error). `steps/output.py:_step_InsertUpdate` gana `<update_bypassed>` (nunca se emitía) con default seguro (`Y` si no hay ningún `<value>` updatable) + `validators/insert_update_bypass.py` para la combinación explícita contradictoria — hallazgo lateral encontrado al revisar `InsertUpdateMeta`, no cubierto por D44 originalmente pero del mismo tipo de bug (`SET` vacío en runtime). `backend/prompts/system_etl.txt` — vocabulario uniforme por rol, `modo_por_atributo` explícito, ejemplos JSON con `update`/`version_field`, checklist ítem 24 invertido, `19b` corregido (`version_field` es clave válida, la inválida es `"version"` a secas). Suite completa antes/después: 605→635 passed, mismos 54 fallos preexistentes (D26), cero regresión nueva — 30 tests nuevos (`test_scd_policy.py`, `test_dimension_step_policy.py` reescrito con inversiones documentadas, `test_dimension_lookup_fields.py`, `test_insert_update_bypass.py`, `test_scd_zero_calendar_guard.py`, `test_fragmentation.py` caso Set A, `test_ktr_builder_fidelity.py`).

<a id="d45"></a>
### D45 — Corte visible: resolución de tabla por SQL como port, clave `(connection, table)` normalizada, RW desdoblado, exención por camino dirigido eliminada `[F3]`

**Contexto:** con el vocabulario uniforme (D44) las dimensiones dejan de ser invisibles al corte — pero `TableInput`/`ExecSQL` siguen invisibles para todo lo demás, y el agujero de C1 con roles RW sigue abierto. Independiente de D44 en el sentido de que no depende de que D44 se implemente primero, pero se vuelve **obligatoria** si alguna investigación futura revirtiera R-K2 (Plan B del plan original) — no es el caso: R-K2 salió positivo, así que esta fase sigue siendo "robustece", no "es el fix".

**Decisión:**

1. **Resolución de tabla por SQL real, no por coincidencia de contenido.** `build_rw_matrix(ktr_data, aliases, resolve_sql_tables=None)` recibe un callable — protocolo definido en `domain/`, implementación con `sqlglot` en `infrastructure/` junto a `adapters/ddl_adapter.py`. Restricción no negociable de `test_architecture_layers.py` (fragmentation es capa pura, sqlglot es `INFRA_LIBS`): primer port real del repo, insumo directo de Track A. Extrae el **conjunto** de tablas de `FROM`/`JOIN`, clasifica `ExecSQL` por `TRUNCATE`/`INSERT`/`UPDATE`/`DELETE`/`CREATE`. `StreamLookup` deja de ser invisible (tabla = la del `TableInput` que lo alimenta). SQL no parseable → `Finding(severity="error")` accionable, no abort (D15). Reemplaza el regex `_TABLE_RE` de `lineage_builder.py:34-38` y retira el workaround por regex que `contract_validate._per_file_table_roles` documenta como deliberado (D23) — un solo resolver para los dos.
2. **Clave de matriz `(connection, table)` normalizada**, no `table.lower().strip()` — cierra C-7 (conexiones lógicas múltiples al mismo destino físico) y la asimetría de namespace de H43 (`table_key_recovery._bare()` quita el schema, el camino feliz no). `schema` **no** entra a la clave todavía (S-10, ver C.11) — en la evidencia disponible `<schema/>` siempre está vacío.
3. **C1 con RW desdoblado.** Un step `RW` cuenta como entrada en `readers` y en `writers` distinguibles — cierra la inmunidad de toda tabla cuyo único step visible es RW (H42).
4. **Eliminar la exención por camino dirigido** (`_reaches`, `fragmentation.py:97-118`). En Kettle todos los steps arrancan como hilos concurrentes; los hops transportan filas, no ordenan efectos de BD. Cambio de comportamiento con test invertido y documentado: `test_compute_cut_self_lookup_insert_new_only_exception_does_not_split`.
5. **Hops de datos que cruzan grupos** — detectar y reportar como error (`split_ktr_by_cut` hoy descarta sin reconectar). Materialización va aparte, C.10.
6. **Chequeos a nivel etapa (S-13):** orden del job coincide con el topológico del corte, ningún fragmento lee lo que otro fragmento posterior escribe, ningún hop de datos descartado sin error.
7. `untouched_comps` se dejan como están (D6-bis explícito) — se agrega inventario en las notificaciones.

**Verificación:** `test_fragmentation.py`, `test_fragmentation_wiring.py`, `test_architecture_layers.py`/`test_pdi_step_coherence.py` verdes sin relajar límites. Detalle completo en Fase 3 de `03c-investigacion-vocabulario-dimension-kettle.md`.

**Nota de ejecución — Sesión A (2026-07-30): puntos 3, 4, 5, 7 ejecutados; puntos 1, 2, 6 quedan para sesión aparte.** Decidido explícitamente con el usuario partir la entrada por costo: 3/4/5/7 son cambios de comportamiento contenidos en `fragmentation.py`, verificables con tests puros, sin infraestructura nueva; 1/2/6 son el primer port real del repo (sqlglot en infra, `Protocol` en `domain/`) y un cambio de forma de la clave de la matriz que ripplea a `contract_validate.py`/`lineage_builder.py` — se dejan para cuando esa sesión se abra.

- **Punto 3 ejecutado tal cual:** `is_c1` pasa de `any(r not in writers for r in readers) and writers` a `any(r != w for r in readers for w in writers)` — la carrera es entre steps DISTINTOS, no por coincidencia con C1-bis (H42). Un step `RW` solo sobre su propia tabla (loader de dimensión normal, `update=Y`) no dispara por serlo.
- **Punto 4 ejecutado, con un ajuste sobre el texto original:** el texto de la decisión decía "se elimina, o se restringe a lookups puros" (ver Fase 3 punto 4 de `03c-investigacion...`) — se eligió eliminar sin restricción: no hay caso en el corpus disponible (`err1.ktr`/`err2.ktr`, Set A/B) que necesite la variante restringida, y agregarla sin caso real violaría D6-bis. `_reaches()` se borra completa (sin otros callers, verificado). `_connected_components()` pasa a respetar `hop.get("enabled", True)` — antes de D45 esto solo lo hacía `_reaches`, que se usaba nada más para la excepción que ahora no existe; sin el traslado, ningún componente respetaría `enabled`. La rama "mismo componente" de `compute_cut` emite `Finding(severity="error")` siempre, ya no condicionado a `safe`. Test invertido: `test_compute_cut_self_lookup_insert_new_only_exception_does_not_split` → `test_compute_cut_self_lookup_same_component_now_reports_race` (`test_fragmentation.py`).
- **Punto 5 ejecutado, con un hallazgo lateral no anticipado por D45 ni por la investigación 03c:** con el algoritmo actual, un grupo es siempre la unión completa de 1+ componentes conexos — por construcción, un hop `enabled` con los dos extremos conocidos **nunca** cruza un grupo (los dos extremos comparten componente, y todo componente cae entero en un solo grupo). El chequeo nuevo en `split_ktr_by_cut` solo puede disparar hoy por el caso hop-colgante (extremo que referencia un step inexistente) — queda igual como Finding `error`, afirmado como invariante para cuando D48 (materialización de hops cruzados vía tabla de staging) haga alcanzable el caso real. Ver H nueva en `01-hallazgos.md`.
- **Punto 7 ejecutado tal cual:** `Finding(severity="info")` en `compute_cut`, solo cuando hay corte real (`final_order` no vacío) y `untouched_comps` no vacío — inventaría los steps que quedaron juntos sin señal de tabla.
- Puntos 1, 2, 6: sin tocar. **Decisión ya tomada para cuando se ejecute el punto 2** (registrada acá para no perderla): cuando un step no declara `connection` en su config, la clave `(connection, table)` no puede resolverse por lectura directa — hoy la inferencia por prefijo de tabla vive en `ktr_builder/connection.py` (`_STAGING_PREFIXES`/`_DWH_PREFIXES` + `_resolve_connection()`, `:15-16,54-68`), corre DESPUÉS del corte (dentro de `build_ktr()`, con `connection_names`/`pass_source_connection`/`pass_dest_connection` que `compute_cut()` no recibe hoy) y devuelve nombres inferidos (`"conn_dwh"`/`"conn_staging"`/`"conn_origen"`) que pueden no estar en `connection_names` todavía en el punto donde correría `build_rw_matrix`. La sesión B extrae la inferencia pura por prefijo (sin `connection_names`/roles de pase, sin resolver contra conexiones reales) a un módulo nuevo de `domain/`, y `connection.py` la importa de ahí — una sola casa para la heurística, matriz y emisor no pueden divergir. No es T2 completo (T2 pide una `resolve_step_table()` unificada con notificación, que además unifica los tres `if not table: continue` de `fragmentation.py`/`dimension_step_policy.py`/`fields_validate.py`) — es el subconjunto que el punto 2 de D45 necesita.
- Suite completa antes/después: 646→650 passed (4 tests nuevos: `test_compute_cut_rw_only_loader_does_not_trigger`, `test_connected_components_ignores_disabled_hops`, `test_compute_cut_untouched_comps_inventory_only_when_real_cut`, `test_split_ktr_by_cut_cross_group_hop_reports_error`; el quinto cambio es el rename/inversión del test existente), mismos 54 fallos preexistentes (D26/D52) — cero regresión.

**Nota de ejecución — Sesión B (2026-07-30): puntos 1, 2, 6 ejecutados.**

- **Punto 1 (resolución de tabla por SQL real):** `domain/sql_resolution.py` nuevo — `SqlResolution`/`SqlTableResolver` (dataclass + `Protocol` puros de stdlib, agregado a `DOMAIN_MODULES`). Implementación real en `services/adapters/sql_table_resolver.py` (`resolve_sql_tables()`, sqlglot) — parsea `SELECT`/`TRUNCATE`/`INSERT`/`UPDATE`/`DELETE`/`CREATE`, extrae tabla(s) de `FROM`/`JOIN` o la tabla afectada, y columnas proyectadas de un `SELECT` (S-7, mismo criterio "pierde certeza con `SELECT *` o expresión sin alias" que `contracts.py:_select_columns`). `build_rw_matrix(ktr_data, aliases, resolve_sql_tables=None)` — con resolver: `TableInput` aporta sus tablas como `"R"`, `StreamLookup` hereda la tabla del `TableInput` que referencia (`cfg["step"]`), `ExecSQL` se clasifica por operación real (`TRUNCATE`/`INSERT`/`UPDATE`/`DELETE` → `"W"`; `CREATE` sin rol, DDL estructural). SQL no parseable → `Finding(severity="error")`, no aborta (D15). Sin resolver (default `None`): comportamiento idéntico a antes de D45 — invariante que preserva toda la Sesión A intacta. Único punto de wiring real: `_build_ktr_stage` (`etl_generator.py`) inyecta la implementación de infra. `contract_validate._per_file_table_roles` pierde su workaround por regex (documentado como deliberado en D23) — pasa el resolver real directo (no es `DOMAIN_MODULES`) y usa `build_rw_matrix` nativo: "un solo resolver para los dos", como pedía el punto 1. `lineage_builder._TABLE_RE` (regex, diagrama de linaje) **no se tocó** — sirve un propósito distinto (tolerante a XML roto) y tocarlo no es necesario para que el motor de corte funcione; queda como residual conocido, no D45.
- **Punto 2 (clave `(connection, table)`):** `domain/table_layer.py` nuevo — `infer_table_layer()`, extraído de `ktr_builder/connection.py` (`_STAGING_PREFIXES`/`_DWH_PREFIXES` se eliminan de ahí, `_resolve_connection()` importa la función). `fragmentation.MatrixKey = tuple[str, str]` — `build_rw_matrix` devuelve `{(connection, tabla): {step: rw}}`; `_connection_key(cfg, table)` resuelve explícito (`cfg["connection"]`) o inferido (mismo criterio, sin `connection_names`/roles de pase — esos solo existen dentro de `build_ktr()`, después del corte). `contract_validate.py`/`guard_staging_layer.py` (Fase 2-ter) adaptados a la clave tupla.
- **Punto 6 (S-13, chequeos a nivel etapa):** `fragmentation.validate_stage_contract(sub_dicts, aliases, resolve_sql_tables=None)` — nueva, llamada desde `_build_ktr_stage` inmediatamente después de `split_ktr_by_cut`. De los 3 ítems de S-13: "orden del job coincide con el topológico" es garantía de construcción (mismo `list`, sin reordenar, entre `split_ktr_by_cut` y `_build_job_plan`), no un chequeo aparte; "hop de datos descartado sin error" ya lo cubre el punto 5 (Sesión A); el gap real y único que necesitaba código nuevo es "ningún fragmento lee lo que otro fragmento POSTERIOR escribe" — V2 (dentro de `compute_cut`) solo mira "sin writer en ESTE archivo", no compara contra los N-1 restantes de la misma etapa. `validate_stage_contract` sí lo hace: matriz R/W por fragmento, primer escritor de cada `(connection, table)`, error si un lector de un fragmento anterior depende de un escritor posterior.
- Suite completa antes/después: 636→639 passed (3 tests nuevos en `test_fragmentation.py`: `validate_stage_contract` single-fragment/writer-antes/reader-antes), mismos fallos preexistentes (1 en el recorte sin servidor/cuota) — cero regresión.

**Estado:** ejecutado completo (Sesión A + Sesión B, 2026-07-30).

<a id="d46"></a>
### D46 — Severidad promovida + `error_catalog_checks` cableada + golden negativo como gate; D15 ejecutada, no superseded `[F4]`

**Contexto:** `error_catalog_checks.py` (V4-V13, 451 líneas, con tests) existe y no está wireada a ningún path de runtime. `Finding.severity` está estructuralmente muerto — los dos call sites lo aplanan a `str` (`etl_generator.py:213`, `build.py:159`) y `_split_integrity_warnings` promueve por prefijo de mensaje, no por severidad; ningún prefijo cubre los findings de corte (`compute_cut`) ni `[Clave de tabla]`, así que un race detectado hoy llegaría a la UI como advertencia de buenas prácticas, no como error.

**Decisión:**

1. **Gate duro previo (S-1), antes de cablear cualquier severidad:** los artefactos post-fix de la corrida real contra `Base_01` (`.ktr`/`.kjb` que **ejecutaron** con conteos verificados) deben producir **cero** findings de V4–V13. Fixtures permanentes (S-3): negativo de todos los checkers + línea base estructural.
2. `error_catalog_checks.py` se cablea al final de `build_ktr` (después de `validate_ktr_xml`) — `parse_ktr(ktr_xml)` → V4/V5/V6/V7/V8/V11/V13 → `Finding` con severidad, patrón "anota, no aborta" (mismo patrón que D34 para conexiones). Motivador real es **A-1** (clave de dimensión vacía — `CombinationLookup` sí declara `required_keys`, pero con contenido vacío; `missing_required_keys` valida presencia, no contenido; V13 es exactamente ese hueco), no B-1 (B-1 se retira como hallazgo — el mapeo de `InsertUpdate` de este repo ya está correcto, verificado contra `InsertUpdateMeta.getXML()`, R-K6).
3. **`v8_truncate_sin_transaccional` corregida antes de cablearse con severidad `error` — estaba invertida, no aproximada (R-K5).** `<unique_connections>` **es** el flag real (`TransMeta.usingUniqueConnections`, no un proxy): difiere todo commit al final de la transformación, desactiva `use_batch` en `Table output` en silencio, y convierte el `truncate` en `DELETE FROM` transaccional (vs. `TRUNCATE TABLE`, típicamente con commit implícito, bajo `unique_connections=N`). El caso peligroso es `truncate=Y` **con** `unique_connections=N`, no al revés — los dos sets de evidencia disponibles tienen `unique_connections=Y`, el caso seguro. Cablear `v8` tal como está formulada marcaría error exactamente la configuración segura. Se corrige la condición antes de darle severidad `error`; hasta entonces queda fuera del cableado con severidad (ya era la decisión original, esta investigación confirma que la razón es más fuerte de lo que se pensaba: no es "aproximada", es "al revés").
4. `Finding.severity` se revive — `_recover_table_keys`/`build.py` dejan de aplanar a `str`, el caller promueve por `severity == "error"`. `compute_cut` pasa `notifications: list[str]` a `list[Finding]`.
5. Superficie de usuario (S-14): `Validacion(tipo="error")` visualmente distinguida, descarga exige reconocimiento explícito — no se bloquea (D15 no se revierte).
6. Se borra el marker de debug `logger.warning("### DIMLOOKUP_MARKER...")` (`steps/lookups.py:35`).

**D15 se ejecuta, no se supersede:** mismo patrón que D34 — el `.ktr` sigue saliendo siempre; lo que cambia es que el finding de error deja de perderse en el canal de buenas prácticas.

**Verificación:** `test_error_catalog_checks.py` — golden negativo de la corrida `Base_01` en cero findings, gate de esta decisión.

**Nota de ejecución (2026-07-30):** fixtures S-1/S-3 obtenidos del usuario (`ktr_1_origen_a_staging.ktr`/`ktr_2_stg_a_dwh.ktr`, Fix 1 + Fix 2 de `fixes_flujo_completo_stg_dwh.md` ya aplicados, verificado leyendo el XML — condición AND completa en `Filtrar Precios Negativos` de `stg_dwh_2`, sin ese step en `ktr_1`), password Kettle real saneado (`<password/>`) antes de commitear — nunca se persiste un `Encrypted ...` real, mismo criterio que el resto del proyecto. Golden test pasa en cero findings al primer intento con V4/V5/V6/V7/V8/V11/V13 (`backend/tests/fixtures/golden_run_base_01/`, `test_error_catalog_checks.py::test_golden_run_base_01_zero_findings`).

**Punto 3 (v8) — verificado al implementar, no hizo falta corregir código:** al leer `error_catalog_checks.py` para cablearlo, `v8_truncate_sin_transaccional` ya tenía la condición correcta (`transactional = unique_connections == "Y"`, finding solo cuando `truncate=Y and not transactional`) y su docstring ya documentaba la investigación R-K5 palabra por palabra. No hay evidencia en el historial de git de una versión anterior invertida — el punto 3 de esta decisión describía una corrección que, para cuando se ejecutó, ya estaba hecha en el módulo. Se cablea V8 sin cambios de código en `error_catalog_checks.py`.

`_split_integrity_warnings` (`etl_generator.py`) gana un cuarto prefijo, `PRE_EMIT_ERROR_PREFIX` (`validators/base.py`, nuevo `split_findings_by_severity()`), en vez de que cada pass devuelva `list[Finding]` a través de todo el plumbing de `list[str]` existente (~7 call sites) — mismo mecanismo de promoción por prefijo que ya usan `FIELD_INTEGRITY_PREFIX`/`CONTRACT_PREFIX`/`ERROR_CATALOG_PREFIX`, menor blast radius que cambiar el tipo de retorno en cada caller. `compute_cut`/`split_ktr_by_cut` (`fragmentation.py`) pasan a `list[Finding]`: V2 (lookup sin productor en la etapa) es `"warning"` — la tabla puede cargarse legítimamente en otra etapa/archivo, no es un error confirmado; "mismo componente sin relación segura" y "ciclo detectado" son `"error"`. `services.ktr_builder.validators.base` se agrega a `DOMAIN_MODULES` en `test_architecture_layers.py` (dataclasses/Protocol puros de stdlib, domain→domain, sin excepción real que registrar).

**Estado:** ejecutado, esta misma sesión (2026-07-30).

<a id="d47"></a>
### D47 — C.12 resuelta: sembrado de la fila `tk=0` embebido en el DDL, no relajar `date_from` a NULLable `[F4]`

**Contexto:** D44 quedó con un bloqueante de ejecución sin resolver (C.12/H47): `checkDimZero` inserta la fila "unknown" con solo `tk`/`version`, lo que choca con `date_from TIMESTAMP NOT NULL` sin DEFAULT que `prompt_validacion_src.txt:24-26` exige hoy. Investigación de seguimiento contra documentación oficial de Pentaho (`investigacion-pentaho-C10-C11-C12.md`, complementa `investigacion-kettle-RK1-RK6.md` sin contradecirlo) resuelve las tres opciones que quedaron abiertas.

**Evidencia que colapsa la elección:**

1. **La doc oficial ("Dimension Lookup-Update", Pentaho Community Wiki) confirma el modo de falla textualmente** y **prescribe el remedio — no relajar el DDL:** *"If you have 'NOT NULL' fields in your table, adding this empty row and then the entire step will fail! So make sure that you have a record with the ID field = 0 or 1 in your table..."* — y en la misma página, sección *Lookup*, documenta el pre-sembrado como patrón normal: *"...just like you would add the specific details of the 'Unknown' row prior to population of the dimension table."*
2. **El 4º camino (opción de config para saltear la fila unknown) no existe en PDI/Kettle.** Existe en Apache Hop (*"Do not check or insert the 'unknown' row"*, pestaña *Technical key creation*) — pero `checkDimZero()` tiene un único guard (`!meta.isUpdate()`) y el bundle i18n completo del step en Kettle no tiene ninguna etiqueta equivalente. Como este sistema emite `.ktr` de Kettle, no de Hop, esta opción **no está disponible**.
3. **El generador de DDL del propio fabricante (botón *SQL* del step, `PostgreSQLDatabaseMeta.getFieldDefinition`) emite `date_from`/`date_to` como `TIMESTAMP` NULLable, sin `NOT NULL`.** El DDL que V1/V3 exige hoy es más restrictivo que el del fabricante, exactamente en la columna que la doc marca como causa de falla — confirma que "relajar a NULLable" sería alinear con el fabricante, pero no es lo que el fabricante recomienda hacer primero.

**Decisión — mecanismo del sembrado: embebido en el DDL, no `ExecSQL`.** De las tres alternativas evaluadas (ver tabla comparativa en `investigacion-pentaho-C10-C11-C12.md` §C.12.5):
- **Elegido: INSERT de la fila `tk=0` en la Parte 3 de `prompt_validacion_src.txt`, junto a la definición de columnas.** Un solo lugar, determinista, sin step nuevo, sin tocar la topología ni la matriz R/W de la Fase 3. La fila existe antes de cualquier corrida — `checkDimZero` la encuentra (`count != 0`) y no hace nada, sin depender de orden de ejecución.
- **Descartado: `ExecSQL` al inicio del `.kjb`.** Agrega un segundo escritor sobre la dimensión — cambiaría la matriz R/W de la Fase 3 y obligaría a garantizar orden respecto del loader (S-13), costo que el sembrado en DDL no tiene.
- **Descartado: dejar que Kettle cree la fila + relajar el DDL a NULLable.** Cero trabajo, pero dos costos que el sembrado evita: (a) los atributos de la fila 0 salen NULL, no `'DESCONOCIDO'` — D21 no queda gratis; (b) obliga a que **toda** columna de negocio de toda dimensión sea NULLable o tenga DEFAULT, restricción de contrato más cara que un INSERT puntual.

**Requisito no obvio que sale de la evidencia:** el sembrado debe usar `tk=0` y `version=1` exactos — no por convención, sino porque `checkDimZero` chequea literalmente `WHERE <tk> = 0` (`getNotFoundTK` = 0 para Postgres, confirmado en R-K4) y porque `IfNull → 0` del lado del hecho apunta ahí. Un sembrado con `tk=-1` no desactiva `checkDimZero` y la transformación sigue abortando.

**Cierra, de paso:** D21 (etiqueta legible del miembro desconocido — la aporta el sembrado, `checkDimZero` nunca la puede escribir) y la observación abierta de `investigacion-kettle-RK1-RK6.md` §5 sobre el origen de la etiqueta `'DESCONOCIDO'` observada en la corrida real — tiene ahora una hipótesis con respaldo oficial (un sembrado previo, patrón recomendado), pendiente de confirmar contra los artefactos de `Base_01` (ver Pendientes de la investigación).

**Consecuencia sobre D44:** el bloqueante de ejecución (C.12/H47) queda resuelto — D44 ya no está bloqueada, sigue como diseño cerrado sin implementar. El sembrado es parte del contrato de DDL, no del vocabulario de step — se rutea a `06-contrato-ddl.md` como DDL-1, junto con el resto de la deuda de DDL que se está consolidando ahí.

**Nota de ejecución (2026-07-30):** `prompt_validacion_src.txt` (I8, V5) reescrito para exigir INSERT completo de la fila 'desconocido' — `technical_key=unknown_key_value`, `version_field=1`, `date_from='1900-01-01 00:00:00'`, `date_to='2199-12-31 23:59:59.999'`, y cualquier otra columna NOT NULL sin DEFAULT recibe `'DESCONOCIDO'`/`0` según tipo. Sin test dedicado (texto de prompt LLM, mismo criterio que el resto del archivo) — gate real pendiente de corrida contra el modelo. Detalle en `06-contrato-ddl.md` DDL-1. Esta entrada en `02-decisiones.md` no se había actualizado en su momento — corregido acá, drift detectado revisando 03c.

**Estado:** ejecutado (2026-07-30). Cierra C.12/H47.

<a id="d48"></a>
### D48 — C.10 resuelta: materialización de hops que cruzan grupos vía tabla de staging, no `Copy rows to result` `[F3]`

**Contexto:** D45 (punto 5) decidía "detectar y reportar como error" un hop de datos que cruza grupos tras el corte, sin decidir el mecanismo de reconexión. C.10 quedó abierta preguntando si `Copy rows to result`/`Get rows from result` — el mecanismo nativo de Kettle para pasar filas entre transformaciones de un mismo job — alcanza.

**Evidencia que descarta el mecanismo nativo, no por memoria sino por un límite estructural:**

1. `Copy rows to result` acumula el stream completo en heap (`RowsToResult.processRow`, sin streaming, sin spill a disco, sin parámetro de tamaño en la UI ni en la doc oficial) — riesgo de memoria conocido pero sin número oficial, no es el argumento decisivo.
2. **El argumento decisivo: el `Result` que viaja por el `.kjb` tiene una sola lista de filas, sin nombre ni canal** (`Result.getRows()`). `RowsToResult` la puebla con `addAll`, `updateResult` la **reemplaza entera**, `RowsFromResult` consume toda la lista sin poder filtrar por origen. **Un `.kjb` puede materializar como máximo un stream cruzado a la vez.** El corte, por construcción, puede producir N hops cruzados en la misma etapa — el mecanismo no escala más allá del caso degenerado (exactamente un hop, volumen chico, esquema estable).
3. Efecto colateral confirmado en fuente: si se usa igual, el rowset queda **invisible a la matriz R/W** — reintroduciría exactamente la clase de invisibilidad estructural que la Fase 3 existe para eliminar (mismo problema que hoy tiene `TableInput` sin resolver por SQL).

**Decisión:** la materialización de un hop de datos que cruza grupos se hace vía **tabla de staging** (un `Table output` en el grupo emisor + un `Table input` en el grupo receptor), no vía `Copy rows to result`. Consecuencia gratuita: la tabla entra sola a la matriz R/W de la Fase 3 (D45), el orden queda cubierto por el chequeo a nivel etapa (S-13, ya decidido), y el hop cruzado deja de ser un caso especial — se vuelve dos steps normales que el resto del sistema ya sabe razonar.

**No decidido por esta entrada (implementación, no bloqueante):** nombre de la tabla, ciclo de vida (truncar antes/después, quién la limpia), si vive en el schema de staging existente o uno propio. Queda como detalle de implementación de la Fase 3 cuando se ejecute — no amerita una entrada de Abiertos propia por ahora (D6-bis: no adelantar abstracción sin necesidad concreta todavía).

**Nota de ejecución (2026-07-30) — hallazgo que reabre el alcance de esta entrada:** al implementar, resultó que el mecanismo (tabla de staging) no alcanza solo — con el algoritmo de corte de D45, un hop con `from`/`to` conocidos **nunca** cruza un grupo (los dos extremos siempre comparten componente conexo por construcción; un grupo es siempre la unión completa de 1+ componentes). El caso "cruza grupos" que D45 punto 5 dejaba reportado como error solo era alcanzable por el hop-colgante (referencia a un step inexistente) — nunca por un cruce real. Para que D48 tuviera algo real que materializar, hubo que reabrir la decisión de D45 punto 4 ("mismo componente conexo nunca se parte") para el único patrón evidenciado en el corpus: **un único writer, con TODOS sus readers de esa tabla como ancestros dirigidos suyos** (self-lookup: `Existe? -> Filtrar Nuevos -> Insertar Dim Pais`, `err1.ktr`/`err2.ktr`). Para ese patrón, el componente se parte: el writer (+ sus descendientes) pasa a un grupo posterior, el resto (incluidos los readers) a uno anterior, y el/los hop(s) que el corte deja colgando entre ambos se materializan con el mecanismo que esta entrada ya había decidido. Cualquier otro caso dentro de un componente (más de un writer — C1-bis, o algún reader que NO es ancestro del writer — orden real ambiguo, no hay forma segura de decidir qué va primero) sigue exactamente como D45 lo dejó: `Finding(severity="error")`, "revisar a mano", sin partir. No es el caso general (eso pediría resolver un problema de corte de grafo con múltiples pares simultáneos, potencialmente contradictorios, fuera de alcance sin evidencia de que ocurra en la práctica — D6-bis).

**Implementación de los 3 puntos que esta entrada dejaba abiertos:** nombre `etl_corte_N` (determinista dentro de la etapa, N = orden de `sorted(materialize_hops)`) — deliberadamente **fuera** de `STAGING_TABLE_PREFIXES`/`DWH_TABLE_PREFIXES` (`domain/table_layer.py`) para no disparar `guard_staging_layer.py` (Fase 2-ter/D53): es plomería interna del motor de corte, no la capa de staging del contrato del usuario, y un `FilterRows` (el propio "Filtrar Nuevos" del patrón self-lookup) alimentándola es legítimo, no una violación de D42. Conexión: `conn_staging` explícita (reusa la conexión real de staging, no pide una tercera al usuario). Ciclo de vida: `truncate=True` en el `TableOutput` — tabla efímera, vive solo dentro de la misma corrida. Sin columnas explícitas en ninguno de los dos steps (`TableOutput` sin `fields` → Kettle escribe todo el stream por nombre; `TableInput` con `SELECT *`) — evita mantener un mapeo de columnas paralelo al que ya circula por los steps reales.

**Código:** `fragmentation.py` — `_directed_ancestors`/`_directed_descendants` (grafo dirigido de hops, distinto de `_connected_components` que es no dirigido), `component_splits` recolectado en el loop de `compute_cut` que antes solo emitía el error de "mismo componente", aplicado antes de construir `groups_by_comp` (nuevo `comp_id` por componente partido + `trigger_edges` forzando el orden). `compute_cut()` devuelve una clave nueva, `materialize_hops: list[tuple[str,str]]`. `split_ktr_by_cut()` — `_materialize_cut_hop()` nueva, agrega los steps/hops sintéticos a los sub_dicts correspondientes; el loop de "hop cruza grupos" (D45 punto 5) excluye los ya materializados, sigue igual para el resto (dangling genuino).

**Verificación:** `test_fragmentation.py` — el test de D45 (`test_compute_cut_self_lookup_same_component_now_reports_race`) se **invierte de nuevo** a `test_compute_cut_self_lookup_now_splits_via_materialization` (tercera inversión del mismo caso: D16 no partía → D45 pt.4 siempre error → D48 parte con materialización), documentado como tal; 2 tests nuevos confirman que el comportamiento D45 pt.4 se preserva exactamente para lo que D48 NO cubre (C1-bis con 2 writers; reader que no es ancestro); 1 test end-to-end contra `split_ktr_by_cut` verificando la forma exacta de los steps/hops sintéticos y que `infer_table_layer("etl_corte_1")` da `None` (no colisiona con Fase 2-ter/D53). Suite completa antes/después: 639→642 passed, mismos fallos preexistentes — cero regresión.

**Estado:** ejecutado (2026-07-30) para el patrón evidenciado (único writer, todos los readers ancestros). Cierra C.10 para ese alcance; el caso general de corte multi-par dentro de un componente queda sin evidencia de necesidad, no se construye (D6-bis).

<a id="d49"></a>
### D49 — C.11a resuelta: `PREFERRED_SCHEMA_NAME` obligatorio en toda `<connection>` emitida; C.11b (multi-schema completo) queda separada y abierta `[F4]`

**Contexto:** C.11 preguntaba si vale la pena hacer `schema` obligatorio end-to-end (`dim_contracts`, modelo de staging, DDL calificado, emisor, clave de la matriz). La investigación confirma en fuente que el riesgo de fondo (C-4, `search_path` no determinista) es real, y encuentra una palanca barata que no estaba en la mesa — lo que parte la pregunta en dos alcances de costo muy distinto.

**Evidencia:**

1. `DatabaseMeta.getQuotedSchemaTableCombination` — con `<schema/>` vacío **y** sin schema preferido en la conexión, Kettle emite el nombre de tabla pelado, sin calificación ni warning. `PostgreSQLDatabaseMeta` no interviene. **La resolución la hace íntegramente Postgres vía `search_path` de la sesión JDBC** — estado de servidor que no viaja en el `.ktr`/`.kjb`, irreproducible desde el artefacto. Confirma C-4 en fuente, no como sospecha.
2. **Palanca nueva:** `BaseDatabaseMeta.ATTRIBUTE_PREFERRED_SCHEMA_NAME` (`"PREFERRED_SCHEMA_NAME"`) — atributo de la `<connection>` (casilla *"Preferred schema name"* en Spoon, solapa Advanced). Cuando un step no trae `<schema>`, `getQuotedSchemaTableCombination` usa el preferido de la conexión **antes** de caer al nombre pelado.

**Decisión — partir C.11 en dos alcances de costo distinto:**

- **C.11a (esta decisión, resuelta): `PREFERRED_SCHEMA_NAME` obligatorio en el emisor de `<connection>`** (junto a lo que D34 ya gestiona ahí). Cero cambios en `dim_contracts`, modelo de staging, DDL, o steps individuales — el schema pasa a estar determinado por el artefacto en vez de por el `search_path` de quien ejecuta Spoon. Cierra el riesgo real y demostrado de C-4 al costo mínimo posible.
- **C.11b (queda abierta, sin decidir): `schema` obligatorio end-to-end** — `dim_contracts`, modelo de staging, DDL calificado, `<schema>` por step, clave de matriz `(connection, schema, table)`. Esto sí es DWH multi-schema real, alcance de producto separado que C.11a no fuerza a tomar ahora. Reemplaza a C.11 en `02-decisiones.md` §Abiertos.

**Caveat heredado de la investigación, no verificado:** no se confirmó en fuente si `PREFERRED_SCHEMA_NAME` también alcanza la introspección de metadatos (`getTableFields`, botón *SQL*) o solo la construcción de SQL de los steps (`getQuotedSchemaTableCombination`, que sí está verificado). No bloquea D49 — el camino de SQL de los steps es el que importa para el `.ktr` emitido — pero conviene confirmar antes de dar la implementación por completa.

**Estado:** ejecutado 2026-07-30. `_DEFAULT_SCHEMA_BY_TYPE` (`ktr_builder/connection.py`) mapea `POSTGRESQL`/`GENERIC` → `"public"`, `MSSQLNATIVE` → `"dbo"` — mismo default que `superset_export` ya asume para el DWH (no hay campo de schema por conexión en el contrato todavía, ver caveat de C.11b). `_build_connection()` agrega el atributo `PREFERRED_SCHEMA_NAME` a toda `<connection>` emitida, resuelta o placeholder, sin condicionar por tipo. Sin test dedicado nuevo — cubierto por la suite de fidelidad de conexión existente (`test_ktr_connection_golden.py`, `test_ktr_connection_resolution.py`), que sigue en verde. Suite completa antes/después: 646 passed / 54 failed en ambas corridas, mismo set preexistente (D26/D52) — cero regresión. Cierra C.11a; abre C.11b como su reemplazo en Abiertos.

<a id="d51"></a>
### D51 — R-K7: `scd_type==0` colapsa a 1 (Postura A), `InsertUpdate` descartado como loader de dimensión; ejecutado junto con D44 `[F4]`

**Contexto:** D44 dejó abierto qué step carga una dimensión `scd_type==0` — su punto 1 decía "colapsa a 1" en prosa, pero su punto 3 describía en paralelo un loader `InsertUpdate` con semántica SCD0 real, sin resolver la tensión entre ambos. El usuario mandó los dos textos a investigación aparte (R-K7) contra fuente real de Kettle antes de aprobar la implementación.

**Resuelto — Postura A, colapso 0→1:** Kettle no tiene Type 0 real. Ningún modo de atributo de `Dimension lookup/update` (`Insert`/`Update`/`Punch through` + 4 variantes de fecha) significa "no tocar si ya existe", y `dimUpdate()` reescribe TODAS las columnas de atributo con valor en el `SET`, sin filtrar por modo — la semántica de "sobrescritura" es indistinguible entre `scd_type` 0 y 1 en este step. `InsertUpdate` como loader de dimensión (la alternativa con semántica SCD0 fiel) se evaluó y se descartó explícitamente: exigiría emitir `update_bypassed=Y` (tag que el emisor no escribía en ningún caso, ver hallazgo lateral abajo), duplicar las claves naturales en `<value>` para que el INSERT las lleve, garantizar `version`/`date_from`/`date_to` por una vía distinta de la que usa el resto de dimensiones, renunciar a la creación automática de la fila `tk=0` (`checkDimZero`, exclusiva de `Dimension lookup/update`) y sostener una tercera rama de vocabulario — todo eso para una rama que es casi con certeza código muerto: la única regla mecánica que fuerza `scd_type=0` hoy (`classify_scd_candidates` regla 2, `domain/scd.py`) es la dimensión de calendario, y esa nunca la carga el ETL generado (K18, `system_etl.txt`).

**Decisión — vocabulario final:**
1. `derive_dimension_loader_step(scd_type)` → `"DimensionLookup"` para 0, 1 y 2 (una sola línea, sin rama por tipo).
2. `derive_attribute_update_mode(attr, attributes_scd1, attributes_scd2)` → `"Insert"` si `attr ∈ attributes_scd2`, si no `"Update"` — cubre 0 y 1 sin caso especial, porque para `scd_type==0` la inferencia declara sus atributos en `attributes_scd1` (nunca en `attributes_scd2`, que el schema reserva a `scd_type==2`).
3. **Guardarraíl (no estaba en el brief original, agregado en esta sesión):** el colapso 0→1 solo es seguro si la dimensión es de calendario — si el ETL no la carga, no hay pérdida de historial real. Si la inferencia declara `scd_type=0` en una dimensión que SÍ se carga, el colapso convertiría una garantía de inmutabilidad en sobrescritura silenciosa e irreversible. `_scd_zero_calendar_guard()` (`etl_generator.py`) reaplica el mismo predicado que usa la Parte 1 del pre-check (`is_calendar_dimension()`, extraído de `classify_scd_candidates` regla 2 a función nombrada — un único punto de definición) contra el DDL del DWH ya en mano en ese punto del pipeline: nombre de tabla + una sola clave natural + esa clave de tipo fecha en el DDL. Fuera de ese caso → `Finding` severidad error (D15: no aborta, el `.ktr` sale igual, pero el finding llega tipado — mismo patrón que D34/D46). **No se agregó `is_calendar` como campo nuevo del LLM** — los tres insumos del predicado ya están disponibles sin ampliar `INFERENCE_OUTPUT_SCHEMA`.
4. **Centinelas de rango, ítem que el brief pedía como "checker determinista del lado del backend" — revisado al implementar:** no es posible como validación de datos, porque el backend nunca ve filas reales (principio de diseño del proyecto: solo estructura llega al LLM, y tampoco hay lectura de datos de vuelta). Se implementó como texto de prompt más preciso en cambio: `K18` (`system_etl.txt`) ahora especifica los centinelas EXACTOS de Kettle (`1900-01-01 00:00:00` / `2199-12-31 23:59:59.999` / `version=1`) para cualquier calendario pre-poblado externamente, con la advertencia explícita de no usar `NOW()`/`CURRENT_TIMESTAMP`. Ver DDL-2 en `06-contrato-ddl.md`.
5. **`update_bypassed` — hallazgo lateral encontrado al leer `InsertUpdateMeta` para evaluar la Postura B, aplica independientemente de qué postura ganara:** `steps/output.py:_step_InsertUpdate` nunca emitía el tag `<update_bypassed>`; con ausencia de tag, Kettle asume `"N"`, y si TODOS los `<value>` de un `InsertUpdate` real (tablas de hechos, K10) quedan en `update="N"`, `prepareUpdate()` arma un `UPDATE ... SET` vacío y falla en runtime. Corregido: default seguro (bypass automático si no hay ningún value updatable) + `validators/insert_update_bypass.py` para la combinación explícita contradictoria.

**Nota de numeración:** el código de la sesión de Fase 0 (D46) usa `D50` en sus comentarios (`error_catalog_checks.py`, `fragmentation.py`, `build.py`, `etl_generator.py`, `validators/base.py`, `test_architecture_layers.py`) mientras este documento la registra como D46 — drift preexistente entre código y doc, no introducido por esta sesión. Se numera esta entrada `D51` (no `D50`) para no agravar la colisión; el drift D46/D50 queda registrado acá, sin corregir los 6 archivos (fuera de alcance de esta sesión — descubrir es libre, actuar necesita ruta).

**Verificación:** suite completa antes/después idéntica salvo lo nuevo (605→635 passed, mismos 54 fallos preexistentes de D26). Tests nuevos: `derive_dimension_loader_step(0)==derive_dimension_loader_step(1)`, canario de `ATTRIBUTE_UPDATE_TYPE_CODES` (typeCodes reales de `DimensionLookupMeta.getUpdateType()`), guard calendario vs. no-calendario, `check_dimension_lookup_fields`, `check_insert_update_bypass`, fidelidad de `<update_bypassed>` en tres escenarios. No verificado contra corrida real de Pentaho (Fase 4, fuera de esta sesión) — ver `04-verificacion.md`.

**Estado:** ejecutado, esta misma sesión (2026-07-30), junto con D44.

<a id="d52"></a>
### D52 — Fase 2-bis, mitigaciones 1+2: finding de consecuencia por dimensión + regla dura sobre columna monetaria en `attributes_scd2`; mitigaciones 3/4 quedan backlog explícito `[F4]`

**Contexto:** D44/R-K7 (D51) volvieron el step de carga de dimensión idéntico ("Dimension lookup/update") para todo `scd_type` — la Fase 2 sacó el síntoma visible de una misinferencia de `scd_type` (H44: no determinista sobre la misma entrada, medido por diff byte a byte entre corridas). D44/D51 registraron explícitamente que, sin la Fase 2-bis, el sistema pasa a producir errores semánticos indetectables en artefactos impecables — "no opcional respecto de la Fase 2" (03c:270). La Fase 2-bis define 4 mitigaciones (03c:168-176); el usuario decide en esta sesión arrancar solo con 1+2 (código puro, sin superficie de frontend nueva) y dejar 3 (confirmación explícita del usuario en el frontend) y 4 (medición de varianza, ya asignada a Fase 4) como backlog explícito — no se implementan acá.

**Decisión — dos funciones nuevas en `etl_generator.py`, operan solo sobre `dim_contracts` (sin DDL, a diferencia de `_scd_zero_calendar_guard`):**

1. **Mitigación 1 — `_scd_consequence_findings(dim_contracts)`:** un mensaje por dimensión con la consecuencia concreta del `scd_type` elegido, no solo el número — "`dim_producto` cargada como SCD2: cada cambio en {attrs} genera una versión nueva" / "cargada como SCD1: cambios en {attrs} sobrescriben el valor anterior". `scd_type==0` queda afuera (la rama no-calendario ya la señala `_scd_zero_calendar_guard` como error; la calendario no tiene atributo que cambie). Mensajes planos, sin prefijo — entran al canal de `advertencias_buenas_practicas` (mismo canal que el resto de notificaciones no bloqueantes de este módulo, `cfg_warnings`/`inferred_member_warnings`/etc.), no se creó un tipo `Validacion(tipo="info")` nuevo por dimensión para mantener el blast radius mínimo.
2. **Mitigación 2 — `_monetary_scd2_guard(dim_contracts)`:** columna de importe/monto (`error_catalog_checks.MONEY_FIELD_HINTS`, misma señal que `v11_monetario_sin_bignumber`) en `attributes_scd2` es error — un valor monetario cambia con cada transacción, no es lentamente cambiante, y pertenece al hecho, no a la dimensión (cierra B-7). `attributes_scd1` no se chequea — ahí el atributo se sobrescribe, no se versiona, y B-7 es específico de versionar un monto. `PRE_EMIT_ERROR_PREFIX` (mismo mecanismo que `_scd_zero_calendar_guard`) — `_split_integrity_warnings` promueve a `Validacion(tipo="error")`, D15: no aborta, el `.ktr` sale igual.

**Wiring — los 4 caminos que ya tenían `dim_contracts` disponible, sin necesitar DDL (a diferencia de `_scd_zero_calendar_guard`, que si lo necesita y por eso no está en `build_etl_from_raw`):** flujo síncrono de 2 llamadas (`extra_warnings` del `_build_response_from_two_ktr_data`), flujo async (`_try_build`/`repair_warnings` persistido en `job.model_json`), y las dos ramas de `build_etl_from_raw` (dos-KTR y legacy monolítico) — este último no corría `_scd_zero_calendar_guard` por falta de DDL, pero sí puede correr estas dos mitigaciones nuevas.

**Explícitamente fuera de esta decisión:**
- **Mitigación 3** (confirmación explícita del usuario del `scd_type` propuesto y el reparto `attributes_scd1`/`attributes_scd2` antes de generar) — decisión de diseño del DWH, requiere superficie de frontend nueva. Queda backlog de F4, evaluar contra alcance en sesión aparte.
- **Mitigación 4** (medición de varianza, N corridas de la misma entrada) — ya asignada a Fase 4 en 03c (03c:175), no se adelanta acá.

**Verificación:** `test_scd_consequence_and_monetary_guard.py` (18 tests nuevos, unitarios sobre las dos funciones, mismo patrón que `test_scd_zero_calendar_guard.py`). Suite completa antes/después: 646 passed, mismos 54 fallos preexistentes (D26), cero regresión.

**Estado:** ejecutado, esta misma sesión (2026-07-30).

<a id="d53"></a>
### D53 — Fase 2-ter ejecutada: `FilterRows` de saneamiento exigido por CHECK del DDL + guard determinista de capa staging `[F4]`

**Contexto:** `03c-investigacion-vocabulario-dimension-kettle.md` (Fase 2-ter) dejó dos backstops deterministas sin implementar, señalados como "baratos e independientes" y recomendados antes de D45 Sesión B: S-4/H45 (dos corridas del mismo caso validaron cada una solo 1 de 3 columnas con CHECK de rango, y una columna distinta cada vez — error de completitud sistémico, no de modelo) y S-5/H-5 (Set B crudo filtró precios negativos en `origen->staging`, rompiendo el contrato truncate+load — D42 ya sacó la regla del prompt, esto es el backstop que no depende de que el modelo la respete).

**Decisión — dos passes pre-emisión nuevos (`ktr_builder/validators/`), mínimo aceptable de cada uno (no full synthesis, D6-bis):**

1. **`check_constraint_filter_rows` (S-4).** `ValidationContext` gana un campo nuevo, `dwh_constraints: dict[str, dict[str, dict]]` (plain dict, no `FieldConstraints`/pydantic — `validators/base.py` es `DOMAIN_MODULES`, no puede importar `schemas.canonical`), poblado por `etl_generator._dwh_column_check_constraints(dwh_ddl)` (mismo patrón que `_column_types_from_ddl`, reusa `parse_ddl`+D43) solo para columnas con `minimum`/`maximum` no ambos `None`. El pass: para cada writer (`TableOutput`/`InsertUpdate`/`Update`/`DimensionLookup` en rol loader) cuya tabla tiene columnas acotadas, exige un `FilterRows` en el MISMO KTR sobre el campo de stream que alimenta esa columna — presencia plana, no reachability por hops (mínimo aceptable: el caso que motiva esto son steps de una sola etapa, sin ramas cruzadas materializadas todavía). Si el `FilterRows` existe pero su `value_type='String'` contra una columna `integer`/`number`, error aparte — cierra la mitad de A-5 (constante `String` vs campo numérico).
2. **`guard_staging_layer` (S-5).** A diferencia del anterior, SÍ usa reachability (dirigida, vía hops) — reusa `build_rw_matrix` para encontrar writers de tablas `staging` (`domain/table_layer.py`, ver abajo) y ancestros de ese writer para encontrar un `FilterRows` que lo alimente. Vocabulario tomado literal de D42: staging es "copia estructural completa", cualquier `FilterRows` que llegue a un writer de staging es presuntamente una regla de negocio fuera de lugar.
3. **`domain/table_layer.py` nuevo** — `infer_table_layer()`, extracción de `_STAGING_PREFIXES`/`_DWH_PREFIXES` desde `ktr_builder/connection.py` (que pasa a importarla) para que el guard y la inferencia de conexión real lean la MISMA lista. Adelanta parte de lo que D45 punto 2 (Sesión B, esta misma sesión) iba a necesitar de todos modos — ver esa entrada.

**Wiring:** ambos passes se agregan a `PRE_EMIT_PASSES` (`validators/__init__.py`). `_dwh_column_check_constraints` se calcula una vez por invocación de `_recover_table_keys`/`_stage_pipeline` en los 3 call sites que ya tienen `dwh_ddl` disponible (mismo criterio best-effort que el resto de `etl_generator.py`: sin DDL, `{}`, los passes no-opean).

**Verificación:** `test_check_constraint_filter.py` (7 tests), `test_guard_staging_layer.py` (5 tests) — puros, sin LLM/DB, mismo patrón que `test_dimension_lookup_fields.py`. Suite completa antes/después: 637→650 passed (dentro de la sesión completa D53+D45 Sesión B+D48), mismos fallos preexistentes — cero regresión.

**Estado:** ejecutado (2026-07-30). Cierra la Fase 2-ter de `03c-investigacion-vocabulario-dimension-kettle.md`.

<a id="d54"></a>
### D54 — Fase 4, corrida real: resultado parcial, análisis de la única corrida completa (sonnet) `[F4]`

**Contexto:** `03c-investigacion-vocabulario-dimension-kettle.md` § Fase 4 (líneas 209-227) pide correr con 2+ modelos y N corridas por modelo (S-12), sobre el mismo caso de entrada, para medir invariancia. `docs/refactor/fase4_manual/notas.md` ya documentaba de antemano que esta ronda es parcial: sin crédito Gemini, sustituto Sonnet/Haiku (Anthropic), mismo proveedor — no prueba invariancia cross-proveedor, riesgo aceptado explícito.

**Qué hay en `docs/refactor/fase4_manual/` (verificado archivo por archivo, confirmado por el usuario):**
- **Haiku: 0 corridas completas.** `haiku/Error al Inferir.txt` — la inferencia de estructuras (`stg_ddl`/`dwh_ddl`) falló contra el modelo `claude-haiku-4-5` con un schema de 7 campos + array anidado de 11 campos c/u. No es bug de orden de llamadas — es la falta de garantía dura de structured output que sí tiene Gemini, más visible en un modelo chico con schema grande. `etl-skeleton-test-01_haiku_fase4.json` es solo el caso de entrada exportado antes del intento (mismo `type: "etl_skeleton"` que `skeleton_test_01.json`, la plantilla original de caso de entrada, 2026-07-13), no un resultado.
- **Sonnet: 1 corrida completa** (`sonnet/etl-llm-raw-test-01_sonnet_fase4.json`, tipo `etl_llm_raw`, salida cruda del LLM antes de fragmentación) + artefactos finales ya fragmentados (`JOB-principal.kjb`, `KTR-origen-staging.ktr`, `JOB-stg-dwh.kjb`, `stg_dwh/KTR_1_stg_dwh_*.ktr`, `stg_dwh/KTR_2_stg_dwh_*.ktr`, `test-01_sonnet_fase4_ktr.zip`).

**Tabla modelo × corrida × dimensión × `scd_type` (única corrida disponible):**

| Modelo | Corrida | Dimensión | `scd_type` declarado (dim_contracts / validaciones) | `scd_type` real en el `.ktr` emitido |
|---|---|---|---|---|
| Sonnet | 01 | `dim_categoria` | 1 | 1 — `Cargar dim_categoria` sale con `update="Y"`, coherente |
| Sonnet | 01 | `dim_producto` | 1 | **Inconsistente** — `Cargar dim_producto` sale con `update="N"` (solo-lectura, nunca inserta/actualiza), pese a que el propio texto de `validaciones` del mismo JSON declara SCD1 para ambas dimensiones. Ver H51 |
| Haiku | — | — | — | Sin datos, corrida no llegó a generar ETL |

**Varianza dentro del mismo modelo:** no evaluable — 1 sola corrida sonnet, 0 corridas haiku completas. El criterio real de S-12 ("más de una corrida por modelo — el output es no determinista y una muestra no distingue 'arreglado' de 'salió bien esta vez'") **no se cumple todavía**.

**Otros puntos del criterio de cierre de Fase 4, verificados contra esta corrida:**
- **Corte STG→DWH dio 2 archivos:** sí — `stg_dwh/KTR_1_stg_dwh_*.ktr` (solo `dim_categoria`) y `stg_dwh/KTR_2_stg_dwh_*.ktr` (`dim_producto` + `fact_inventario`), orquestados en orden por `JOB-stg-dwh.kjb`. El corte separó `dim_categoria` porque `dim_producto`/`fact_inventario` la vuelven a leer (lookup de FK) — evidencia de que el corte dispara por dependencia real, no solo por el umbral `scd_type` 2 que motivó A-3 originalmente (acá ambas dimensiones son SCD1 y igual cortó).
- **Ninguna `Validacion(tipo="error")`:** cierto en las dos etapas del JSON crudo (todo `info`/`warning`) — pero no por ausencia real de errores: el bug de H51 (`update="N"` en un loader) no tiene checker que lo detecte, así que "cero errores" acá es un negativo no verificado, no una garantía.
- **`contract_validate` (D38) atrapando A-4:** no evaluable con lo disponible — necesitaría inspeccionar el `.ktr` de origen→staging contra el de stg→dwh por nombre de columna, fuera del alcance de este análisis (ya lo cubre la suite de tests, D38 ejecutado).

**Hallazgo nuevo derivado de esta corrida:** H51 — `enforce_dimension_step_policy` y `check_dimension_lookup_fields` no verifican el flag `update` de un `DimensionLookup` en rol loader (solo lo hacen para rol `fact_lookup`), así que un loader mal configurado como solo-lectura pasa sin ningún finding. Abierto, sin dueño de track.

**Estado:** parcial (2026-07-31). F4 sigue "en curso" — falta al menos 1 corrida más de sonnet (mismo caso), retomar Haiku con un caso más chico o esperar crédito Gemini para cumplir S-12, y decidir dueño para H51.

<a id="d55"></a>
### D55 — Plan de reparación del generador ETL (8 ítems): vocabulario `<field><update>` por modo sin condición de vacío, semilla `tk=0` sintetizada en el DDL (alineada con D47), escala monetaria desde el DDL `[F4]`

**Contexto:** sesión de planificación (no de investigación — el diagnóstico de los 8 defectos venía cerrado de una auditoría externa al repo, no re-investigado en esta sesión) sobre defectos confirmados en el generador: vocabulario cruzado en `<field><update>` de `DimensionLookup` (mismo síntoma que H51, abierto desde D54, sin dueño de track hasta ahora), `ConcatFields` con tag inexistente en el formato real de Kettle (`<extra_field>` en vez de `<ConcatFields><targetFieldName>`), suite de tests que valida contra el fixture-golden usado como input en vez de generar y comparar la salida real de `build_ktr()`, ausencia de sembrado determinista de la fila `tk=0` (evidencia: cero resultados de `seed`/`ON CONFLICT` en `app/services`), narración del modelo sin contra-chequeo contra el XML emitido, dos checkers incompletos (`check_constraint_filter_rows` no compara el valor contra el bound del CHECK; `guard_staging_layer` no mira la proyección SQL de `TableInput`/`ExecSQL`), y escala `BigNumber` sin longitud/precisión. Los identificadores P1-x/P2-x/P3-x/V-x/NUEVA-x usados durante la sesión vienen de un análisis externo a este repo (no están en `01-hallazgos.md`, salvo H51 que D54 ya había dejado abierto) — se listan acá por trazabilidad de la sesión, no como referencia a hallazgos ya indexados en este archivo.

**Decisión — plan de 8 ítems, confirmado por el usuario tras dos rondas de revisión.** La primera versión del plan reintroducía, en tres ítems distintos, la misma clase de defecto que venía a reparar — un default silencioso ante un valor que no se conoce. Corregido antes de confirmar:

1. **Vocabulario `<field><update>` de `DimensionLookup` seleccionado por modo del step, sin ninguna condición sobre si `fields` está vacío.** La primera versión proponía "fields no vacío en modo N = error" — refutada contra `DimensionLookupMeta.java` (`pentaho/pentaho-kettle`, `master`: `getFields()` 741-820, `actualizeWithInjectedValues()` 564-569, `readData()` 930-937, `readRep()` 995-1000). En modo N (`update=N`, rol lookup/fact_lookup, D16), `fields` es el mecanismo real de retorno de columnas adicionales del lookup — uso legítimo, no residuo de cuando el step era loader; bloquearlo además impide la deduplicación de lookups que quedó anotada como mejora posible. Regla final (D-1): modo Y → vocabulario `ATTRIBUTE_UPDATE_TYPE_CODES` (ya en `domain/scd.py`); modo N → vocabulario `ValueMetaFactory` (constante nueva, `VALUE_META_TYPE_NAMES`, lista completa pendiente de verificar contra fuente antes de mergear — mismo tipo de verificación que el ítem 4 necesita para el formato de `JOBENTRYSQL`, ver abajo). El validador pre-emisión (`dimension_lookup_fields.py`) reporta error ante vocabulario cruzado; el emisor (`lookups.py`) levanta `KtrBuilderError` — no hay fallback silencioso a "Insert" — usando el mismo precedente que ya existe en `build.py:376-385` para step-type no soportado (un `.ktr` mal formado es peor que uno que no se genera), aplicado acá porque el costo de emitir en silencio (dimensión quedando en modo Insert-siempre, SCD2 no pedido) es del mismo orden. **Cierra H51** (D54) — pasa a tener dueño de track.
2. **`ConcatFields` reescrito al formato real** (`<ConcatFields><targetFieldName>/<targetFieldLength>/<removeSelectedFields>` anidado, no `<extra_field>` suelto), confirmado contra el fixture del propio repo (`golden_run_base_01/ktr_1_origen_a_staging.ktr:951-955`).
3. **Suite nueva que genera vía `build_ktr()` en vez de consumir el golden como input.** No existe en el repo un `ktr_data` de entrada que reproduzca `golden_run_base_01` (son captura de una corrida real, sin companion) — comparar byte-a-byte contra ese fixture específico no es viable sin ingeniería inversa. Se usa un fixture nuevo y mínimo, diseñado para ejercitar los casos de los ítems 1 y 2, en vez de forzar el golden existente. `test_golden_run_base_01_zero_findings` (ya existente, válido para lo que valida) no se toca.
4. **Semilla `tk=0`: el mecanismo NO reabre D47.** La primera versión de este ítem proponía una entry `JOBENTRYSQL` nueva en el `.kjb` — exactamente el mecanismo que D47 ya evaluó y descartó explícitamente ("agrega un segundo escritor sobre la dimensión... obligaría a garantizar orden respecto del loader, costo que el sembrado en DDL no tiene"). Corregido antes de confirmar: el mecanismo sigue siendo el de D47 (INSERT embebido en el DDL). Lo que este ítem agrega es la pieza que D47 dejó abierta sin marcarla como tal — el sembrado depende hoy al 100% de que el LLM seleccionado siga la instrucción de `prompt_validacion_src.txt` (I8/V5); no hay verificación determinista de que el INSERT realmente llegó al DDL final (`validate_and_correct_ddl()`, `ddl_validation.py`, es también una llamada al modelo, no una síntesis de código). Se agrega un pass posterior a `validate_and_correct_ddl()` que sintetiza el INSERT en el texto del DDL final cuando no está — determinista, sin tocar `.ktr`/`.kjb`, sin agregar un segundo escritor. Bloqueo de fuente pendiente, no de decisión: el formato exacto de `JOBENTRYSQL` ya no aplica (mecanismo descartado); no queda gap de fuente en este ítem.
5. **Contra-chequeo narración↔XML** — pass nuevo que cruza afirmaciones de `validaciones`/`advertencias_buenas_practicas` del modelo contra `cfg["update"]`/vocabulario real del step correspondiente en el `.ktr` emitido.
6. **`check_constraint_filter_rows` compara el valor de la constante contra el bound del CHECK**, no solo la presencia de un `FilterRows` con operador de la familia correcta — gap confirmado por lectura directa del checker antes de planificar sobre él.
7. **`guard_staging_layer` detecta transformación en la proyección SQL** (`CASE`/`NULLIF`/`COALESCE`/aritmética, vía `sqlglot` — ya dependencia del repo, `requirements.txt:119`, verificado contra la versión instalada `30.8.0` con el caso real), no `WHERE`. La primera versión de este ítem proponía una heurística `\bWHERE\b`, que no detecta el caso que motivó la sección (`CASE WHEN` en la proyección, sin `WHERE`) y dispara falsos positivos sobre filtros técnicos legítimos (fecha, tenant, flag de activo).
8. **Escala `BigNumber` tomada de `CanonicalField.precision`/`.scale`** (ya poblados por `ddl_adapter.py` desde el DDL — extracción existente, no nueva) en vez de un default fijo. La primera versión de este ítem defaulteaba a `18,2` ("precedente estándar de columna monetaria") — rechazado por ser exactamente el defecto que el ítem viene a cerrar, con un número más plausible que `-1` pero igual de inventado por columna. Corregido: nuevo campo `ValidationContext.dwh_numeric_scale` + pass pre-emisión que repara desde el DDL cuando resuelve por nombre de columna, y deja error (sin fabricar nada — el XML sigue mostrando `-1,-1`) cuando no. Confirmado explícitamente para este ítem: un finding `severity="error"` de un pass pre-emisión **no bloquea la entrega** (`validators/base.py:9-12`, D15 — "notifica, no bloquea"; `build.py:163-174` no usa esos findings para abortar) — a diferencia del `KtrBuilderError` del ítem 1, que si bloquea (capa distinta, el emisor, no el validador).

**Plan completo (archivos, funciones, código propuesto, criterio de aceptación sobre el XML por ítem, dependencias entre ítems) fuera de este archivo por volumen — documento de sesión, no append-only.** Esta entrada registra la decisión, su razonamiento y las tres correcciones que la sesión de revisión forzó — no duplica el detalle de implementación línea por línea.

**Nota (2026-08-01):** el detalle completo se movió a `docs/refactor/plan-reparacion-etl.md` (antes vivía fuera del repo, en Desktop, mientras el usuario lo revisaba). Mutable, no append-only — el usuario confirmó que va a explorar al menos un punto abierto en sesión aparte y, de corresponder, impactarlo ahí directamente en vez de en esta entrada.

**Estado:** ítems 1-3 ejecutados (2026-08-01); 4-8 planificados, no ejecutados. Ítem 1: `domain/scd.py` (`VALUE_META_TYPE_NAMES`), `dimension_lookup_fields.py` (vocabulario por modo Y/N, sin condición de `fields` vacío), `steps/lookups.py` (un solo tag `<update>` por field, `KtrBuilderError` en vocabulario cruzado), `dimension_step_policy.py` (rama nueva: loader con `update=N` reparado a `Y`, override respetado — cierra H51). Ítem 2: `steps/transform.py` `_step_ConcatFields` reescrito al formato real (`<ConcatFields><targetFieldName>/...` anidado tras `<fields>`), confirmado contra `golden_run_base_01/ktr_1_origen_a_staging.ktr:951-955`. Ítem 3: `test_build_ktr_emission.py` nuevo (parsea XML real de `build_ktr()`, no el golden como input) + 2 tests nuevos en `test_dimension_step_policy.py`. Verificación: `pytest tests/test_dimension_step_policy.py tests/test_build_ktr_emission.py tests/test_dimension_lookup_fields.py` — 28 passed. Suite completa: 695 passed / 33 failed, mismo set preexistente confirmado por `git stash` (sin relación con estos 3 ítems) — cero regresión. Ítems 4-8 quedan para sesión(es) aparte — ver "Pendientes concretos de F4" en `03-plan.md`.

<a id="d56"></a>
### D56 — Ítem 5 (contra-chequeo narración↔XML): implementado con limitación conocida. Se registra el alcance real y la alternativa pendiente.

Estado: decidido. Complementa el ítem 5 de D55, no lo revierte.

Qué quedó implementado en la tanda C: el renombrado del canal
(etl_generator.py:825, la prosa del modelo pasa a `narracion_modelo`) y
narration_crosscheck.py, que cruza afirmaciones sobre el modo de un
DimensionLookup contra el XML emitido, vía regex de patrón acotado sobre
la narración en español del modelo.

Limitación conocida, registrada a propósito. Un regex que no matchea
produce cero findings, indistinguible de "narración consistente". El falso
negativo es invisible — el mismo modo de falla de V-1, que este ítem venía
a reparar. Es la cuarta instancia de la clase de defecto que las
revisiones 2, 5 y 6 del plan corrigieron en otros ítems bajo D5 y D45
pt.1; sobrevivió porque su forma es un regex y no un `return` mudo.

Mitigación aplicada. El pass declara su cobertura real: Finding
severity="info" al cierre, con "N/M step(s) DimensionLookup cruzados
contra alguna afirmación de la narración". Con cobertura 0 el mensaje dice
explícitamente que "sin hallazgos" significa "no verificado", no
"narración consistente". Severidad "info" y no "error"/"warning":
"error" sería falso positivo sistemático en todo KTR sano cuya narración
no mencione el modo, y "warning" sugeriría una reparación que este pass no
hace; precedente en el branch de override de dimension_step_policy.py.
No convierte al pass en confiable — lo hace honesto sobre cuándo no lo es.

Punto ciego residual, no corregido. Si la narración afirma algo sobre el
modo de una dimensión y el artefacto no tiene NINGÚN step DimensionLookup,
el pass devuelve lista vacía: el mismo falso negativo, del lado inverso.
No se repara acá — es munición para la inversión, no un fix puntual más.

Qué NO se hizo y queda abierto para D. La inversión: derivar el informe de
validación del XML emitido, determinísticamente, y que la prosa del modelo
nunca sea fuente de una aserción de validación. No se construye ahora
porque falta contexto sobre el consumo del informe (quién lo lee, para
qué, qué hace con él). Registrado como GAP-2 en prompt-sesion-D.txt, Q1.
Si D adopta la inversión, narration_crosscheck.py se retira; no se
extiende ni se generaliza el regex mientras tanto.

Procedencia. La objeción venía de la revisión del plan C y quedó anotada
únicamente en prompt-sesion-D.txt, fuera del repo — por eso el plan
conservó el alcance viejo y el pass se implementó igual. Tercera instancia
del mismo patrón: D47 (decisión cerrada ausente del contexto),
system_etl.txt:369 (convención que solo vive en el prompt del modelo).
Regla derivada: toda restricción de alcance sobre un ítem del plan se
registra en este archivo, no en un prompt de sesión.

<a id="d57"></a>
### D57 — Reclasificación a fact_lookup: se limpia `fields`, no se conserva.

Estado: decidido, aplicado en el mismo turno.

Problema. `enforce_dimension_step_policy`, branch rol=fact_lookup con
canonical ya DimensionLookup (dimension_step_policy.py:274-283): hacía
`new_cfg = dict(cfg); new_cfg["update"] = "N"` — pisaba el flag y dejaba
`fields` intacto. Un step que el LLM generó como loader (update=Y, fields
con vocabulario Y: Insert/Update/...) y que la policy reclasifica a
fact_lookup quedaba con modo N + vocabulario Y. Vocabulario cruzado, que
el emisor rechaza con KtrBuilderError desde el ítem 1(b) de D55.
Reproducido en la corrida post-C: "DimensionLookup 'Cargar dim_producto':
campo con type='Update' fuera del vocabulario de modo N".

Por qué se escapó — el hallazgo de proceso. El punto estaba anotado en
plan-reparacion-etl.md §1(c) línea 113 como "nota, no bloqueo". Esa
clasificación era correcta cuando se escribió: bajo el régimen anterior el
vocabulario cruzado producía un .ktr que abría igual, con semántica
silenciosamente incorrecta. El ítem 1(b) del MISMO plan convirtió esa
condición en un gate duro. Un ítem del plan invalidó la severidad asignada
por otro ítem del plan, en secciones distintas, sin que nadie lo notara.
Regla derivada: cuando un ítem agrega un gate duro, se revisan las notas
"no bloqueo" del resto del plan que dependan de que esa condición sea
tolerada.

Decisión. En ese branch, `new_cfg["fields"] = []` más un Finding con
repaired=True que registre cuántas entradas se descartaron y por qué.

Fundamento — `fields` vacío en modo N es la forma correcta, no un
degradado. DimensionLookupMeta.getFields() 776-803 guarda el recorrido con
`if (!update && fieldLookup.length > 0)`: en modo lookup, `fields` es un
mecanismo OPCIONAL de columnas extra ("retrieve extra fields on lookup?",
comentario del fuente). La technical key —lo único que un hecho necesita
de la dimensión— viaja por su propio mecanismo, no por `fields`. Y las
entradas que se descartan no son columnas de retorno: son modos de
actualización escritos bajo la premisa de que el step era el loader,
premisa que la resolución topológica de rol acaba de declarar falsa.
Conservarlas traducidas (opción evaluada y descartada) presupondría que
querían ser columnas de retorno, que es exactamente lo que no consta.

Descartado: traducir el vocabulario Y-mode a value-meta real vía contrato
/DDL. Requiere un mapeo tipo-DDL → ValueMetaFactory que hoy no existe, y
resuelve un problema del que no hay evidencia.

Test. test_enforce_dimension_step_policy_forces_readonly_on_fact_lookup_scd2
(test_dimension_step_policy.py:224-238) solo verificaba update=="N", nunca
`fields` — pasaba en verde con el defecto adentro. Se extiende para
verificar el vaciado y el Finding.

Queda abierto, sin cambios. El origen de columnas de retorno legítimas
para un fact_lookup en modo N (P3-1, deduplicación) sigue sin definir.
Cuando se planifique, ahí se decide de dónde salen esos `fields` — no acá,
y no reciclando config escrito para otro rol.

<a id="d58"></a>
### D58 — role_of_dimension_step: BFS solo desambigua con 2+ candidatos; already_readonly valida vocabulario.

Estado: decidido, aplicado en el mismo turno.

Problema. D57 no alcanzaba la corrida real (etl-llm-raw-test-01_sonnet_
fase4.json): 'Cargar dim_producto', único `DimensionLookup` sobre
`dim_producto`, llega del LLM con `update="N"` y `fields` en vocabulario Y
— contradice su propia narración ("update=Y y todos los atributos en modo
Update"). El step alimenta, vía hop, `Cargar fact_inventario`
(`InsertUpdate`, tabla distinta) — patrón normal (el loader devuelve su SK
y esa misma rama sigue hacia el hecho, sin un segundo step dedicado a FK).
`role_of_dimension_step` (D16/H21) hace BFS hacia adelante y, al alcanzar
un escritor de otra tabla, concluye `"fact_lookup"` — sin mirar si hay
OTRO step candidato para `dim_producto`. Clasificado mal, cae en el branch
D57 (ya arreglado, limpia `fields`), que fuerza `update="N"` — pero el
step YA estaba en `update="N"`, así que `already_readonly`
(`dimension_step_policy.py:342-345`, antes de este fix) cortaba con
`continue` mudo sin validar `fields` contra el vocabulario de modo N —
mismo defecto de clase que el `continue` de H51. El crash sobrevivía.

Verificación previa a escribir la regla (pedida antes de implementar): ¿un
lookup de solo lectura contra una dimensión cargada en OTRO `.ktr` podría
hacer que "contar candidatos en este `ktr_data`" clasifique mal un
lookup huérfano como loader? Confirmado que NO en el pipeline actual:
`enforce_dimension_step_policy` corre siempre sobre el dict COMPLETO de
una sola etapa (KTR_2, STG→DWH) — tanto en el flujo síncrono
(`etl_generator.py:1392`) como en `build_etl_from_raw`
(`etl_generator.py:1150-1160`) — ANTES de que `compute_cut()`/
`split_ktr_by_cut()` fragmente esa etapa en N archivos físicos
(`_build_response_from_two_ktr_data`/`_build_ktr_stage`, llamadas
DESPUÉS). KTR_1 (origen→STG) nunca tiene steps de dimensión — las
dimensiones solo se cargan en KTR_2. Y `DimContract`
(`schemas/etl_schemas.py:145-162`) no tiene ni necesita un campo de
alcance/archivo: es puramente descriptivo del contrato SCD, y hoy no
existe ningún mecanismo de dimensión compartida entre ETLs distintos. El
supuesto se sostiene — se implementa el conteo tal cual, sin ese guardia
adicional.

Riesgo distinto, encontrado en la misma verificación y NO cerrado por
este fix: si el LLM omite por completo el loader de una tabla que sí
declaró en `dim_contracts`, el único step que quede sobre esa tabla (un
lookup de solo lectura huérfano) también cuenta 1 candidato, y esta regla
lo forzaría a loader — ningún campo disponible hoy distingue "único
candidato porque es inequívocamente el loader" de "único candidato porque
al loader real le falta su contraparte". No es el caso de la corrida real
(ahí el step SÍ es el loader — trae los 6 atributos de negocio de la
dimensión en `fields`) y excede el alcance de este fix. Señalado en el
código (`_dimension_step_table_counts`, docstring) para quien lo
encuentre.

Decisión — dos cambios en `dimension_step_policy.py`:
1. `_dimension_step_table_counts()`: precomputa, una vez por llamada a
   `enforce_dimension_step_policy`, cuántos steps `DimensionLookup`/
   `CombinationLookup` targetean cada tabla. Si el conteo para la tabla de
   un step es ≤1, `role="loader"` directo, sin invocar el BFS — no hay
   ambigüedad que desambiguar (D16/H21 diseñó el BFS para el caso de 2+
   candidatos; aplicarlo con 1 solo era sobre-aplicar la heurística fuera
   de su alcance original).
2. `already_readonly` (branch fact_lookup, step ya en `update="N"`): antes
   de dar el step por bueno con `continue`, valida cada `fields[i].type`
   contra el vocabulario de modo N (`VALUE_META_TYPE_NAMES`). Si hay
   alguno fuera de vocabulario, agrega un finding `tipo="error"` — no
   repara (no hay contrato para inventar qué hacer con columnas de retorno
   legítimas en modo N, mismo principio D5/D45 pt.1 que los ítems 7/8 del
   plan) pero deja de ser un `continue` mudo.

Con (1), la corrida real cae en el branch H51 (ya existente, ya probado):
se corrige a `update="Y"` y se resintetiza `fields` desde `dim_contracts`
— sin crash. (2) cierra el defecto de clase para el próximo fact_lookup
genuino con vocabulario cruzado que (1) no reclasifica (porque si tiene
2+ candidatos, sigue yendo por BFS).

Test. `test_single_dimension_lookup_step_per_table_resolves_loader_not_
fact_lookup` y `test_already_readonly_fact_lookup_with_crossed_vocabulary_
reports_error` (`test_dimension_step_policy.py`);
`test_single_step_per_table_reproduction_d58` (`test_build_ktr_emission.py`,
extremo a extremo contra `build_ktr()`, reproducción literal del payload
real). `test_policy_reclassified_fact_lookup_does_not_emit_crossed_
vocabulary` (D57) se ajustó agregando un segundo step candidato — con 1
solo, (1) hace que ya no ejercite el branch fact_lookup que D57 arregló.

Narración vs. artefacto (nota, no acción). El payload real mostró al LLM
narrando `update=Y` para `dim_producto` y emitiendo `update=N` — el caso
exacto que `check_narration_crosscheck` (item 5, plan) existe para
atrapar. No disparó: el `campo` de la narración llegó compuesto
("dim_categoria / dim_producto", "dim_producto.fk_categoria") en vez del
nombre exacto de tabla que el pass compara con `==` estricto — 0/2 steps
cruzados, solo el finding de cobertura "no verificado". No se toca
`narration_crosscheck.py` en este turno (instrucción explícita) — queda
anotado como limitación real de su matching por igualdad exacta.

<a id="d59"></a>
### D59 — O1, lote E-04…E-08: 5 steps de emisión corregidos contra `readData()` real de Kettle `[O1]`

Estado: decidido, ejecutado, mismo turno.

Alcance. Cierra el "lote barato" de `10-estabilizar-emision.md` (E-04
StringOperations, E-05 Unique, E-06 ExcelInput, E-07 JsonInput, E-08
TextFileOutput) — los ítems 3, 5, 6, 7 y 8 de
`investigacion-tags-validos-por-step.md` § A. Quedan fuera, a propósito:
E-09 (`CombinationLookup`, falta el bloque `<fields><return>`) y E-10
(`DataValidator`, mapeo `name`/`fieldname` invertido) — estructurales,
más caros que 1-3 líneas, sesión aparte de O1 (E-11, `SplitFieldToRows`,
tampoco entra: es un problema de alias→`<type>` en `step_types.py`, no de
un builder de `steps/*.py`).

Método. Cada fix se verificó leyendo `readData()`/`getXML()` real de la
clase `*Meta.java` en `github.com/pentaho/pentaho-kettle` (rama
`master`), citando clase y método — la autoridad que exige
`docs/README.md` § "Autoridad sobre comportamiento de Pentaho". Un
commit por step, cada uno con test propio contra la salida real de
`build_ktr()` (patrón de `test_build_ktr_emission.py`, no fixtures
consumidas como input).

1. **StringOperations** (`steps/transform.py:_step_StringOperations`,
   commit `d0a79b9`) — `StringOperationsMeta.readData()` lee
   `trim_type`/`lower_upper` como los literales `none/left/right/both` y
   `none/lower/upper`; el emisor escribía índices numéricos (`"0".."3"`),
   que nunca matchean — el step no recortaba ni cambiaba
   mayúsculas/minúsculas con ninguna configuración. Corregido a los
   literales; `"title"` (no existe como código real de `lower_upper`) se
   resuelve vía el flag `init_cap`, independiente en Kettle.
2. **Unique** (`steps/transform.py:_step_Unique`, commit `3194463`) —
   `UniqueRowsMeta.readData()` lee `case_insensitive` (ausente = `true`,
   siempre case-insensitive); el emisor escribía `case_sensitive`,
   inexistente, con la polaridad invertida. Corregido a `case_insensitive`
   con la polaridad real.
3. **ExcelInput** (`steps/input.py:_step_ExcelInput`, commit `58d4e89`) —
   `ExcelInputMeta.readData()` parsea `spreadsheet_type` vía
   `SpreadSheetType.valueOf()` dentro de un try/catch que cae a `JXL`
   (motor legado, no lee `.xlsx`) ante tag ausente o no reconocido; el
   emisor nunca lo escribía. Corregido: se emite por extensión de archivo
   (`.xls`→`JXL`, cualquier otro caso→`POI`, que lee Excel 2007+). Valores
   reales del enum confirmados en `SpreadSheetType.java`: `JXL`, `POI`,
   `SAX_POI`, `ODS`.
4. **JsonInput** (`steps/input.py:_step_JsonInput`, commit `1462d85`) —
   `JsonInputMeta.getincludeNulls()` cae, sin el tag `includeNulls`, a
   `kettle.properties` del entorno de ejecución
   (`KETTLE_JSON_INPUT_INCLUDE_NULLS`) — no-determinismo entre máquinas
   para el mismo `.ktr`. Corregido: se emite siempre explícito (default
   `"N"`, igual al fallback real de la property).
5. **TextFileOutput** (`steps/output.py:_step_TextFileOutput`, commit
   `37e792d`) — `TextFileOutputMeta.readData()` lee `create_parent_folder`
   como hijo directo de `<step>`, no anidado en `<file>`; el emisor lo
   anidaba, inocuo hasta hoy solo porque el único valor emitido (`"Y"`)
   coincide con el default ante tag ausente. Corregido: se emite al nivel
   correcto.

Evidencia. 5 commits (`d0a79b9`, `3194463`, `58d4e89`, `1462d85`,
`37e792d`), 5 tests nuevos en `test_build_ktr_emission.py`
(`test_string_operations_emits_literal_kettle_codes_not_numeric_indices`,
`test_unique_emits_case_insensitive_tag_with_correct_polarity`,
`test_excel_input_emits_spreadsheet_type_by_extension`,
`test_json_input_emits_include_nulls_explicit`,
`test_text_file_output_emits_create_parent_folder_at_step_level`), los 12
tests del archivo en verde. Suite completa corrida antes del lote: 693
passed / 55 failed (failures preexistentes, de red/API-key y del rojo ya
conocido E-03 — ninguno en los 3 archivos tocados por este lote).

<a id="d60"></a>
### D60 — O1-b: `VALUE_META_TYPE_NAMES` corregida, criterio de degradación legítima, política de los 4 sitios de aborto `[O1]`

Estado: decidido, mismo turno. Ejecutado: verificación/fix de `VALUE_META_TYPE_NAMES` (E-02) y el criterio de abajo. Pendiente: convertir los 4 sitios (Alcance punto 2 de `10-estabilizar-emision.md`) — esta entrada fija la regla con la que esa conversión se hace, no la ejecuta.

**1. `VALUE_META_TYPE_NAMES` (E-02) — verificada contra fuente, estaba incompleta.**

`DimensionLookupMeta.getUpdateType()` (`pentaho/pentaho-kettle`, rama `master`, `plugins/dimensionlookup/.../DimensionLookupMeta.java`, método ~842-858, invocado desde `readData()` ~1080-1090) delega a `ValueMetaFactory.getIdForValueMeta(ty)` cuando el step está en modo `update=false` — interpreta el tag `<field><update>` como nombre de value-meta. `getIdForValueMeta()` (`ValueMetaFactory.java:97-103`) resuelve por nombre exacto (case-insensitive) contra **todos** los plugins `ValueMetaPluginType` registrados y devuelve `TYPE_NONE` si no matchea ninguno — el mismo `TYPE_NONE` que es el id de `"-"` (colisión de sentinel ya registrada en `10-estabilizar-emision.md`).

El vocabulario que el emisor debe aceptar como legítimo no es "todo lo que resuelve" (eso incluiría `Serializable`, un tipo interno que Kettle mismo no ofrece como opción) sino exactamente `ValueMetaFactory.getValueMetaNames()` (`ValueMetaFactory.java:87-96`): filtra `id > 0` (excluye `"-"`/`TYPE_NONE`, el sentinel) y excluye `TYPE_SERIALIZABLE` explícitamente. Contra `ValueMetaInterface.java:95-128` (`TYPE_NONE=0` … `TYPE_INET=10`, array `typeCodes`), el resultado de `getValueMetaNames()` son 9 nombres: `Number, String, Date, Boolean, Integer, BigNumber, Binary, Timestamp, Internet Address`.

`VALUE_META_TYPE_NAMES` (`domain/scd.py`) traía 8 de los 9 — faltaba **`Internet Address`** (`TYPE_INET=10`). Corregido en el mismo turno (commit pendiente de este cierre), con la cita completa de clase+línea dejada como comentario en el símbolo.

**No explica el crash de `'Cargar dim_producto'` (E-01).** Ese step tenía `type='Update'` — un código de modo Y (`ATTRIBUTE_UPDATE_TYPE_CODES`), no un nombre de value-meta — mientras el step estaba clasificado en modo N. Agregar `Internet Address` no lo hubiera aceptado: el defecto de E-01 es que `fields` no se reescribió al vocabulario del modo nuevo cuando D58 forzó `update=N` sin loader completo (ver diagnóstico), no que el vocabulario N estuviera incompleto. E-02 era un defecto real e independiente — sin este fix, cualquier atributo legítimamente tipado `Internet Address` hubiera abortado el build sin motivo real — pero no cierra E-01.

**2. Criterio de degradación legítima vs. rota (E-03).**

Investigado antes de escribir el criterio: `test_repair_dimension_loader_fields_floor_when_gate_fails` (rojo, registrado como E-03) falla porque reusa el fixture de `test_repair_dimension_loader_fields_success` (mismo contrato, mismo stream — atributo faltante `nombre_categoria`, stream con `categoria`). `_deterministic_field_mapping()` (`etl_generator.py:629-655`) resuelve ese caso por el atajo sin LLM (sinónimo sin prefijo `nombre_`) **antes** de que el test alcance el LLM fake que simula la alucinación — el mapeo que sale (`categoria`→`nombre_categoria`) es real y verificado contra el stream, no inventado. El test nunca ejercía el camino que dice probar; **no es un defecto de `_repair_dimension_loader_fields`, es un defecto del fixture del test.** Corregido en el mismo turno: el test ahora usa un atributo sin match determinístico (`descripcion_categoria`), lo que sí fuerza el camino del LLM fake, y confirma que el gate (`etl_generator.py:805-815`, `mapping[a].lower() in upstream_lower` para cada atributo faltante) rechaza el `stream_field` alucinado en los 2 intentos y deja el step intacto — el "piso" que el diagnóstico prometía **sí existe**, contra lo que E-03 y este mismo archivo (`10-estabilizar-emision.md`, sección "La degradación ya existe, y está rota") afirmaban. Corrección de Regla A aplicada — ver `errores.md`.

Con esa verificación hecha, el criterio que hacía falta para generalizar (y que sigue siendo necesario para los 4 sitios, más allá de que este caso puntual resultara no roto):

> **Una degradación es legítima si y solo si el dato que sale al `.ktr` pasó, en el momento del build, por una verificación contra un inventario real — nunca porque quien lo propuso (LLM original, LLM de repair, heurística determinística) lo afirma.**
>
> 1. Para un `stream_field`, el inventario es `upstream_fields_for_step()` (lo que el grafo real de ESTE `.ktr` produce en ese punto); para una tabla/columna del DWH, el DDL real parseado. Nunca "el modelo dijo que existe".
> 2. **Sin inventario resoluble no hay verificación posible.** No se asume identidad ni ningún otro valor por default en ese caso — el atributo se omite de la salida y el finding es `error`, señalando que no se pudo verificar (no que se decidió inventar algo).
> 3. La severidad refleja el estado de verificación, no el esfuerzo invertido en producirlo:
>    - Verificado, coincide por identidad → sin finding (ya confiable).
>    - Verificado, pero con nombre distinto del esperado (inferencia real) → `info` — funciona, un experto lo confirma antes de correr en Spoon.
>    - No verificable, o verificación fallida → `error` — el valor sale tal cual llegó (nunca sustituido por un default plausible) y el finding dice explícitamente qué no va a funcionar.
> 4. Un intento de reparación que falla dos veces deja el mismo rastro que no haber intentado — nunca se sube la severidad a `info` porque "se intentó".

Contra este criterio: `_repair_dimension_loader_fields` (gate en `etl_generator.py:805-815`) y `_deterministic_field_mapping` cumplen — verificado en el punto anterior. `_synthesize_dimension_lookup_config` (`dimension_step_policy.py:229-267`) cumple en el camino de repair (línea 234-241: exige `upstream_lower is not None` y pertenencia). **No cumple** en su rama de `upstream_lower is None` (grafo no resoluble, línea 243-244): asume `stream_field = attr` por identidad sin verificación y sin finding — comportamiento heredado, documentado como tal en su propio docstring ("preserva el comportamiento histórico... asume... sin verificar"), pero es exactamente el patrón que el punto 2 del criterio prohíbe. Registrado como **E-16** (`errores.md`, origen E-03) — no se toca en este turno (profundidad de cadena ya en 2, y está fuera del alcance puntual de E-03, que era sobre el mapeo del repair).

**3. Política de los 4 sitios de aborto (Alcance punto 2), derivada del criterio.**

Regla compartida: **nunca abortar todo el build por el contenido de un step.** Aislar el defecto al step, emitir el dato exactamente como llegó (nunca sustituido por un valor adivinado) y agregar `Finding(severity="error")` con step, campo, valor literal y qué va a pasar en Kettle — predicho contra el `Meta` real (leer como Kettle), pero reportado en voz alta en vez de dejarlo pasar en silencio (fallar distinto que Kettle, ver `docs/README.md` § Autoridad sobre Pentaho).

| Sitio | Hoy | Política nueva |
|---|---|---|
| `build.py` `incomplete` (`missing_required_keys`, ~L142-157) | Aborta TODO el build por una clave estructural faltante en un step | Sin inventario que verificar (una clave ausente no tiene "valor real" contra qué contrastar) — se emite el step con esa clave vacía/ausente tal cual y `Finding(error)` nombrando el step y la clave. No bloquea el resto del build. |
| `build.py` `critical_incomplete` (`_CRITICAL_FIELDS`, ~L230-253) | Aborta TODO el build por un campo crítico vacío o placeholder (`"SELECT 1"`) | Mismo tratamiento: se emite el valor literal (incluso el placeholder — es lo que llegó, no se inventa nada mejor) + `Finding(error)` explícito de que ese step no va a producir filas reales. |
| `build.py` `STEP_BUILDERS.get(canonical_type) is None` (~L381-385) | Aborta TODO el build — no hay builder registrado, literalmente no hay código que emita XML para ese tipo | Único sitio de naturaleza distinta: no hay "valor tal cual llegó" que preservar, porque no existe forma de codificarlo. Sustituto defendible: emitir un step `Dummy` real de Kettle (no-op documentado, no una invención de comportamiento) en su lugar, conservando nombre y hops, + `Finding(error)` con el tipo original no soportado. |
| `steps/lookups.py` `_step_DimensionLookup` vocabulario cruzado (~L90-96) | Aborta TODO el build — `KtrBuilderError` (el crash de E-01) | Se emite el `field_value` literal tal como llegó (nunca coaccionado a un valor "corregido" adivinado) + `Finding(error)` que cita el vocabulario esperado para el modo asignado y predice el efecto real en Kettle (mode Y: cae a `TYPE_UPDATE_DIM_INSERT` sin aviso, R-K7; mode N: `getIdForValueMeta` cae a `TYPE_NONE`) — la predicción va en el mensaje, no en el comportamiento del emisor. |

Los 3 primeros comparten mecanismo (pass-through + finding); el tercero es la única excepción de forma (no de contenido) entre los 4 — coherente con la línea que ya traza `10-estabilizar-emision.md` § "Qué sigue abortando, a propósito".

**Supersede, específicamente:** la frase de D55 ítem 1 (rótulo interno "D-1" en ese texto) — *"El validador pre-emisión... reporta error ante vocabulario cruzado; el emisor (`lookups.py`) levanta `KtrBuilderError` — no hay fallback silencioso a 'Insert' — usando el mismo precedente que ya existe en `build.py:376-385` para step-type no soportado"* — en la parte que exige `KtrBuilderError`/abort total para esos dos sitios (`lookups.py` vocabulario cruzado y `build.py` step no soportado) y, por la misma tabla de D55, extiende a los otros 2 sitios de `build.py` que comparten la clase de problema (contenido, no forma). El resto de D55 (selección de vocabulario por modo, sin condición de `fields` vacío) sigue vigente — no se toca acá.

**Pendiente, explícito:** esta entrada decide la regla; no reescribe `build.py`/`lookups.py`. Eso es la parte no ejecutada del Alcance punto 2 de `10-estabilizar-emision.md`, sesión aparte de O1.

<a id="d61"></a>
### D61 — O2-a: `common.py` partido en dominio (`common.py`) e infraestructura (`xml_helpers.py`) `[O2]`

Estado: decidido, ejecutado, mismo turno.

`common.py` era una fila **partido** del mapa capa-objetivo (`docs/arquitectura-objetivo.md`): `_yn`/`KtrBuilderError` son puros (normalización de un valor de config, una excepción de dominio) mientras que `_sub` arma un `xml.etree.ElementTree.Element` — infraestructura de serialización XML. Mismo criterio ya aplicado a `registry.py` → `step_types.py`/`step_emitters.py`.

Ejecutado: `_sub` se mudó a `xml_helpers.py` (nuevo, `services/ktr_builder/`). `common.py` queda con `_yn`/`KtrBuilderError`, docstring actualizado explicando el split. Todo import de `_sub` en `build.py`, `connection.py`, `steps/control.py`, `steps/input.py`, `steps/output.py`, `steps/transform.py` apunta ahora a `xml_helpers.py`; donde un módulo también usaba `_yn`, el import se separó en dos líneas (`common` para `_yn`, `xml_helpers` para `_sub`).

Nota de capa física: el mapa marca `common.py` como `domain/` "ejecutado", pero el archivo sigue viviendo en `services/ktr_builder/common.py`, no en `backend/app/domain/`. Es la misma distinción que ya usa `arquitectura-objetivo.md` para `step_types.py`: el mapa fotografía la capa lógica a la que pertenece el contenido, no compromete una fecha de reubicación física — mudar el archivo es la migración grande (`ports/`/`infrastructure/` físicos), pospuesta a propósito (ver `20-arquitectura.md` § "Lo que O2 NO hace antes de entregar").

`docs/services/ktr_builder/README.md` actualizado: fila `common.py` marcada "Ejecutado (O2-a)", fila nueva `xml_helpers.py` agregada. `test_architecture_layers.py`: comentario de `DOMAIN_MODULES` actualizado para reflejar el split ya ejecutado (ya no dice "se incluye para permitir que `contracts.py` importe la mitad pura" — ahora todo el módulo es dominio puro sin excepción parcial).

**Verificación:** `test_architecture_layers.py` verde. `FROZEN_*` sin cambios (esta sesión no corrige ninguna violación existente, solo mueve código ya conforme).

<a id="d62"></a>
### D62 — O2-b (T1): `resolve_step_table()` en `domain/`, tres call sites dejan de tragar la tabla vacía en silencio `[O2]`

Estado: decidido, ejecutado, mismo turno.

**Problema (T1, `docs/refactor/05-transversales.md`):** `fragmentation.build_rw_matrix`, `dimension_step_policy.enforce_dimension_step_policy` y `fields_validate.validate_dimension_lookup_races` reimplementaban, cada uno por separado, "extraer candidato de tabla, normalizar, y si viene vacío, `continue` sin dejar rastro". D40 (`table_key_recovery.py`) adelantó la resolución de la causa (recupera `table` por contenido antes de que estos 3 módulos corran) pero no tocó la reacción — los 3 `continue` mudos seguían intactos, tal como registra el `Estado` de T1.

**Decisión:** `resolve_step_table(step_name, table_raw) -> (tabla | None, mensaje | None)` nueva en `domain/step_table.py`. Reemplaza la parte realmente duplicada (`.strip()`, chequeo de vacío, notificación) — no decide qué candidato mirar (`cfg["table"]` vs. `cfg["target_table"]`/`cfg["table_name"]`, prioridad entre ellos) ni si el tipo de step "debería" tener tabla: eso sigue siendo contrato de cada caller. Sin ese filtro previo, notificar por cada step sin `table` sería ruido (la mayoría de los steps de una transformación — `Sort`, `FilterRows`, `JavaScript`... — legítimamente no tocan ninguna tabla), no señal.

**Por qué NO devuelve `Finding` (`services/ktr_builder/validators/base.py`), pese a que R12 pide una entidad tipada:** se intentó primero, y cierra un ciclo de imports real y verificado — `domain/step_table.py` → `validators.base` fuerza la ejecución de `validators/__init__.py` (para llegar al submódulo `base`), que importa `guard_staging_layer`, que importa `fragmentation`, que importa `domain/step_table.py` de vuelta (`ImportError: cannot import name 'resolve_step_table' from partially initialized module`, reproducido antes de revertir). `resolve_step_table()` devuelve un mensaje de texto plano; cada caller lo envuelve en su propia forma de notificación (`Finding` en `fragmentation.py`, dict `{"tipo","campo","mensaje"}` en `dimension_step_policy.py`, string plano acumulado en `errors` en `fields_validate.py` — mismo contrato que ya tenía esa función). `domain/step_table.py` queda sin ningún import de proyecto — cumple la regla direccional Y el proxy conservador ("domain solo importa stdlib") a la vez, sin necesidad de una excepción nombrada.

**Los tres call sites, reordenados para notificar solo donde corresponde** (antes: extraían la tabla ANTES de saber si el step era relevante, así que el `continue` mudo cubría tanto "step sin tabla porque no le corresponde" como "step que sí debería tener tabla y no la tiene" — indistinguibles):

1. **`fragmentation.build_rw_matrix`** — `_step_rw(canonical, cfg)` (no depende de `table`, solo de `canonical`+`cfg["update"]`) se evalúa primero; si es `None` (step sin rol R/W, ej. `Sort`), `continue` sin tabla ni aviso, igual que antes. Si tiene rol R/W (`TableOutput`, `InsertUpdate`, `DimensionLookup`...) y la tabla no resuelve, se agrega un `Finding(severity="error")` a la lista que la función ya devuelve (`tuple[dict, list[Finding]]` — sin cambio de firma).
2. **`dimension_step_policy.enforce_dimension_step_policy`** — la función sigue necesitando `table` para CUALQUIER step (no solo `DIMENSION_STEP_TYPES`: el desenlace "tipo de step fuera de `{DimensionLookup, CombinationLookup}` sobre una tabla de `dim_contracts`" depende de resolverla primero). Se preserva ese comportamiento; lo que cambia es que un `DimensionLookup`/`CombinationLookup` (`DIMENSION_STEP_TYPES`) SIN tabla resoluble — antes invisible — ahora agrega `{"tipo": "error", "campo": "", "mensaje": ...}` a `results` antes del `continue`. Sin cambio de firma (sigue devolviendo `list[dict]`).
3. **`fields_validate.validate_dimension_lookup_races`** — ya filtraba por `canonical in ("DimensionLookup", "CombinationLookup", "DBLookup")` ANTES de resolver tabla, así que acá el mensaje se agrega siempre que la tabla no resuelva (los tres tipos, por contrato, tienen que tocar una tabla). Sin cambio de firma (sigue devolviendo `list[str]`, mismo canal que ya promueve `build.py` a `Validacion tipo="error"` vía `FIELD_INTEGRITY_PREFIX`).

**No tocado, a propósito:** `table_key_recovery.py` — resuelve la causa (recupera `table` antes de que estos 3 corran), no la reacción; esta entrada hace lo que D40 no hizo, no lo repite. Casing preservado por sitio: `dimension_step_policy.py` seguía comparando con `.strip()` sin forzar minúsculas (para no cambiar el casing en sus propios mensajes al usuario), mientras que `fragmentation.py`/`fields_validate.py` siguen normalizando a minúsculas después de llamar a `resolve_step_table()` — la función no fuerza ningún casing, cada caller decide, igual que antes.

**Verificación:** `test_architecture_layers.py`, `test_build_ktr_emission.py`, `test_contract_validate.py`, `test_dimension_field_repair.py`, `test_dimension_step_policy.py`, `test_fragmentation.py`, `test_ktr_xml_validator.py` — 77 passed / 1 failed (`test_build_ktr_get_system_info_without_fields_gets_default_field`, preexistente e independiente, ver D60). Suite completa corrida contra la misma base.

<a id="d63"></a>
### D63 — O1-b: dedupe de vocabulario cruzado en `DimensionLookup` — canal único `check_dimension_lookup_fields` `[O1]`

Estado: decidido y ejecutado en la sesión que cerró el Bloque 1 (D60); esta entrada es el registro faltante — se escribió el resultado (el bloque de reporte se borró de `dimension_step_policy.py:551-567`) sin dejar la justificación, y una sesión posterior (Bloque 0 de la siguiente) la pidió por separado. Auditado retroactivamente acá, sin encontrar regresión.

**Problema:** con el Sitio 3 de D60 (`enforce_dimension_step_policy`, rama `already_readonly`) y `validators/dimension_lookup_fields.py::check_dimension_lookup_fields` corriendo los dos, un `DimensionLookup` que llega ya en modo N con `fields` heredado en vocabulario modo Y se reportaba DOS VECES — mismo step, mismo defecto, dos redacciones distintas (`enforce_dimension_step_policy` inline vs. el validador pre-emisión). Se decidió un canal único: `check_dimension_lookup_fields` (corre incondicional en `build.py` para TODO `DimensionLookup`, ambos modos — cubre lo que el bloque borrado cubría y más). El bloque de `dimension_step_policy.py` se borró, dejando solo el comentario que explica por qué (líneas 539-551).

**Verificación (auditoría retroactiva, esta sesión), en el orden pedido:**

1. **¿El Finding llega al frontend?** Sí, sin regresión. `check_dimension_lookup_fields` corre vía `run_passes()` dentro de `build.py` (`table_findings`, línea ~187) → `split_findings_by_severity()` marca cada `Finding(severity="error")` con `PRE_EMIT_ERROR_PREFIX` → esa lista entra a `warnings` que `build_ktr()` devuelve → `_build_ktr_stage()` la acumula en `ktr_warnings` → `etl_generator.py` la pasa a `_split_integrity_warnings()` (líneas ~1099, ~1237), que reconoce `PRE_EMIT_ERROR_PREFIX` (junto a `FIELD_INTEGRITY_PREFIX`/`CONTRACT_PREFIX`/`ERROR_CATALOG_PREFIX`) y promueve a `Validacion(tipo="error")` en la respuesta. Cadena completa verificada archivo por archivo, no por inspección superficial.
2. **Cobertura por timing.** El bloque borrado corría dentro de `enforce_dimension_step_policy()` (llamado en `etl_generator.py` ANTES de `split_ktr_by_cut`/`compute_cut`, sobre el dict completo de la etapa). `check_dimension_lookup_fields` corre dentro de `build_ktr()`, llamado una vez POR sub-transformación después del corte (`_build_ktr_stage`, un `build_ktr()` por elemento de `sub_dicts`). Verificado que no hay pérdida: `split_ktr_by_cut()` → `compute_cut()` → `_connected_components()` (`fragmentation.py:240-266`) arma la lista `names` a partir de TODOS los steps de `ktr_data["steps"]` (no solo los que tienen hops — un step aislado es un componente singleton) y a cada `name` le asigna un `comp_id`; `groups` particiona esa asignación completa. Cada step del dict original cae en exactamente un grupo, y `_build_ktr_stage` llama `build_ktr()` una vez por grupo — la unión de lo que ven las N llamadas es exactamente el conjunto que el bloque borrado veía en una sola pasada. Sin gap de cobertura.
3. **Whitespace (hueco 0a).** Confirmado el sentido correcto: Kettle compara `<field><update>` con `equalsIgnoreCase()`, que NO recorta whitespace. Antes de `392a0f9`, `check_dimension_lookup_fields` matcheaba con `field_type.lower()` (la variable YA stripeada, usada para detectar ausencia) en vez de `raw_field_type` — divergencia real entre lo que el validador aceptaba y lo que Kettle acepta, registrada como **E-19** (`errores.md`, origen E-01). `392a0f9` ya lo corrigió a `str(raw_field_type).lower() not in valid_vocab` (línea 103) — sin strip, lee como Kettle. `lookups.py` (Sitio 4, mismo commit) no adoptó ningún strip: el bloque que abortaba (`if field_value not in valid_vocab: raise KtrBuilderError`) se borró entero, no se invirtió — el emisor ahora solo emite `field_value` tal cual llegó (D60 política de los 4 sitios), sin comparación propia. No hay inversión que revertir.
4. **Fragilidad del test.** `test_already_readonly_fact_lookup_with_crossed_vocabulary_is_left_untouched` (`test_dimension_step_policy.py`) asertaba `not any(r["campo"]=="dim_producto" and "vocabulario cruzado" in r["mensaje"] for r in results)` — frágil: pasa igual si `enforce_dimension_step_policy` empezara a emitir un finding con otra redacción para el mismo defecto. Con el fixture de ese test (loader ya coincide con `expected`, lookup ya `already_readonly`), NINGÚN branch de la función agrega nada a `results` — se cambió el assert a `results == []`, estructural: falla ante cualquier finding nuevo para este caso, no solo ante la reaparición de una frase puntual.

**Ejecutado en esta sesión:** fix de E-19 (assert) en `test_dimension_step_policy.py`, registro de E-19 en `errores.md`, esta entrada.

**Verificación runtime:** `test_dimension_step_policy.py` + `test_dimension_lookup_fields.py` + `test_build_ktr_emission.py` — 50 passed / 0 failed (corrida completa de los 3 archivos tocados por D60/D63, incluido el assert estructural nuevo).

<a id="d64"></a>
### D64 — O1: Alcance punto 3 (`10-estabilizar-emision.md`) verificado en corrida real — canal ya existía, sin cambio de código `[O1]`

Estado: verificado, mismo turno. **Ningún archivo de código se modificó en esta sesión** — solo trazado + corrida real + esta documentación.

**Pregunta (Alcance punto 3, pendiente desde que se escribió `10-estabilizar-emision.md`):** los findings de `enforce_dimension_step_policy` (canal (a): `results` → `job.model_json["step_policy_conflictos"]`) — ¿llegan al usuario, y por qué camino?

**Trazado (canal a), archivo por archivo:** `enforce_dimension_step_policy()` (`dimension_step_policy.py:507-523`) agrega `{"tipo": "error", "campo": tabla, "mensaje": "...falta(n)... Sobra(n)...", "repairable": True, ...}` a `results`. Ese `results` (tras el intento de `_repair_dimension_loader_fields()`, que lo deja intacto si el gate no cierra) se persiste sin transformar en:
- Flujo async (`generate_etl_async`, `etl_generator.py:2074`): `job.model_json["step_policy_conflictos"]`, leído por `_try_build()` (`etl_generator.py:1820`) y convertido con `Validacion(**c)` — Pydantic v2 ignora las claves extra (`repairable`/`step_name`/`missing`/`sobra`) por default (`Validacion` no declara `model_config(extra=...)`), así que `tipo`/`campo`/`mensaje` (el texto completo, con los nombres de columna) pasan intactos a `extra_validaciones`.
- Flujo síncrono (`etl_generator.py:1683`) y `build_etl_from_raw()` (`etl_generator.py:1393`/`1433`): mismo patrón, `Validacion(**r)` o `.extend(step_policy_results)` directo a `data_2["validaciones"]` (que Pydantic valida igual al construir `ETLGenerateResponse`).

En los tres casos, `extra_validaciones`/`data_2["validaciones"]` entra a `ETLGenerateResponse.validaciones` (`_build_response_from_two_ktr_data`, `etl_generator.py:1248-1251`) — el MISMO campo, la MISMA lista, donde cae el canal (b) (`check_dimension_lookup_fields` vía `_split_integrity_warnings`, D63). El frontend (`ResultView.jsx:116-121`, `ValidationItem` línea 28) renderiza `validaciones` sin distinguir canal: un badge por `tipo` (`Error`/`Advertencia`/`Info`), campo, mensaje completo sin truncar, dentro de la sección "Validaciones".

**Conclusión: no hay hueco que cerrar — el canal ya era el mismo (canónico) desde `149b836` (commit que introdujo `step_policy_conflictos`, anterior a toda la serie D57/D58/D60).** El punto 3 del Alcance se escribió como pendiente pero la wiring ya existía; lo que faltaba era la verificación contra una corrida real, no el código.

**Verificación (corrida real, no unit test con mocks):** `build_etl_from_raw()` invocado directamente con el corpus real de E-01 (`docs/refactor/fase4_manual/sonnet/etl-llm-raw-test-01_sonnet_fase4.json`) y `dim_contracts` reconstruidos a mano desde `DDL-inferido-test-con-raw.txt` (`dim_producto` SCD1: `technical_key=sk_producto`, `attributes_scd1=[bk_producto, nombre_producto, nombre_categoria, precio_unitario]`), `llm=None` (sin costo, sin red — mismo modo que "Reutilizar respuesta"). Resultado en `result.validaciones`:

```
[error] campo='dim_producto': Step 'Cargar dim_producto' es la única candidata para 'dim_producto'
(dimensión declarada en dim_contracts), pero no trae en 'fields' los atributos que el contrato
declara — falta(n): nombre_categoria. Sobra(n) (no pertenecen a esta dimensión): fk_categoria,
precio_lista, stock. Probable loader faltante...
```

más 6 findings `[Dimension lookup/update]` (canal b) nombrando cada atributo (`nombre_producto`, `fk_categoria`, `precio_lista`, `precio_unitario`, `stock`, `bk_producto_calculado`) con `type='Update'` fuera de vocabulario modo N. **Ambas señales — vocabulario cruzado Y los 3 nombres de columna inexistentes — llegan al usuario antes de ejecutar, en la misma corrida.** Build completo, sin excepción: 1 archivo (`origen_stg`) + 2 archivos + 1 `.kjb` (`stg_dwh`, partido por `compute_cut`) + `.kjb` maestro. Los 3 `.ktr` generados son XML bien formado (verificado con `xml.etree.ElementTree.parse()` — no se abrió Spoon literalmente en este entorno, mismo proxy que el resto de este objetivo usa).

**Repair no se disparó en esta corrida** (el finding de canal (a) llegó sin reparar, con `llm=None`): `_repair_dimension_loader_fields()` retorna sin intentar nada apenas `llm is None` (`etl_generator.py:700-702`), ANTES de evaluar `_deterministic_field_mapping()` — que no necesita LLM y hubiera resuelto `nombre_categoria`→`categoria` (prefijo `nombre_`) igual. No es un bug de esta verificación: es una oportunidad de repair gratis que hoy queda gateada detrás de un chequeo que no debería aplicarle — registrado como **E-21** (`errores.md`), no corregido acá (fuera del alcance de este punto — el piso, entregar con el problema documentado, se cumple igual con o sin repair).

**Encontrado, no buscado — E-20 (`errores.md`):** los 6 findings de canal (b) aparecen **duplicados** (12, no 6) en `result.validaciones`. Causa confirmada con stack trace: `_recover_table_keys()` (H29, `etl_generator.py:305-334`) corre `run_passes()` — el tuple `PRE_EMIT_PASSES` COMPLETO, no solo `recover_table_key` — sobre el `ktr_data` completo ANTES del corte; `build_ktr()` (vía `_build_ktr_stage`) corre el mismo `run_passes()` completo otra vez sobre el sub-dict ya partido. `check_dimension_lookup_fields` (y cualquier otro pass de `PRE_EMIT_PASSES` insensible a si `table` ya se recuperó) no tiene forma de saber que ya corrió — el mismo finding sale dos veces, byte a byte. No es específico de este corpus: aplica a toda corrida con dimensiones (sync, async, `build_etl_from_raw`), desde que `_recover_table_keys` se cableó (H29). No bloquea el criterio de aceptación (el finding SÍ llega, con toda la info) pero es ruido real para el usuario — el mismo error se ve dos veces sin explicación. Abierto, `Origen=E-01` (encontrado verificando su cierre), no se corrige en esta sesión (regla de escritura: descubrir es libre, actuar necesita ruta — y esto no estaba en el alcance del prompt que originó esta sesión).

**Verificación runtime:** ninguna (sin cambio de código, no aplica correr la suite). La corrida real de arriba se hizo con un script ad-hoc (`repro_dim_producto.py`, scratchpad), no un test nuevo — no se agrega a `backend/tests/` porque no hay código nuevo que cubrir; si E-20 se corrige en una sesión futura, ESE cambio sí necesita test.

<a id="d65"></a>
## D65 — O1-b cierra; con eso, O1 queda completo

**Fecha:** 2026-08-03
**Commit:** `80a1e3b`

**Qué se decidió**
O1-b se da por cerrada. O1-a y O1-c ya estaban cerradas, así que O1 queda completo.

**Evidencia**

- Test `test_e01_corpus_through_real_async_pipeline_reaches_built` (`backend/tests/test_ktr_build_job_api.py`): corre el corpus real de E-01 por el camino asíncrono completo — `/generate-async` → `/connections` → `/status` —, ruta nunca antes ejercitada (D64 solo había corrido `build_etl_from_raw()` directo). Resultado: `model_status == "done"`, `build_status == "built"`, y el finding de vocabulario cruzado llega a `result.validaciones` nombrando los 3 campos inventados (`fk_categoria`, `precio_lista`, `stock`).
- Sin Spoon en esta máquina (verificado: no hay Pentaho Data Integration instalado). En su lugar se hizo cross-check de los `<type>` XML emitidos contra `investigacion-tags-validos-por-step.md`: 13 tipos de step del corpus, todos con plugin id real verificado, ninguno cae en la trampa de E-11.
- Fix de Bloque 3: `_build_response_from_two_ktr_data` (`backend/app/services/etl_generator.py`) ya no descarta la etapa origen→STG cuando la etapa STG→DWH falla estructuralmente. Ahora entrega esa etapa sola más un `Validacion(tipo="error")` con el motivo del fallo de la otra. Test: `test_stg_dwh_structural_failure_still_delivers_the_origen_stg_stage_built` (`backend/tests/test_etl_generate_response_shape.py`).
- Suite completa: 733 passed / 30 failed. Baseline previo a esta sesión: 730 passed / 31 failed. Cero regresión, 3 tests nuevos en verde.

**Qué supersede**
La baja a "parcial" de los criterios 3 y 4 que hizo la sesión de auditoría anterior. Ambos vuelven a "Hecho", ahora respaldados por corrida real y no solo por lectura de código.

**Efectos colaterales registrados, NO arreglados**
Quedan abiertos en `errores.md`; no bloquean el cierre.

- **E-23** — impacto de E-21 confirmado empíricamente: con LLM disponible, el repair determinístico resuelve el caso sin llegar a llamar al modelo.
- **E-24** — nuevo: los findings de "vocabulario modo N" sobreviven en `validaciones` después de que el repair H51 reclasifica el step a modo Y con vocabulario correcto. El archivo final queda bien, pero el finding que ve el usuario describe un estado ya superado.


<a id="d66"></a>
### D66 — O2-c: `lineage_builder.py` partido en dominio (`domain/lineage.py`) e infraestructura, registro retroactivo `[O2]`

Estado: decidido y ejecutado en la sesión que cerró O2-c (misma sesión que cerró O2-a/O2-b, 2026-08-03); esta entrada es el registro faltante — la fila del mapa (`arquitectura-objetivo.md`) y `docs/README.md` ya decían "cerrada"/"Ejecutado (O2-c)" sin que existiera una D-N propia. `docs/README.md` había anotado "D63 pendiente de redactar" como placeholder; D63 se usó después para un tema distinto (dedupe E-20, O1-b) y la referencia quedó apuntando a un número equivocado — corregida en la sesión que escribe esta entrada (ver D67).

**Problema:** `lineage_builder.py` era la última fila **partido** barata del mapa capa-objetivo. `build_lineage`, `stitch_lineage_many` y `stitch_lineage` son funciones puras sobre el dict KTR (armar el grafo de linaje origen→staging→DWH); `_parse_ktr_xml` lee XML ya serializado — infraestructura.

**Decisión:** las tres funciones puras se mueven a `domain/lineage.py`, devolviendo `LineageGraphData` — dataclass propia de stdlib, no `schemas.lineage.Lineage` (`BaseModel` de Pydantic, prohibido en `domain/` por `domain/README.md` § "Qué NO va acá", motivo no explícito en la fila original del mapa hasta esta ejecución). `services/lineage_builder.py` queda como borde: convierte `LineageGraphData` → `Lineage` para la API y conserva `_parse_ktr_xml` (infra). Firmas públicas sin cambios: `build_lineage`, `stitch_lineage_many`, `stitch_lineage`, `build_lineage_from_xml`, `stitch_lineage_from_xml` siguen expuestas desde `services/lineage_builder.py` — `routers/ai.py` y `etl_generator.py` (congelado, `90-congelado.md` T8, no tocado) no necesitaron ningún cambio.

`domain.lineage` agregado a `DOMAIN_MODULES` en `test_architecture_layers.py`. `FROZEN_R1` sigue vacío — el import a `schemas.lineage` que tenía el módulo original ya no existe del lado `domain`, sin excepción nueva que registrar. Mapa (`arquitectura-objetivo.md`, fila `services/lineage_builder.py`) marcado "Ejecutado (O2-c)".

**Verificación:** suite completa 697 passed / 54 failed, igual a la cifra de O1-c — cero regresión. `test_architecture_layers.py` verde.

<a id="d67"></a>
### D67 — O2 verificado completo al pedir "empezar O2"; nada ejecutado, solo verificación y corrección de docs `[O2]`

Estado: verificado, mismo turno. **Ningún archivo de código se modificó en esta sesión** — solo trazado contra código/git, `docs/README.md` y esta documentación.

**Contexto:** el pedido de sesión fue "Leé `docs/README.md` y `docs/refactor/10-estabilizar-emision.md`. Comienza O2." Antes de escribir código, se verificó el estado real de O2-a/O2-b/O2-c contra el código (Regla A de `docs/README.md`: ningún documento de estado es autoridad sobre si algo está hecho).

**Hallazgo:** las tres sesiones de O2 (`20-arquitectura.md`) ya estaban ejecutadas:

- `domain/common.py` + `services/ktr_builder/xml_helpers.py` existen (O2-a, D61).
- `domain/step_table.py` existe, con `resolve_step_table()` consumida por los tres call sites (O2-b, D62).
- `domain/lineage.py` existe, 11 KB (O2-c) — sin D-N propia hasta esta sesión, ver D66.
- `backend/tests/test_architecture_layers.py`: 4 passed, `FROZEN_R1` vacío.
- Mapa capa-objetivo (`arquitectura-objetivo.md`) marca las tres filas correspondientes "Ejecutado".

**Discrepancia encontrada y corregida en el mismo turno (Regla 8 de `docs/README.md`):** `docs/README.md`, tabla de sesiones, fila O2-c decía "D63 pendiente de redactar". D63 ya estaba escrita — para un tema distinto (dedupe de vocabulario cruzado, O1-b). La referencia quedó de un placeholder anterior a que D63 se asignara a otra decisión. Corregida para no apuntar a un número equivocado; la D-N real de O2-c es D66 (arriba).

**Decisión:** no hay nada que ejecutar para O2 — los criterios de terminado de `20-arquitectura.md` (O2-a/b/c con su D-N, suite verde, `FROZEN_*` no creció, filas del mapa marcadas) se cumplen. O2 queda cerrado. Próximo paso natural: O3 (`30-decision-python-llm.md`), que según `docs/README.md` necesita O1 cerrado (D65) + `referencia/` escrita (sesión REF, cerrada 2026-08-03) — ambas precondiciones ya cumplidas.

**Verificación:** `test_architecture_layers.py` corrido esta sesión, 4 passed. Sin cambio de código, no aplica correr la suite completa.

---

<a id="d68"></a>
### D68 — O3 caso testigo: el step de dimensión se sintetiza siempre, no se pide y corrige `[O3]`

**Contexto:** O3 (`30-decision-python-llm.md`) identificó una cadena de 6 estaciones para una sola decisión — cómo se configura el step que carga una dimensión: Python deriva `scd_type` → se lo cuenta al modelo → el modelo devuelve el step completo (puede contradecir el contrato) → Python detecta la contradicción (`enforce_dimension_step_policy`) → Python repara con otra llamada al LLM (`_repair_dimension_loader_fields`) → si no alcanza, degrada. Cada estación nueva, agregada históricamente para atrapar al modelo contradiciendo un contrato que ya conocía de antemano, es un lugar más donde la semántica puede divergir de las otras cinco — el motor de "arreglo un error y aparece otro" (`errores.md`: E-16, E-21, E-23, E-24, los cuatro alrededor de esta misma cadena).

**Decisión — la línea entre lo que pregunta y lo que deriva:**

1. El modelo aporta topología (steps + hops) + `config.table` + `keys[].stream_field`/`fields[].stream_field` — lo único no derivable de un contrato: qué campo del stream alimenta cada columna cuando los nombres no coinciden.
2. Python sintetiza SIEMPRE (no solo al detectar discrepancia) `update`/`return_field`/`date_from`/`date_to`/`version_field`/`fields[].type` desde `DimContract`, vía `build_dimension_lookup_config()` (`ktr_builder/dimension_step_policy.py`), llamado desde `apply_dimension_contracts()` — reemplaza `enforce_dimension_step_policy` (que comparaba lo que el modelo escribía contra el contrato y corregía si difería; ya no hay nada de eso que comparar, porque no se le pide escribirlo).
3. El rol (loader vs. fact_lookup) sigue derivándose de la topología que el modelo dibujó (`role_of_dimension_step`, D16 intacto). Con un solo candidato sobre una tabla se fuerza a loader sin excepción — **supersede parcialmente D58:** el discriminador que inspeccionaba si `fields` del modelo ya traía el contrato completo (evidencia de intención) se retira, porque `fields` del modelo dejó de ser prueba de intención — es apenas una pista de mapeo que la síntesis valida contra el stream real. La rama `already_readonly` ("ya venía bien, no se toca") también se retira: la síntesis reconstruye el config siempre.
4. Se borra la estación de reparación completa: `_repair_dimension_loader_fields`, `_dimension_repair_context`, `_deterministic_field_mapping` (`etl_generator.py`). Su lógica determinista (resolver `nombre_categoria`→`categoria` despojando el prefijo `nombre_`) pasa a ser el paso 3 de una escalera de 4 dentro de `build_dimension_lookup_config` (mapeo propuesto por el modelo → identidad → prefijo → omitir + finding error), en el camino principal, sin LLM. Cierra E-21/E-23 por construcción: el `if llm is None: return` que dejaba ese intento determinista inalcanzable sin proveedor deja de existir junto con la función que lo contenía.
5. `PRE_EMIT_PASSES` (`validators/__init__.py`) se parte en `TABLE_RECOVERY_PASSES` (antes de sintetizar — recupera `table`) y `VERIFY_PASSES` (después — inspecciona el config ya sintetizado). Antes, los passes de verificación (`check_dimension_lookup_fields`, `check_narration_crosscheck`) corrían junto con la recuperación de tabla, sobre el config que el MODELO había escrito y que estaba a punto de ser pisado por la síntesis — un finding ahí describía un valor que no iba a llegar al usuario, señal falsa, no ruido inocuo.
6. `system_etl.txt` § "STEP DE DIMENSIONES" y `_format_dim_contracts()` (`etl_generator.py`) recortados: el modelo ya no recibe ni escribe `step_requerido`/`step_lookup_fk`/`scd_type`/`modo_por_atributo`/`version_field`/`date_from`/`unknown_key_value` (11 tokens por dimensión → 4: `columnas_destino`, `natural_keys`, `campo_sk_en_stream`, `columna_vigencia`).

**Riesgo nombrado, no cerrado del todo:** con un solo candidato sobre una tabla y grafo no resoluble (`upstream_fields_for_step` devuelve `None` — step sin predecesor), la síntesis cae al mismo fallback de identidad-sin-verificar que ya usaba un loader legítimo en esa situación — pero acá, a diferencia de un loader legítimo, no hay ninguna otra señal de que el step sea de verdad el loader (podría ser un lookup huérfano real, con el loader faltante en otro lado). Se agregó un finding `tipo=warning` explícito para esa intersección exacta (rol forzado de fact_lookup a loader + grafo no resoluble) — D60 exige reportar, nunca fabricar en silencio. El finding hace el riesgo visible, no lo cierra: confirmar contra corrida real antes de dar por saldado el criterio 5 de abajo.

**Verificación:** `apply_dimension_contracts()` corrido en aislamiento (no vía pytest) contra el corpus real `etl-llm-raw-test-01_sonnet_fase4.json` (el mismo de E-01/D64) — el step 'Cargar dim_producto' resuelve `nombre_categoria`→`categoria` (paso 3, prefijo) y `bk_producto`→`bk_producto_calculado` (paso 1, mapeo propuesto por el modelo), e ignora `fk_categoria`/`precio_lista`/`stock` (vocabulario cruzado de `fact_inventario`, finding `info`) — sin ninguna llamada a LLM. No corrido contra la suite completa (la corre el usuario) ni contra `/generate-async`→`/status` end-to-end — criterio 5 de `30-decision-python-llm.md`, pendiente.

**Estado:** ejecutado, esta sesión (2026-08-04). Decisiones 2, 4 y 5 de la tabla de `30-decision-python-llm.md` quedan resueltas como consecuencia directa de esta; decisión 3 (ramificar por `scd_type` en la emisión) sin tocar — D44 vigente sin cambios.

---

<a id="deliberadamente-no-decidido"></a>
## Deliberadamente no decidido

Distinguir esto de lo cerrado evita que alguien lo dé por resuelto:

- **Si el borde tipado de entrada *grande* (H2, schema `string → object`, tipo validado por construcción) va, y en qué fase.** Lo resuelve arquitectura. La pregunta concreta: ¿es habilitador de la fragmentación o una optimización paralela? **Parcialmente resuelto por D14:** para el alcance chico que el corte necesita (H4, H11, H6), no es habilitador — ya está separado en F1.5/F2.5 y no bloquea. Para el alcance grande (H2), la pregunta sigue abierta.
- **El cambio `string → object` en el schema del LLM.** Depende de un spike empírico contra Gemini y Anthropic, no de un criterio.
- **Qué hace el producto ante un raw incompleto en `build-from-raw`.** Hoy el repair loop está desconectado a propósito, con discusión pendiente. Bloquea cuán estricto puede ser ese punto de entrada.
- **El alcance exacto de las reglas de fragmentación.** Depende de D7: primero los casos, después las reglas. D7 ya confirma que los casos existen (ver Verificaciones pendientes) — falta la entrega concreta de su ubicación antes de poder escribir las reglas.
- **El plan de soporte multi-motor SQL.** D12 fija Postgres como default y exige notificación, pero no dice dónde vive la decisión de dialecto, qué construcciones son dependientes de motor más allá de `DISTINCT ON`, ni qué pasa si el usuario cambia de motor después de generar. Requiere sesión propia.

---

<a id="verificaciones-pendientes"></a>
## Verificaciones pendientes

1. ~~Confirmar que nadie del equipo tenga trabajo apoyado en ETLs guardados.~~ **Verificado 2026-07-22: nadie tiene trabajo apoyado en ETLs guardados.** D3 queda confirmado sin condición, desbloquea D10.
2. ~~Re-verificar D6 en frío.~~ **Hecho 2026-07-22** — ver evidencia bajo D6 y D6-bis arriba.
3. ~~Recolectar los casos donde forzar dos archivos falló (D7).~~ **Ubicación entregada 2026-07-22:** `C:\Users\05147\OneDrive\Escritorio\Test_Asistente_ETL\Simplificado\Sol\02\Errores\` — `err1.ktr`, `err2.ktr`. Coincide con el "corpus de regresión" que ya mencionaba el handoff de Fragmentación. Ambos archivos referencian `InsertUpdate`, `DimensionLookup` y `sk_producto` (confirmado por búsqueda de texto, no analizado en profundidad — el análisis de contenido es trabajo de Track F1/F4, no de esta sesión). D7 queda desbloqueado para F2/F3.

---

<a id="abiertos-no-bloquean-el-arranque-del-refactor-sí-bloquean-ítems-puntuales"></a>
## Abiertos (no bloquean el arranque del refactor, sí bloquean ítems puntuales)

<a id="c1"></a>
### C.1 — Plan de variabilidad de dialecto SQL `[F4]`

Postgres queda como default decidido (D12), pero el soporte multi-motor no tiene plan: dónde vive la decisión de dialecto, qué construcciones dependen de motor más allá de `DISTINCT ON`, qué pasa si el usuario cambia de motor después de generar, dónde exactamente se notifica. Requiere sesión y plan propios — información crítica que se fija antes de generar.

<a id="c2"></a>
### C.2 — Contrastar las reglas de fragmentación existentes contra D6-bis `[F2]`

**Resuelto 2026-07-22.** Releídas las reglas de "cuándo fragmentar" en `handoff_fragmentacion_y_errores.md` (sección Fase 2 del prompt, líneas 51-62): C1 (toda tabla que aparece W y R en la misma etapa marca corte), la agrupación en componentes conexos, el ordenamiento por grafo de FK, y los validadores V1/V2/V3 (ninguna tabla W+R en el mismo ktr / todo lookup tiene productor / un solo escritor por tabla). Las cuatro son señal estructural — ninguna depende de cantidad de steps, longitud de archivo, ni legibilidad. **No hay ningún umbral tipo "partir si >N steps" en el material** — no se encontró nada que eliminar.

*Conclusión:* el handoff ya cumplía D6-bis antes de que D6-bis se escribiera formalmente — coincidencia, no verificación previa (el handoff es anterior). Track F2 puede diseñar sobre el criterio C1 + V1/V2/V3 tal como están, sin depurar nada primero. Desbloquea Track F2 en este eje — F2 sigue sin arrancar sin aprobación explícita (ver `03-plan.md`).

<a id="c3"></a>
### C.3 — Verificaciones contra la base real (independiente del dialecto) `[F1/F4]`

```sql
-- ¿existen las columnas que el WHERE/ORDER BY asumen?
SELECT table_name, column_name
FROM information_schema.columns
WHERE column_name IN ('stg_estado', 'stg_fecha_carga');

-- ¿la BD genera el sk ahora que el step ya no lo hace?
SELECT column_name, column_default, is_identity
FROM information_schema.columns
WHERE table_name = 'dim_producto' AND column_name = 'sk_producto';
```

**Resultado (2026-07-22):** la base sí genera `sk_producto` sola —
```json
{"column_name": "sk_producto", "column_default": "nextval('dim_producto_sk_producto_seq'::regclass)", "is_identity": "NO"}
```
Secuencia vía `DEFAULT`, no `IDENTITY`. **Esto solo protege si el `INSERT` omite la columna por completo.** Verificado contra el generador: `_step_InsertUpdate` (`backend/app/services/ktr_builder/steps/output.py:43-63`) arma la lista de `<value>` directamente desde `cfg["fields"]`, sin ningún filtro que excluya una clave técnica/surrogate — si el step que carga `dim_producto` emite un mapeo hacia `sk_producto` (aunque sea con un valor vacío), ese `INSERT` incluye la columna explícita y pisa el `DEFAULT`. La pregunta real no es "¿la base genera el sk?" (sí) sino "¿el step generado por el LLM alguna vez mapea algo a esa columna?" — eso depende del contenido de cada corrida, no es verificable en abstracto. `err1.ktr`/`err2.ktr` (ver D7, arriba) referencian `InsertUpdate` y `sk_producto` — candidatos para revisar esto en concreto cuando Track F1/F4 los analice. No es más "rotura esperando genérica"; es un caso puntual a confirmar contra esos dos archivos.

<a id="c5"></a>
### C.5 — ¿El backend recomienda/emite constraints DDL? (R7, `bitacora_etl_ventas.md`) `[F4]`

L2-E05 (bitácora): `dim_producto` sin `UNIQUE(id_producto)` — el upsert por clave natural funciona igual, pero sin índice único admite duplicados en reprocesos concurrentes. Regla propuesta como R7: "emitir constraints de integridad que el upsert por clave natural asume."

**No es una decisión que esta sesión pueda tomar sola — es superficie de producto nueva.** Hoy el backend **no emite DDL en ningún punto**: `dwh_ddl` es un input (el usuario lo provee), nunca un output. Antes de rutear R7 a cualquier track hay que decidir: ¿el backend alguna vez sugiere/emite `ALTER TABLE`, o se limita a advertir en el canal que ya existe? Camino barato disponible sin abrir superficie nueva: usar el canal de `advertencias_buenas_practicas` (ya existe, ya es advisory-only, D15 ya lo trata como "notifica, no bloquea") para señalar el constraint recomendado como texto, sin que el backend emita SQL DDL real. No aplicado — queda abierto hasta que el usuario confirme el camino.

<a id="c6"></a>
### C.6 — Política de default ante FK no resuelta (R5-b/R11, `bitacora_etl_ventas.md`) `[F4]` — resuelta por D21

L2-E06 (bitácora, marcado ahí mismo como "a decidir"): una venta con `id_producto` ausente del maestro deja `fk_producto` NULL, y `fact_venta.fk_producto` es NOT NULL — el INSERT rompe.

**Resuelto 2026-07-24 — ver D21.** Política = miembro inferido (Kimball): el lookup nunca devuelve NULL, crea placeholder en la dimensión con la clave natural real y se auto-corrige (overwrite tipo 1) cuando el producto llega de verdad. Implementación: anti-join previo (SQL directo, fuera de la matriz R/W) + `Union` hacia el loader único de la dimensión — `dim_producto` conserva exactamente un writer, evita el choque con D16 sin reabrirla y sin depender de ningún orden incidental entre steps. No implementado en código todavía — trabajo de F4.

<a id="c4"></a>
### C.4 — Auditoría retroactiva de cambios no declarados `[Fundamento]`

El material de fragmentación es un **autorreporte de sesión**, no evidencia independiente: describe la división de KTR, pero la pérdida de SCD2 real y tres clases de cambio no declaradas (ver tabla de D9) no salieron a la luz hasta comparar los XML generados, varias sesiones después. Si el documento las hubiera declarado, no habrían sido un hallazgo — eso es justamente lo que D9 (registro de deltas) busca prevenir hacia adelante.

Falta hacerlo hacia atrás: por cada commit que tocó generación de KTR, comparar el mensaje del commit y lo declarado en la documentación contra el diff canónico (mismo método de D9, aplicado retroactivamente, mecánico). **Falta acotar el alcance** — hasta qué commit hacia atrás tiene sentido ir.

*Evidencia de que hace falta un chequeo así:* ya apareció un caso de afirmación no verificada en el material acumulado — se documentó que `_TABLE_FIELD_KEYS` vivía "suelto en `dimension_step_policy.py`"; verificado contra el repo, vive en `ktr_default_validator.py:54` (ver H4 en `01-hallazgos.md`).

<a id="c7"></a>
### C.7 — `ConnectionsMapRequest.conn_dwh/conn_staging` no acepta `connection_id` string `[sin track]`

**Origen:** H24 (`01-hallazgos.md`), triage de H17. Movido acá desde `04-deuda-abierta.md` (disuelto, T4) — ninguna fase lo tiene asignado y necesita una elección de producto, no trabajo.

`resolve_real_connections()` soporta reusar una `Connection` guardada como destino (rama string), pero `ConnectionsMapRequest` solo acepta `InlineConnection` — la rama string queda inalcanzable desde HTTP para `conn_dwh`/`conn_staging`. Decisión pendiente: (a) `ConnectionsMapRequest` pasa a aceptar `Union[str, InlineConnection]` (restaura el caso), o (b) se borra la rama string del service (y se reescriben/borran los tests que la ejercitan). **Nota:** mientras no se decida, produce 6 tests rojos permanentes en `test_ktr_build_job_api.py`, ya contados como ruido conocido (D26).

<a id="c8"></a>
### C.8 — `_CRITICAL_FIELDS["GetSystemInfo"]` vuelve inalcanzable su propio fallback `[sin track]`

**Origen:** H25 (`01-hallazgos.md`), triage de H17. Movido acá desde `04-deuda-abierta.md` (disuelto, T4).

`_CRITICAL_FIELDS["GetSystemInfo"]` aborta el build si falta `fields`, antes de que `_step_GetSystemInfo` pueda aplicar su default documentado (`fecha_carga`). Fix aparente trivial (sacar `"fields"` de `_CRITICAL_FIELDS`), pero es un cambio de comportamiento de validación ya en producción — no se toca sin decisión explícita de que el fallback debe ganar sobre el chequeo crítico.

<a id="c9"></a>
### C.9 — `documentacion`: ¿resto sin limpiar o campo olvidado en el schema? `[sin track]`

**Origen:** H26 (`01-hallazgos.md`), triage de H17. Movido acá desde `04-deuda-abierta.md` (disuelto, T4).

`ETL_OUTPUT_SCHEMA` no declara `documentacion` (`additionalProperties: false`), pero `ETLGenerateResponse.documentacion`/`etl_generator.py` la esperan con default vacío. Ambiguo a propósito: (a) feature vieja sacada del contrato LLM, restos sin limpiar — el campo de respuesta y el `.get()` con default sobran; o (b) olvido real al escribir el schema — debería declararse como property opcional, y hoy el usuario nunca recibe documentación generada por el LLM aunque el código esté listo para mostrarla. No se decide acá.

<a id="c10"></a>
### C.10 — Materialización de hops de datos que cruzan grupos `[F3]` — resuelta por D48

**Resuelto 2026-07-30 — ver D48.** Investigación contra doc oficial + fuente de Kettle (`investigacion-pentaho-C10-C11-C12.md`) descarta `Copy rows to result` como mecanismo general (rowset único global por `.kjb`, no memoria) y fija tabla de staging como el camino. Detalle de implementación (nombre/ciclo de vida) queda para cuando la Fase 3 se ejecute, no bloqueante.

**Origen:** Fase 3 de `03c-investigacion-vocabulario-dimension-kettle.md`, ítem 5. `split_ktr_by_cut` filtra hops a los que tienen `from` y `to` en el mismo grupo; uno que cruza se descarta sin reconectar. D45 (punto 5) decide **detectar y reportar como error**, pero no decide la materialización (tabla temporal intermedia, `Copy rows to result`, u otro mecanismo) — eso es superficie de diseño propia, no ejercitada todavía porque en la evidencia disponible (Set A/B) los grupos ya estaban desconectados en ese punto. Sin decidir.

<a id="c11a"></a>
### C.11a — `PREFERRED_SCHEMA_NAME` obligatorio en la conexión `[F4]` — resuelta por D49

**Resuelto 2026-07-30 — ver D49.** Alcance mínimo separado de C.11b: agregar `PREFERRED_SCHEMA_NAME` al emisor de `<connection>` cierra el riesgo real de `search_path` no determinista (confirmado en fuente, `DatabaseMeta.getQuotedSchemaTableCombination`) sin tocar `dim_contracts`/DDL/steps.

<a id="c11b"></a>
### C.11b — `schema` obligatorio end-to-end (multi-schema completo) como prerrequisito para entrar a la clave de la matriz `[F3]`

**Origen:** Fase 3 de `03c-investigacion-vocabulario-dimension-kettle.md`, ítem 2 (S-10), reencuadrada 2026-07-30 tras D49 — separa el alcance caro (multi-schema real) del alcance barato ya resuelto (C.11a). D45 deja `schema` **fuera** de la clave `(connection, table)` porque en los dos sets de evidencia `<schema/>` está vacío en todo step de BD — agregarlo hoy no cambiaría nada, la componente sería cadena vacía siempre. Para que sirva de verdad hace falta `schema` obligatorio en `dim_contracts` y en el modelo de staging, DDL calificado, y el emisor escribiéndolo — alcance propio, DWH multi-schema real, más allá de cerrar el riesgo de `search_path` (eso ya lo cierra C.11a). Sin decidir ni acotar.

<a id="c12"></a>
### C.12 — `checkDimZero` vs. `date_from NOT NULL` sin DEFAULT — bloqueante de ejecución de D44 `[F4]` — resuelta por D47

**Resuelto 2026-07-30 — ver D47.** Doc oficial de Pentaho confirma el modo de falla y prescribe el remedio: pre-sembrar la fila `tk=0` (no relajar el DDL). El 4º camino (config del step) no existe en Kettle, solo en Hop. Mecanismo elegido: sembrado embebido en el DDL. Detalle abajo, y ruteado a `06-contrato-ddl.md` (DDL-1).

**Origen:** corolario de R-K2, no estaba en el checklist original de 12 preguntas de `03c-investigacion-vocabulario-dimension-kettle.md` — apareció investigando R-K1 en detalle. Ver **H47** para la evidencia completa (`01-hallazgos.md`).

`checkDimZero` (Kettle, corre solo en la copia 0, primera fila, solo si el loader tiene `update=Y`) inserta la fila técnica "unknown" con `insert into <tabla>(<tk>, <version>) values (0, 1)` — dos columnas nombradas, el resto queda en su DEFAULT o NULL. `prompt_validacion_src.txt:24-26` (V1/V3) exige `date_from TIMESTAMP NOT NULL` sin DEFAULT en toda dimensión de `dim_contracts`, sin excepción por `scd_type`. Ese INSERT de dos columnas viola el NOT NULL sin DEFAULT → `KettleDatabaseException` → transformación abortada en la primera fila, no un warning. Invisible hasta hoy porque solo dispara contra tabla vacía y porque `scd_type` 0/1 usaba `CombinationLookup` (no llama `checkDimZero`) — **D44 generaliza el loader a `DimensionLookup(update=Y)` para todo `scd_type`, expandiendo el radio a toda dimensión del sistema.**

**Tres opciones que estaban sobre la mesa — resueltas por D47, la opción 2 (sembrado, en el DDL en vez de `ExecSQL`) es la elegida:**
1. ~~Agregar `DEFAULT` a `date_from` en `prompt_validacion_src.txt` (mantiene `NOT NULL`)~~ — descartada, no es el camino que prescribe el fabricante.
2. **Pre-sembrar la fila "unknown"** — elegida, mecanismo: embebida en el DDL, no vía `ExecSQL` (ver D47 para el porqué). `checkDimZero` encuentra `count != 0` y no hace nada — el mecanismo que, por accidente, pudo haber evitado el problema en corridas ya vistas si tenían la fila sembrada de otra forma (ver solape con H46/D21).
3. ~~Relajar `date_from` a NULLable~~ — descartada: funcionaría, pero no es lo que el fabricante prescribe hacer primero, y no cierra D21 (atributos NULL en vez de `'DESCONOCIDO'`) como sí lo hace el sembrado.

**Ya no bloquea** (era: dar por cerrado en código el punto 1 de D44). **Gate de verificación, ya señalado en la propia investigación:** correr contra una dimensión realmente vacía, con y sin sembrado — es la única forma de confirmarlo en runtime; ninguno de los checkers de forma de XML (V4-V13) lo detecta porque el XML sale válido. Con sembrado tiene que pasar limpio; sin sembrado tiene que abortar (si aborta con sembrado, `tk` de la fila sembrada probablemente no es `0`).
