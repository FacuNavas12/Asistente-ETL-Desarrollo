# Fase 0 — Inventario

Mapa del backend (`backend/app/`) tal como está hoy. Descriptivo, sin juicios de valor — la evaluación es Fase 2. Toda afirmación con `archivo:línea`; donde no se pudo determinar leyendo código, dice "no verificable sin ejecutar".

## 1. Árbol de directorios

**`backend/app/` (raíz)** — 2 archivos, 124 líneas.
- `main.py` (124): instancia `FastAPI`, configura logging rotativo (`main.py:41-59`), registra 5 routers (`main.py:115-119`), `lifespan` lanza dos tareas de background: drenaje del outbox (`main.py:96`) y purga de `KtrBuildJob` vencidos (`main.py:97`, función en `main.py:62-81`).
- `__init__.py`: vacío.

**`routers/`** — 5 archivos + `__init__.py` vacío, 1094 líneas.
- `ai.py` (475): endpoints del flujo IA — validar/documentar ETL, inferir estructuras, generar ETL (síncrono/async/SSE), reconstruir desde raw, linaje, generación de Jobs (.kjb).
- `connections.py` (341): CRUD de `Connection` + test de conexión real + explorador de esquema.
- `etl.py` (94): CRUD de `Etl` persistido (vía outbox) + reconexión de destino sin volver a llamar al LLM.
- `job.py` (43): CRUD simple de `Job` persistido.
- `schema.py` (141): inferencia de esquema desde archivo (CSV/Excel) y desde DDL pegado.

**`models/`** — 9 archivos + `__init__.py`, 797 líneas.
- `anthropic_llm.py` (260) / `gemini_llm.py` (270): implementaciones concretas de `BaseLLM` por proveedor.
- `llm_base.py` (47): ABC `BaseLLM`, dataclass `LLMResponse`, `extract_first_json` (fallback last-resort).
- `llm_factory.py` (44): `build_llm(settings, role)` selecciona proveedor según `settings.llm_provider`.
- `base.py` (26): `WorkflowItemMixin` (columnas compartidas por `Etl`/`Job`).
- `connection.py` (72): ORM `Connection` + enums `DbType`/`TestStatus`.
- `etl.py` (8), `job.py` (8): ORM `Etl`/`Job`, ambos solo heredan `WorkflowItemMixin`.
- `ktr_build_job.py` (59): ORM `KtrBuildJob` — correlación entre generación async y conexiones destino.

**`schemas/`** — 9 archivos + `__init__.py`, 847 líneas; subcarpeta `llm_output_schemas/` 7 archivos + `__init__.py`, 476 líneas.
- `canonical.py` (173): `CanonicalSchema`/`CanonicalField`/`CanonicalType` — esquema intermedio, converge desde los 3 adapters de entrada.
- `common.py` (28): `CamelModel` base + `WorkflowStatus`.
- `connection.py` (111): schemas Pydantic de conexión (create/update/read/test).
- `context_schemas.py` (73): `ModelContext`/`ModelTableContext`/`ColumnStats`/`ColumnProfile`.
- `etl.py` (40) / `job.py` (34): schemas de persistencia simple.
- `etl_schemas.py` (271): contratos del flujo de generación IA (`ETLGenerateResponse`, `EtapaOutput`, `DimContract`, `StepETL`) — ver sección 5.
- `job_schemas.py` (95): `JobPlan`/`JobEntry` del flujo de generación de `.kjb`.
- `lineage.py` (22): `Lineage`/`LineageNode`/`LineageEdge`.
- `llm_output_schemas/`: un archivo por JSON Schema de salida estructurada — `etl_output.py` (152, define `ETL_OUTPUT_SCHEMA`), `inference_output.py` (107), `job_plan_output.py` (90), `ddl_validation_output.py` (53), `validator_output.py` (26), `document_output.py` (10), `job_explain_output.py` (10).

**`services/`** (top-level) — 21 archivos + `__init__.py` vacío, 4898 líneas. Carpeta más grande del backend.
- `etl_generator.py` (1188): orquestador central del flujo ETL — ver sección 3.
- `job_analyzer.py` (550): análisis/refinamiento/generación de Jobs PDI desde `.ktr` subidos.
- `db_connector.py` (631): conexión real a la BD externa del usuario (test, list tables, columnas, FKs, sample rows, datos paginados).
- `profiler.py` (274): perfilado estadístico de columnas (agregados SQL + muestra ≤20 filas).
- `dialect.py` (258): capa de dialecto SQL (Postgres/SQL Server) que usa el profiler.
- `context_builder.py` (224): arma `ModelContext` desde 4 caminos (DB/archivo/DDL/manual) — único punto de serialización a texto de prompt.
- `etl_service.py` (199): CRUD de `Etl`, outbox local + Supabase.
- `structure_inferrer.py` (192): inferencia automática de DDL STG/DWH desde 3 campos de usuario.
- `type_mappings.py` (174): mapeo tipos SQL crudos → `CanonicalType`.
- `file_schema.py` (132): inferencia de esquema desde CSV/Excel vía Frictionless.
- `ddl_validation.py` (123): audita/corrige DDL DWH contra `dim_contracts` vía LLM, antes de armar el prompt del KTR STG→DWH.
- `ktr_default_validator.py` (170): scrub de constantes con función SQL + chequeo de columnas NOT NULL sin mapeo.
- `ktr_xml_validator.py` (117): lint post-generación del XML `.ktr` (última barrera, `KtrXmlValidationError`).
- `kjb_xml_validator.py` (101): lint post-generación del `.kjb`.
- `masker.py` (86): enmascarado format-preserving de valores de muestra.
- `documenter.py` (48): documentación en lenguaje natural (LLM).
- `validator.py` (38): validación de calidad/malas prácticas (LLM).
- `job_service.py` (43): CRUD de `Job` directo contra repo (sin outbox).
- `sql_defaults.py` (51): clasifica un DEFAULT SQL como literal vs función/expresión.
- `validate_business_rules.py` (24): chequeo heurístico de reglas de negocio reflejadas en steps.
- `lineage_builder.py` (275): construcción del grafo de linaje — ver sección 3.

**`services/ktr_builder/`** — 12 archivos + `__init__.py`, 3522 líneas. Serializador JSON→XML `.ktr`.
- `build.py` (407): orquestador — normaliza config, valida, resuelve conexiones, emite XML final (`build_ktr`).
- `contracts.py` (435): alias de clave + semántica produce/consume por tipo de step (`parse_cfg`, `normalize_config`, `STEP_CONTRACTS`).
- `fields_validate.py` (446): validación de resolución de campos en orden topológico.
- `error_catalog_checks.py` (424): auditoría del catálogo E1-E14 sobre el XML ya serializado.
- `repair.py` (324): reparación de steps con config incompleto, LLM acotado a un step por vez.
- `registry.py` (309): registro central de step types (`STEP_TYPE_ALIASES`, `STEP_BUILDERS`, `KNOWN_PDI_STEP_TYPES`, `_CRITICAL_FIELDS`).
- `connection.py` (332): resolución/serialización de conexiones Kettle, incl. `resolve_real_connections` (`:93`).
- `fragmentation.py` (312): motor de corte F3 — parte un KTR en N sub-transformaciones según matriz R/W.
- `dimension_step_policy.py` (275): deriva/fuerza tipo de step de dimensión según `scd_type`.
- `validate.py` (118): validación estructural pre-XML.
- `layout.py` (52): auto-layout x/y de steps sin posición.
- `common.py` (36): helper compartido.
- `__init__.py` (52): reexporta API pública del paquete.

**`services/ktr_builder/steps/`** — 5 archivos + `__init__.py` vacío, 1311 líneas. Un builder XML por familia de step Kettle.
- `transform.py` (417), `lookups.py` (204), `output.py` (257), `input.py` (255), `control.py` (178).

**`services/adapters/`** — 4 archivos + `__init__.py` vacío, 559 líneas. Convergen en `CanonicalSchema`.
- `ddl_adapter.py` (294), `frictionless_adapter.py` (100), `schema_to_context.py` (86), `db_adapter.py` (79).

**`services/superset_client/`** — 9 archivos + `__init__.py`, 1292 líneas. Cliente API REST de Superset.
- `client.py` (124), `dashboard.py` (290), `charts.py` (190), `dwh_tables.py` (178), `database.py` (132), `zip_tools.py` (212), `datasets.py` (113), `constants.py` (12), `errors.py` (6).

**`services/superset_export/`** — 6 archivos + `__init__.py`, 1165 líneas. Arma el ZIP de export (`assets/import/`), sin LLM.
- `asset_yaml.py` (349), `zip_builder.py` (308, `build()` en `:196`), `chart_selection.py` (227), `semantic_types.py` (124), `constants.py` (87), `synthetic_values.py` (44).

**`core/`** — 6 archivos + `__init__.py` vacío, 402 líneas.
- `auth.py` (153, JWT/JWKS), `config.py` (103, `Settings` env vars), `database.py` (64, engine/sessionmaker), `dependencies.py` (33, DI de LLM), `log_filters.py` (31), `sanitize.py` (18).

**Fuera del alcance pedido pero presentes bajo `backend/app/`:**
- `outbox/` (4 + `__init__.py`, 405 líneas): `sqlite_outbox.py` (134), `drainer.py` (119), `runner.py` (85), `port.py` (34).
- `repositories/` (3 + `__init__.py` vacío, 46 líneas): `base.py` (38, `BaseRepository` genérico), `etl_repository.py`/`job_repository.py` (4 líneas c/u).
- `backend/prompts/` (fuera de `app/`, no `.py`): 7 `.txt` con los system prompts, cargados en runtime.

## 2. Puntos de entrada

**`ai.py`** (todos bajo `Depends(require_auth)`, `routers/ai.py:53`):

| Método + ruta | archivo:línea | Cadena |
|---|---|---|
| `POST /api/v1/etl/validate` | `routers/ai.py:90-96` | router → `validator.validate_etl` → LLM (secondary) |
| `POST /api/v1/etl/document` | `routers/ai.py:99-105` | router → `documenter.document_etl` → LLM (secondary) |
| `POST /api/v1/etl/infer-structures` | `routers/ai.py:110-117` | router → `structure_inferrer.infer_structures` → `context_builder` (lee DB si origen es DB) → LLM (main) |
| `POST /api/v1/etl/infer-structures/refine` | `routers/ai.py:120-127` | router → `structure_inferrer.refine_structures` → LLM (main) |
| `POST /api/v1/etl/generate-from-inference` | `routers/ai.py:130-137` | router → `etl_generator.generate_etl_from_inference` (ver sección 3) |
| `POST /api/v1/etl/build-from-raw` | `routers/ai.py:140-150` | router → `etl_generator.build_etl_from_raw` → `ktr_builder`, LLM opcional |
| `POST /api/v1/etl/generate-async` | `routers/ai.py:220-241` | router → **DB directo** (`db.add(KtrBuildJob)`) + `asyncio.create_task(generate_etl_async)` → LLM → DB directo |
| `POST /api/v1/etl/{job_id}/connections` | `routers/ai.py:244-269` | router → **DB directo** + `etl_generator._try_build` → `ktr_builder.resolve_real_connections` (DB) → DB directo |
| `GET /api/v1/etl/{job_id}/status` | `routers/ai.py:272-280` | router → **DB directo**, sin service/repo |
| `POST /api/v1/etl/generate-from-inference/stream` | `routers/ai.py:283-349` | router (SSE) → `etl_generator.generate_etl_from_inference` |
| `POST /api/v1/etl/{etl_id}/superset/export` | `routers/ai.py:362-398` | router → **DB directo** + `superset_export.build` + `superset_client.import_dashboard` → API externa |
| `POST /api/ai/lineage-from-ktr` | `routers/ai.py:407-420` | router → `lineage_builder.build_lineage_from_xml`/`stitch_lineage_from_xml` (puro) |
| `POST /api/v1/job/analyze` | `routers/ai.py:425-440` | router → `job_analyzer.analyze_job` → LLM (main) + filesystem temporal |
| `POST /api/v1/job/refine` | `routers/ai.py:443-456` | router → `job_analyzer.refine_job` → LLM (main) |
| `POST /api/v1/job/generate` | `routers/ai.py:459-475` | router → `job_analyzer.generate_job` → `kjb_xml_validator` (LLM solo para la explicación) |

**`connections.py`** (prefix `/api/connections`):

| Método + ruta | archivo:línea | Cadena |
|---|---|---|
| `POST /api/connections` | `routers/connections.py:78-111` | router → **DB directo**, sin service/repo |
| `GET /api/connections` | `routers/connections.py:114-123` | router → DB directo |
| `GET /api/connections/{conn_id}` | `routers/connections.py:126-132` | router → DB directo |
| `PUT /api/connections/{conn_id}` | `routers/connections.py:135-159` | router → DB directo |
| `DELETE /api/connections/{conn_id}` | `routers/connections.py:162-170` | router → DB directo |
| `POST /api/connections/{conn_id}/test` | `routers/connections.py:175-190` | router → `db_connector.test_connection` → BD real + DB directo (update status) |
| `GET /.../{conn_id}/schema/tables` | `routers/connections.py:195-210` | router → `db_connector.list_tables` → BD real |
| `GET /.../{table_name}/columns` | `routers/connections.py:213-242` | router → `db_connector.get_columns` → `adapters.db_adapter.build` → BD real |
| `GET /.../{table_name}/profile` | `routers/connections.py:245-309` | router → `db_connector` + `profiler` + `db_adapter` → BD real |
| `GET /.../schema/table-data` | `routers/connections.py:312-341` | router → `db_connector.get_table_data` → BD real |

**`schema.py`** (prefix `/api/schema`):

| Método + ruta | archivo:línea | Cadena |
|---|---|---|
| `POST /api/schema/infer` | `routers/schema.py:32-91` | router → filesystem temporal → `file_schema.infer_file_schema` → `frictionless` |
| `POST /api/schema/from-ddl` | `routers/schema.py:104-141` | router → `adapters.ddl_adapter.parse_ddl` (sqlglot, puro) |

**`etl.py`** (prefix `/api/etls`):

| Método + ruta | archivo:línea | Cadena |
|---|---|---|
| `GET /api/etls/` | `routers/etl.py:19-21` | router → `etl_service.list_etls` → `etl_repository` (DB) + outbox local |
| `POST /api/etls/` | `routers/etl.py:24-27` | router → `etl_service.create_etl` → outbox local |
| `GET /api/etls/{id}` | `routers/etl.py:30-32` | router → `etl_service.get_etl` → outbox + `etl_repository` |
| `PUT /api/etls/{id}` | `routers/etl.py:35-37` | router → `etl_service.update_etl` → outbox |
| `PATCH /api/etls/{id}/status` | `routers/etl.py:40-42` | router → `etl_service.set_etl_status` → outbox |
| `DELETE /api/etls/{id}` | `routers/etl.py:45-47` | router → `etl_service.delete_etl` → outbox + `etl_repository` (DB) |
| `POST /api/etls/{id}/connections` | `routers/etl.py:50-94` | router → `etl_service.get_etl` + `ktr_builder.resolve_real_connections` (DB) + `etl_generator._build_response_from_two_ktr_data` (sin LLM) → `etl_service.update_etl` |

**`job.py`** (prefix `/api/jobs`) — todos vía `job_service` → `job_repository` (DB directo, **sin outbox**): `GET /` (`routers/job.py:16-18`), `POST /` (`:21-23`), `GET /{id}` (`:26-28`), `PUT /{id}` (`:31-33`), `PATCH /{id}/status` (`:36-38`), `DELETE /{id}` (`:41-43`).

## 3. Flujo del step

### 3.1 Construcción del prompt del LLM

`_build_prompt_from_inference` (`services/etl_generator.py:791-918`) arma el texto según `mode`: `None` monolítico (`:818-843`), `"origen_stg"` KTR_1 (`:845-878`), `"stg_dwh"` KTR_2 (`:880-918`). Usa `_format_dim_contracts` (`:176-204`) y `_format_inferred_member_dims` (`:268-291`). `_load_system` (`:455-456`) lee `backend/prompts/system_etl.txt` desde disco. `context_builder.build_model_context` (`services/context_builder.py:156`) + `format_model_context_for_prompt` (`:182`) son el único punto de serialización de esquema de origen a texto de prompt (según el docstring del propio archivo, `:10-11`). Prompts equivalentes en otros flujos: `ddl_validation._build_prompt` (`services/ddl_validation.py:45`), `structure_inferrer._build_infer_prompt`/`_build_refine_prompt` (`:69`, `:101`), `job_analyzer._build_analyze_prompt`/`_build_refine_prompt`/`_build_explain_prompt` (`:148`, `:167`, `:201`).

### 3.2 Recepción/parseo de la respuesta del LLM

Gemini: `models/gemini_llm.py:189-191` — `json_data = json.loads(raw)` (respuesta ya es texto JSON por `response_mime_type`). Anthropic: `models/anthropic_llm.py:180-187` — `json_data = block.input` extraído de un bloque `tool_use` (ya es dict, sin `json.loads`; `raw = json.dumps(...)` en `:184` solo para loguear). Ambos producen `LLMResponse` (`models/llm_base.py:8-17`) con `json_data: Optional[Dict[str, Any]]`. Flujo monolítico legacy: `_build_response` lee `resp.json_data` (`etl_generator.py:688-709`, uso en `:694`). Flujo de 2 KTR: `data_1`/`data_2` desde `resp_1.json_data`/`resp_2.json_data` (`:952-953`, y `:1108-1109` en la variante async). `ETLGenerateResponse`/`EtapaOutput` (`schemas/etl_schemas.py:92-107`, `:77-89`) son shape de **salida**, no de entrada — el `dict` que llega del LLM no pasa por validación Pydantic hasta ensamblar la respuesta final.

### 3.3 Cada punto donde `config` de un step se lee/parsea/transforma

Función canónica: `parse_cfg` (`services/ktr_builder/contracts.py:38-54`, `json.loads` en `:51`, lanza `ConfigParseError` en vez de degradar a `{}`). Call-sites (exhaustivo):

| # | archivo:línea | Contexto |
|---|---|---|
| 1 | `ktr_builder/contracts.py:38-54` | `parse_cfg()` — función canónica |
| 2 | `ktr_builder/contracts.py:389-396` | `normalize_config()` — alias de clave → canónica |
| 3 | `ktr_builder/contracts.py:399-426` | `normalize_step_configs()` — primer paso del pipeline, parsea string→dict in-place (`:419`) |
| 4 | `ktr_builder/contracts.py:429-435` | `missing_required_keys()` |
| 5 | `etl_generator.py:137` | `_type_mismatch_warnings` — cast de `SelectValues` |
| 6 | `etl_generator.py:493-509` | Diagnóstico en `_build_response_from_data`, `json.loads` manual (`:496`), solo loguea |
| 7 | `ktr_builder/build.py:122-136` | Loop de normalización, reasigna `step["config"]` (`:132`) |
| 8 | `ktr_builder/build.py:196-219` | Chequeo de campos críticos (`:203`) |
| 9 | `ktr_builder/build.py:221-239` | Resolución de conexión por step (`:227`) |
| 10 | `ktr_builder/build.py:324-364` | Loop de emisión XML final, fallback string (`:328-340`) |
| 11 | `ktr_builder/fields_validate.py:83` | `_nearest_incomplete_ancestor` |
| 12 | `ktr_builder/fields_validate.py:151,170` | `repair_select_values_narrowing` |
| 13 | `ktr_builder/fields_validate.py:184-200` | Reinyección de campo — reescribe `pred_step["config"]` |
| 14 | `ktr_builder/fields_validate.py:234` | `find_missing_field_producers` |
| 15 | `ktr_builder/fields_validate.py:318` | `find_nearest_source_table_name` |
| 16 | `ktr_builder/fields_validate.py:422` | `validate_dimension_lookup_races` |
| 17 | `ktr_builder/dimension_step_policy.py:67` | `_write_target_table` |
| 18 | `ktr_builder/dimension_step_policy.py:157` | `enforce_dimension_step_policy`, loop principal |
| 19 | `ktr_builder/dimension_step_policy.py:219-222` | Mutación: fuerza `update="N"` |
| 20 | `ktr_builder/dimension_step_policy.py:245-252` | Mutación: reescribe `config` al convertir `DimensionLookup`→`CombinationLookup` |
| 21 | `ktr_builder/fragmentation.py:60` | `build_rw_matrix` (motor de corte F3) |
| 22 | `ktr_builder/repair.py:152-153` | `repair_ktr_steps`, normaliza y reasigna |
| 23 | `ktr_builder/repair.py:171` | Reasigna tras respuesta del LLM de reparación |
| 24 | `ktr_builder/repair.py:200` | `_find_twin_constant_config` |
| 25 | `ktr_builder/repair.py:283,302` | `repair_integrity_gaps`, rama LLM |
| 26 | `ktr_builder/repair.py:311,317` | `repair_integrity_gaps`, fallback determinístico |
| 27 | `ktr_builder/validate.py:81` | `_validate_ktr` — columnas SELECT duplicadas |
| 28 | `ktr_builder/validate.py:100` | `_validate_ktr` — `Calculator`/`Formula` encadenado |
| 29 | `ktr_default_validator.py:75,95` | `scrub_function_default_constants`, primer loop |
| 30 | `ktr_default_validator.py:105,119` | `scrub_function_default_constants`, segundo loop |
| 31 | `ktr_default_validator.py:148` | `check_missing_required_fields` |
| 32 | `lineage_builder.py:45-56` | `_extract_table` — `normalize_config(...).get("table")` |
| 33 | `lineage_builder.py:115` | `build_lineage` |
| 34 | `lineage_builder.py:200,206` | `stitch_lineage_many` |
| 35 | `lineage_builder.py:231-256` | `_parse_ktr_xml` — camino inverso, reconstruye `config` mínimo leyendo XML ya serializado (solo `/api/ai/lineage-from-ktr`) |

Puntos 11-16, 21, 27-31: solo lectura. Puntos 13, 18-20, 22-26, 29-30: mutan `step["config"]` in-place.

### 3.4 Generación del XML final

`build_ktr` (`ktr_builder/build.py:69-407`) — punto único de entrada del paquete. Pasos internos: normalización (`:122-136`), `_validate_ktr` (`:138`), `scrub_function_default_constants` (`:145`), `check_missing_required_fields` (`:150`), `repair_select_values_narrowing` (`:159`), validaciones de integridad (`:180-186`), campos críticos (`:196-219`), resolución de conexiones (`:221-239`), emisión XML por step vía `STEP_BUILDERS[canonical_type]` (`:347/364`), última barrera `validate_ktr_xml` (`:405`). Builders concretos en `ktr_builder/steps/{input,output,lookups,transform,control}.py`, registrados en `registry.py:153` (`STEP_BUILDERS`). `.kjb`: `job_analyzer.build_kjb_xml` (`:225`).

### 3.5 Construcción del linaje

`build_lineage` (`lineage_builder.py:84-129`) desde el dict KTR (no XML). `stitch_lineage_many` (`:132-220`) generaliza a M archivos. `stitch_lineage` (`:223-228`) wrapper de compatibilidad M=2, usado por el endpoint público. `build_lineage_from_xml`/`stitch_lineage_from_xml` (`:268-275`) variante desde XML serializado.

### 3.6 Orden de llamadas — `generate_etl_from_inference` (`etl_generator.py:921-999`)

1. `:935` — `validate_and_correct_ddl(req.dwh_model, req.dim_contracts, llm)` (`ddl_validation.py:77`) — LLM.
2. `:938-939` — `build_model_context` + `format_model_context_for_prompt`.
3. `:940` — `_staging_table_names_from_ddl` (`:160-173`).
4. `:941` — `_load_system("system_etl.txt")`.
5. `:943-944` — arma `prompt_1` (`origen_stg`) + **LLM #1**.
6. `:946-947` — arma `prompt_2` (`stg_dwh`, con `dwh_ddl` corregido) + **LLM #2**.
7. `:952-953` — extrae `data_1`/`data_2`.
8. `:961-962` — `normalize_step_configs(data_1["ktr"])`/`(data_2["ktr"])`.
9. `:964-965` — `repair_ktr_steps(...)` sobre ambos KTR (puede llamar LLM por step, `repair.py:136`).
10. `:966-967` — `repair_integrity_gaps(...)` sobre ambos KTR (`repair.py:230`).
11. `:975-985` — warnings heurísticos: `_required_columns_from_ddl`, `_type_mismatch_warnings`, `_dim_contracts_anomaly_warning`, `_inferred_member_notifications`, `validate_business_rules` (×2, `:983-984`).
12. `:986-988` — `enforce_dimension_step_policy(data_2["ktr"], ...)` (`dimension_step_policy.py:121`) — determinístico, muta in-place, corre antes del build.
13. `:989-999` — `_build_response_from_two_ktr_data(...)` (`:557-685`): `_build_ktr_stage` (`:306-344`) por cada KTR → `split_ktr_by_cut` (`fragmentation.py:256`) → `build_ktr` (`ktr_builder/build.py:69`) por grupo → `_build_job_plan` (`:366-443`) → `build_kjb_xml` si N>1 → `stitch_lineage_many` (`lineage_builder.py:132`, `:658-661`) → ensambla `ETLGenerateResponse` (`:672-685`).

`generate_etl_async` (`:1083-1188`) repite el mismo orden (pasos 1-12) pero persiste el intermedio en `KtrBuildJob.model_json` (`:1156`); el build real ocurre después en `_try_build` (`:1008-1080`), cuando las conexiones destino están disponibles.

## 4. Fuentes de datos externas

| Fuente | Dónde entra | Tipo al entrar |
|---|---|---|
| Respuesta LLM (Gemini) | `models/gemini_llm.py:185` (`raw = response.text`), `:191` (`json.loads`) | `str` → `dict` sin validar Pydantic |
| Respuesta LLM (Anthropic) | `models/anthropic_llm.py:182-183` (`json_data = block.input`) | `dict` directo del SDK |
| BD externa del usuario | `services/db_connector.py:397` (columns), `:442` (FKs), `:532` (sample rows), `:575` (table data) | `list[ColumnInfo]` (Pydantic) para columnas; filas crudas vía `_serialize_row` (`:138-146`) |
| Archivo subido (CSV/Excel) | `routers/schema.py:56-68` (temp file) → `file_schema.py:35` | bytes → archivo en disco → `CanonicalSchema` |
| DDL pegado | `routers/schema.py:104-129` → `adapters/ddl_adapter.py` | `str` → AST sqlglot → `list[CanonicalSchema]` |
| Config/env vars | `core/config.py:9-103` (`Settings(BaseSettings)`, lee `.env` en `:6,10`) | tipado Pydantic `BaseSettings` |
| API Superset | `services/superset_client/client.py`, invocado desde `routers/ai.py:385-391` | HTTP (`httpx`) → dict JSON |

No verificable sin ejecutar: si los SDKs de LLM validan internamente el JSON contra el schema antes de entregarlo — no hay validación Pydantic explícita del `dict` de entrada en `etl_generator.py`.

## 5. Estructuras de datos en circulación (step/config)

1. **JSON Schema de entrada** — `schemas/llm_output_schemas/etl_output.py:92-119` (`ktr.steps[*] = {name, type, config: string}`, `config` explícitamente string JSON, justificado en `:1-14`). Solo lo consume el SDK del LLM al decodificar.
2. **`dict` sin tipar `{name, type, config, x, y}`** — vehículo real y dominante. Sin definición formal; sale de `resp.json_data["ktr"]["steps"]` (`etl_generator.py:952-953`) y viaja mutado por referencia por `contracts.py`, `build.py`, `fields_validate.py`, `repair.py`, `fragmentation.py`, `dimension_step_policy.py`, `validate.py`, `ktr_default_validator.py`, `lineage_builder.py`, `steps/*.py` (sección 3.3 completa).
3. **`StepContract` (dataclass frozen)** — `ktr_builder/contracts.py:133-140`. Contrato *por tipo* (no instancia): `STEP_CONTRACTS: dict[str, StepContract]` (`:291-378`), consumido por `fields_validate.py`, `repair.py`, `build.py`.
4. **`StepETL` (Pydantic)** — `schemas/etl_schemas.py:43-49` (`{orden, tipo_step_pdi, nombre, descripcion, configuracion: dict, justificacion}`). Resumen legible para frontend dentro de `ProcesoETL.steps` (`:52-55`), armado aparte de `data["proceso_etl"]["steps"]` (`etl_generator.py:628-631`) — no es lo que `build_ktr` consume.
5. **`JobEntry`/`JobPlan` (Pydantic)** — `schemas/job_schemas.py:42-67`. No es step sino entrada de Job que referencia un archivo `.ktr`/`.kjb` entero (`filename`, `entry_type`), construido en `etl_generator._build_job_plan` (`:366-443`) y `job_analyzer.py`.
6. **Reconstrucción desde XML** — `lineage_builder.py:231-256` (`_parse_ktr_xml`), quinto shape ad-hoc `{name, type, config: {sql, table, filename}}` leído directo del XML `<step>`, solo para el endpoint de linaje sin dict original.

No verificable sin ejecutar: si el LLM alguna vez devuelve `config` como objeto real (violando el `"type": "string"` declarado) — `build.py:328-340` y `contracts.py:38-54` contemplan ambos casos, lo que sugiere que ocurrió históricamente, sin confirmación por logs reales.

## 6. Tests

**`backend/tests/`** — 34 archivos `test_*.py` + `README.md` + `fixtures/connections_sample.ktr`. Sin `conftest.py` en todo el repo.

- **Requiere servidor HTTP real (`localhost:8000`):** `test_api.py` (`requests.post` directo, ej. `:122,135,145`).
- **Llamadas reales a API de LLM, consumen cuota** (`@pytest.mark.integration`): `test_structured_outputs.py` (`:139,257,431,546,658`; exclusión documentada en su propio docstring `:1-13`).
- **SQLite en memoria (engine SQLAlchemy real, sin DB externa):** `test_connections_api.py`, `test_etl_job_crud.py`, `test_ktr_build_job_api.py`, `test_ktr_connection_resolution.py`, `test_fase1_canonical.py`.
- **Unitarios/mocks, sin red/DB/filesystem:** `test_connection_schemas.py`, `test_db_connector.py`, `test_dialect.py`, `test_dimension_step_policy.py`, `test_error_catalog_checks.py`, `test_fragmentation.py`, `test_fragmentation_wiring.py`, `test_inferred_member.py`, `test_job_entry_job.py`, `test_ktr_default_validator.py`, `test_ktr_step_repair.py` (mock LLM `AsyncMock`), `test_ktr_integrity_repair.py`, `test_ktr_xml_validator.py`, `test_lineage_builder.py`, `test_profiler.py`, `test_sql_defaults.py`, `test_validate_ktr_defensive.py`, `test_config_parse_fail_fast.py`, `test_canonical_schema.py`, `test_ktr_builder_fidelity.py`, `test_ktr_connection_golden.py`, `test_etl_generate_response_shape.py`, `test_context_safety.py`.
- **Filesystem real (temp files, sin red):** `test_file_schema.py`, `test_ddl_adapter.py`, `test_ddl_adapter_defaults.py`.
- **ZIP con cliente Superset mockeado:** `test_superset_export.py`.

**`backend/tests_manual_llm/`** — 1 archivo (`test_h9_h10_live_scenario.py`) + `README.md`. Fuera de la colección de `pytest.ini` (`python_files = tests/test_*.py`) — llamada real al LLM configurado en `.env`, cobra por llamada, solo corre a mano.

No verificable sin ejecutar: cuántos tests "SQLite en memoria" fallarían con migraciones Alembic reales en vez de `Base.metadata.create_all` (carpeta `alembic/` fuera de este alcance).

---

Lo más sorprendente: `config` de un step convive en **6 representaciones distintas** (JSON Schema string, dict mutable dominante, `StepContract` de contrato, `StepETL.configuracion` — que el propio JSON Schema del LLM nunca permite poblar, `additionalProperties:false` en `etl_output.py:36-49` —, `JobEntry` de orquestación .kjb, y el shape reconstruido desde XML en `lineage_builder._parse_ktr_xml`), con 35 call-sites repartidos en 9 módulos que la leen o mutan; de paso, `test_api.py` apunta a dos rutas (`/api/ai/etl`, `/api/v1/etl/generate`) que ya no existen en ningún router actual.
