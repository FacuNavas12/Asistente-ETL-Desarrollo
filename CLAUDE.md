# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Refactor de fragmentación en curso

El sistema hoy fuerza todo ETL a 2 KTR fijos (Origen→STG, STG→DWH) + 1 KJB. Ese forzado está identificado como la causa raíz de una clase de errores (carreras lectura/escritura, dimensiones no cargadas, doble escritor) y se está desacoplando: la fase lógica queda, pero el backend decide de forma determinista cuántos archivos físicos la materializan.

- **`docs/refactor/02-decisiones.md`** — fuente de verdad. Manda sobre cualquier análisis o plan que lo contradiga.
- **`docs/refactor/00-objetivo.md`** — qué habilita el refactor y el estado final deseado.
- **`docs/refactor/01-hallazgos.md`** — problemas estructurales detectados, con `archivo:línea` y estado.
- **`docs/refactor/03-plan.md`** — fases derivadas, con dependencias.
- **`docs/arquitectura-objetivo.md`** — doctrina de capas (Track A, migración aparte, hoy pospuesta) para cuando el backend se reorganice en `api/schemas/services/domain/ports/infrastructure/core`. No aplicada todavía — nada del código actual respeta esta estructura de carpetas.

**Toda sesión que tome una decisión sobre este refactor cierra actualizando `docs/refactor/02-decisiones.md` en el mismo turno** — no dejarla implícita en el código ni en el historial de chat.

## Dev Commands

**Frontend** (React 19 + Vite):
```bash
cd frontend
npm install        # after git pull si package.json cambió
npm run dev        # dev server → http://localhost:5173
npm run build      # production build → dist/
npm run lint       # ESLint
npm run preview    # preview production build
```

**Al agregar dependencia frontend:**
```bash
cd frontend
npm install <paquete>          # instala y actualiza package.json + package-lock.json
# commitear ambos: package.json Y package-lock.json
```
Otros devs solo necesitan `npm install` al hacer pull. No agregar paquetes sin commitear `package-lock.json`.

**Al hacer `git pull` y `package.json` cambió:**
```bash
cd frontend && npm install     # sincronizar node_modules
```

**Backend** (FastAPI):
```bash
cd backend
venv\Scripts\activate            # Windows venv
uvicorn app.main:app --reload   # → http://localhost:8000
```

Backend reads env vars from `backend/.env`. El proveedor LLM se selecciona con `LLM_PROVIDER` (default: `gemini`; usar `anthropic` para Anthropic). Gemini: `GOOGLE_API_KEY`, `GEMINI_MODEL`. Anthropic: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`. Todo configurable en `backend/app/core/config.py`.

## Architecture

React SPA with Auth0 auth talking to FastAPI backend. Backend proxies LLM (Gemini o Anthropic, switchable en runtime via `LLM_PROVIDER`) and manages schema extraction. ETL/Job state persiste en DB (SQLAlchemy, `backend/app/core/database.py`, default SQLite via `DATABASE_URL`, prod típicamente Postgres/Supabase) en tablas `etls` / `jobs` / `ktr_build_jobs` / `connections`; `result`/`result_json`/`form_data` son columnas `JSON` opacas (sin schema fijo en DB, el contrato vive en los Pydantic schemas del backend). Versionado de schema vía Alembic (`backend/alembic/`) — correr `alembic upgrade head` tras un `git pull` que traiga una migración nueva, nunca depender de `create_tables()`/`Base.metadata.create_all` para cambios de schema en DB compartidas. `EtlContext.jsx` en el frontend solo mantiene un draft en `sessionStorage` (2h TTL) mientras se arma el formulario — el ETL confirmado se persiste vía API contra esa DB, no en `localStorage`.

**Principios de diseño NO negociables:**
- Al LLM solo se le envía la ESTRUCTURA de las tablas (esquema, tipos, formatos, reglas), nunca filas de datos.
- El backend NUNCA persiste contraseñas de conexión a bases de datos (origen/staging/DWH). El modelo `Connection` solo guarda metadata (host/puerto/base/usuario/tipo/ssl_mode); el password viaja por request en cada operación que conecta de verdad (crear conexión, test, exploración de esquema, build del `.ktr`) y vive solo en memoria del lado que lo usa — nunca en una columna, nunca en `sessionStorage`/`localStorage`. Ver "Credenciales de conexión" más abajo.

**Frontend structure:**
```
src/
  routes/AppRouter.jsx          — PrivateRoute wraps auth-gated pages
  context/EtlContext.jsx        — ETL CRUD + draft persistence + schema_version validation
  context/ThemeContext.jsx      — dark/light toggle
  api/connections.js            — clientes HTTP para /api/connections/*
  api/schema.js                 — inferSchema(), parseDDL(), canonicalSchemaToTablaOrigen()
  pages/CreateETL/
    CreateETL.jsx               — main ETL form wizard, owns all form state
    components/Input/
      InputForm.jsx             — selector de modo (formulario/CSV/Excel/Conexiones/DDL)
      InputCSV.jsx              — sube archivo → POST /api/schema/infer → CanonicalSchema
      InputExcel.jsx            — ídem para .xlsx/.xls
      InputConnection.jsx       — conexión BD → GET /profile → CanonicalSchema + PK/FK badges
      InputDDL.jsx              — textarea DDL → POST /api/schema/from-ddl → CanonicalSchema[]
      InputFormulario.jsx       — entrada manual de columnas
    components/Tables/
      tableUtils.jsx            — useTableEditor, useTableList, ColumnTable (hooks y componentes compartidos)
      TableCatalogConnection.jsx
      TableConfirmPanel.jsx
      TableDataPreview.jsx
      TableManagement/ConfirmedTablesList.jsx
    components/Staging/StagingForm.jsx
    components/DWH/DwhForm.jsx
    components/BussinesRules/
      BussinesRulesForm.jsx
      BusinessRulesDrawer.jsx
    components/InferenceReview/InferenceReview.jsx
    components/Goal/GoalDescription.jsx
    validation/
      etlform.js                — validateForm({ origenTables, stagingDef, reglasNegocio, dwhModel })
      stringCleaners.js         — naming conventions for DWH tables/columns
  pages/EtlDetail/EtlDetail.jsx — result display + chart
  pages/CreateJob/
    CrearJob.jsx
    components/ (JobForm.jsx, JobResult.jsx, JobReview.jsx)
  pages/Home/Home.jsx
  pages/Settings/Settings.jsx
```

**Backend structure:**
```
app/
  main.py                         — FastAPI app, mounts routers (ai, connections, schema, etl, job)
  routers/
    ai.py                         — POST /api/ai/chat (ETL generation) + /superset/export; requiere auth
    connections.py                — CRUD /api/connections/* + schema explorer; requiere auth + ownership (ver Auth)
    schema.py                     — POST /api/schema/infer (CSV/Excel via Frictionless)
                                    POST /api/schema/from-ddl (DDL via sqlglot); requiere auth
    etl.py                        — CRUD /api/etls/*; requiere auth (sin ownership check todavía)
    job.py                        — CRUD /api/jobs/*; requiere auth (sin ownership check todavía)
  models/
    llm_base.py                   — BaseLLM ABC + LLMResponse dataclass (interfaz común)
    gemini_llm.py                 — GeminiLLM: retries 4× con backoff exponencial en 429/503
    anthropic_llm.py              — AnthropicLLM: ídem para Anthropic
    llm_factory.py                — build_llm(settings, role) → BaseLLM; sin singletons
    connection.py                 — Connection ORM model, DbType enum (postgresql | sqlserver).
                                    SIN columna de password (nunca se persiste — ver "Credenciales de
                                    conexión"). owner_id: String (claim "sub" del JWT, no UUID).
    base.py                       — WorkflowItemMixin (id/name/status/form_data/result JSON/created_at/updated_at)
    etl.py                        — Etl ORM model (tabla `etls`, usa WorkflowItemMixin)
    job.py                        — Job ORM model (tabla `jobs`, usa WorkflowItemMixin)
    ktr_build_job.py               — KtrBuildJob ORM model (tabla `ktr_build_jobs`, flujo async de generación 2-KTR).
                                    owner_id: String (mismo criterio que Connection) — resolve_real_connections
                                    lo usa para rechazar conn_id de otro owner.
  schemas/
    canonical.py                  — CanonicalSchema, CanonicalField, CanonicalType (central)
    etl_schemas.py                — ETLRequest, TablaOrigen (con canonical_schema), ColumnaOrigen
    connection.py                 — ColumnInfo (DTO interno), ConnectionRead (password siempre "********"), etc.
                                    Create acepta `password` en el body (validado, nunca persistido);
                                    Update ya no tiene campo password (no hay nada que actualizar).
    context_schemas.py            — ColumnProfile, ColumnStats, ModelContext (prompt layer)
    job_schemas.py                — schemas del flujo CreateJob
  services/
    context_builder.py            — build_model_context() → 4 paths → ModelContext → prompt
    file_schema.py                — infer_file_schema() via Frictionless (CSV/Excel)
    type_mappings.py              — map_sql_type() PG/MSSQL string → CanonicalType
    db_connector.py               — get_columns(), get_foreign_keys(), get_sample_rows(), etc. Todas reciben
                                    `password: str` como parámetro explícito (nunca lo leen de una columna) —
                                    ver "Credenciales de conexión".
    profiler.py                   — fetch_db_column_stats(), compute_file_column_stats(), profile_columns() → ColumnProfile
    dialect.py                    — DialectProfiler protocol + impl PostgreSQL / SQLServer / Fake
    masker.py                     — format-preserving masking de ejemplos antes de que entren al perfil
    etl_generator.py              — construye prompt(s), llama LLM, arma ETLGenerateResponse.
                                    Flujo 2-KTR: 2 llamadas al LLM (origen→STG / STG→DWH) +
                                    build_kjb_xml() (.kjb) + stitch_lineage(); legacy: 1 llamada, 1 KTR.
    ktr_builder/                  — paquete (antes módulo único): build_ktr(ktr_data, ...) → (xml, filename, warnings),
                                    serializa un ktr JSON → XML .ktr para Pentaho PDI (se llama 1x por KTR).
                                    resolve_real_connections() arma metadata real (host/port/db/user/tipo) pero
                                    el password SIEMPRE es variable de Kettle (${ORIGEN,STAGING,DWH}_DB_PASSWORD),
                                    nunca embebido — ver "Credenciales de conexión".
    lineage_builder.py            — build_lineage()/stitch_lineage() (dict KTR) y variantes _from_xml();
                                    stitch_lineage cose origen→STG→DWH matcheando tablas STG entre KTR_1 y KTR_2
    validator.py                  — validación de estructuras
    documenter.py                 — generación de documentación ETL
    structure_inferrer.py         — inferencia de estructura
    job_analyzer.py               — análisis de jobs Pentaho (flujo CreateJob)
    superset_client/               — integración con API REST de Superset (login, get_or_create_database,
                                    import_dashboard). Conexión real al DWH se configura A MANO en Superset
                                    (Configuración → Conexiones a bases de datos) — no hay auto-provisioning
                                    con password real, mismo motivo que arriba.
    adapters/
      db_adapter.py               — list[ColumnInfo] → CanonicalSchema
      frictionless_adapter.py     — frictionless.Schema → CanonicalSchema
      ddl_adapter.py              — sqlglot AST → list[CanonicalSchema]
      schema_to_context.py        — list[CanonicalSchema] → ModelContext
  core/
    config.py                     — pydantic-settings (reads .env); LLM_PROVIDER, tokens, temps, AUTH_*
    dependencies.py               — FastAPI DI: get_main_llm(), get_secondary_llm(), get_settings()
    database.py                   — SQLAlchemy engine/session (DB propia del backend, vía DATABASE_URL)
    auth.py                       — require_auth (valida JWT contra JWKS si AUTH_REQUIRED=true) +
                                    get_current_owner(payload) → claim "sub", o None en modo dev
    sanitize.py                   — sanitización de inputs
    log_filters.py                — redacción de credenciales en logs
```

## Canonical Schema — flujo de extracción

Todos los orígenes convergen en `CanonicalSchema` antes de llegar al LLM:

```
CSV/Excel   → POST /api/schema/infer     → frictionless_adapter → CanonicalSchema
BD viva     → GET  /profile              → db_adapter           → CanonicalSchema (con perfil)
DDL paste   → POST /api/schema/from-ddl  → ddl_adapter          → CanonicalSchema[]
Formulario  → (local)                    → _schema_from_columnas_origen → CanonicalSchema
                                                    ↓
                                        canonical_to_model_context()
                                                    ↓
                                        format_model_context_for_prompt()  ← ÚNICO exit point
                                                    ↓
                                                  LLM
```

**Invariante:** `format_model_context_for_prompt()` es el único punto de salida al prompt. Solo serializa campos de `ColumnProfile` (whitelist). Nunca incluye filas de datos crudos.

**`TablaOrigen`** (en `ETLRequest.origenTables`) tiene campo `canonical_schema: Optional[CanonicalSchema]`:
- CSV/Excel/DDL: poblado por el frontend tras llamar a `/infer` o `/from-ddl`
- BD: poblado por `InputConnection` tras llamar a `/profile`
- Formulario: `None` — `context_builder` genera un `CanonicalSchema` mínimo

**`EtlContext.jsx`** valida `schema_version == "1.0"` al cargar drafts del localStorage. Formato antiguo → descarte explícito con mensaje al usuario (nunca silencioso).

## ETL Form Data Flow

`CreateETL.jsx` owns all form state. Four sections feed into a single `validateForm()` call before `addEtl()`:

```
origenTables  → InputForm.jsx                    (5 modos de entrada)
stagingDef    → StagingForm.jsx                  (transformation rules per column)
dwhModel      → DwhForm.jsx                      (dimension/fact table schema)
reglasNegocio → BussinesRulesForm.jsx            (free-text business rules)
```

`StagingForm` links to `origenTables` — its column picker populates from the selected origin table.

## API endpoints de esquema

| Endpoint | Descripción |
|---|---|
| `POST /api/schema/infer` | Sube CSV o Excel, devuelve `CanonicalSchema` con tipos + perfil estadístico |
| `POST /api/schema/from-ddl` | Parsea DDL (CREATE TABLE), devuelve `list[CanonicalSchema]` |
| `GET /api/connections/{id}/schema/tables/{t}/profile` | Esquema BD + perfil estadístico → `CanonicalSchema` |
| `GET /api/connections/{id}/schema/tables/{t}/columns` | Solo estructura → `list[CanonicalField]` |

Los 4 endpoints de `/api/connections/{id}/schema/*` y `POST /api/connections/{id}/test` exigen el header `X-DB-Password` (nunca query string — evita que quede en logs de acceso). El backend no tiene el password guardado en ningún lado; lo recibe fresco en cada llamada. Ver "Credenciales de conexión".

## Credenciales de conexión

El backend no persiste passwords de bases de datos de origen/staging/DWH — decisión de diseño, no limitación técnica. `Connection` (DB propia del backend) solo guarda host/puerto/base/usuario/tipo/ssl_mode.

- **Crear/test/explorar esquema:** el frontend mantiene el password en memoria de componente durante la sesión de armado del ETL (`ConnectionForm.jsx` → `InputConnection.jsx` → `TableCatalogConnection.jsx`), nunca en `sessionStorage`/`localStorage`. Lo reenvía en cada llamada que conecta de verdad, vía header `X-DB-Password` (test, schema explorer) o en el body (`POST /api/connections`).
- **Generación del `.ktr`:** `resolve_real_connections()` (`ktr_builder/connection.py`) arma host/port/database/username/tipo reales a partir de `Connection`, pero el password SIEMPRE queda como variable de Kettle (`${ORIGEN_DB_PASSWORD}` / `${STAGING_DB_PASSWORD}` / `${DWH_DB_PASSWORD}`), declarada en `<parameters>` con default vacío y documentada en una plantilla `kettle.properties` adjunta. Nunca se resuelve, ni se codifica de ninguna forma — el `.ktr` no tiene forma de contenerlo. El usuario lo completa a mano en Spoon/`kettle.properties` antes de ejecutar.
- **Superset:** la conexión real al DWH se configura a mano, una sola vez, en Superset → Configuración → Conexiones a bases de datos. No hay auto-provisioning con URI real (`get_or_create_database` crea/usa un placeholder si no hay una configurada).
- **`kettle_crypto.py` (ofuscación reversible del formato Kettle, removido):** existió como utilidad de fidelidad de formato para Spoon, pero el password nunca formó parte de lo que el backend recibe/persiste/escribe con contenido real — sale siempre vacío o como `${VAR}` (ver punto anterior). Sin nada propio que ofuscar, implementar el algoritmo de Kettle en el backend no tenía función; se sacó el módulo. Si en el futuro hace falta leer un `.ktr` ajeno con passwords ofuscados reales, el algoritmo (XOR contra seed fijo) queda en el historial de git.

Antes de esta decisión de diseño, las contraseñas se guardaban cifradas (Fernet, `core/crypto.py` — ya no existe) en `Connection.encrypted_password`. Si algo en el código nuevo necesita "la contraseña de una conexión guardada", es una señal de que se está reintroduciendo el patrón viejo — no hacerlo sin discutirlo primero.

## Key Shared Utilities

**`pages/CreateETL/components/Tables/tableUtils.jsx`** — reused across all ETL sections:
- `useTableEditor({ emptyTable, emptyCol, tables, setTables, columnsKey })` — manages add/edit/remove state for table+column lists
- `useTableList(items, setItems)` — simpler CRUD for flat lists
- `ColumnTable` — generic column renderer, driven by `columnDefs` prop

**`pages/CreateETL/validation/stringCleaners.js`** — naming conventions for DWH tables/columns (uppercase, `DIM_`/`FACT_` prefixes, `SK_` surrogate key prefix).

**`pages/CreateETL/validation/etlform.js`** — `validateForm({ origenTables, stagingDef, reglasNegocio, dwhModel })` returns `{ isValid, errors[] }`.

## Auth

Auth0 configured in `frontend/src/auth0/`. `PrivateRoute` wraps all ETL pages. Auth provider wraps the app in `main.jsx`.

**Backend:** `core/auth.py` — `require_auth` valida el JWT contra JWKS solo si `AUTH_REQUIRED=true` (default `false`, modo desarrollo, sin validar nada). Todos los routers (`connections`, `ai`, `schema`, `etl`, `job`) dependen de `require_auth`. `get_current_owner(payload)` devuelve el claim `sub` del token (identificador estable OIDC/Auth0), o `None` en modo desarrollo.

**Ownership:** `Connection.owner_id` y `KtrBuildJob.owner_id` (ambos `String`, no `Uuid` — un `sub` de Auth0 nunca es un UUID) filtran por dueño en `routers/connections.py` (`_get_owned_or_404` — "no existe" y "es de otro" devuelven el mismo 404, nunca 403, para no confirmar existencia a quien adivina un UUID) y en `resolve_real_connections` (rechaza `conn_id` de otro owner al armar el `.ktr`). `owner=None` (modo desarrollo) salta el filtro en ambos lados. **`etl.py` y `job.py` no tienen ownership check todavía** — solo autenticación.

**Gap conocido, no resuelto:** `frontend/src/hooks/useAuthFetch.js` agrega el header `Authorization: Bearer` cuando `VITE_AUTH_REQUIRED=true`, pero **ningún fetch del frontend lo usa todavía** (`api/connections.js` y el resto llaman `fetch()` directo). Antes de poner `AUTH_REQUIRED=true` en el backend hace falta enchufar `useAuthFetch` en todos los módulos de API — si no, cada request devuelve 401.

## Archivos de referencia y documentación

**`DESARROLLO.md`** — historial de diseño del proyecto. Contiene:
- Descripción del objetivo y stack
- Arquitectura del flujo ETL (`etl_generator` → LLM → `ktr_builder`)
- Decisiones de diseño tomadas (una sola llamada al LLM, serialización KTR en Python, conexiones BD con placeholder)
- Reglas del system prompt que surgieron de pruebas reales (R8–R11)
- Tabla de pendientes (corte 2026-05-13, desactualizada)

> Las rutas de frontend en DESARROLLO.md están desactualizadas (`src/views/` en vez de `src/pages/`). Las rutas correctas están en este archivo. El flujo de `etl_generator` y las decisiones de diseño siguen siendo válidos.

Partes a fundir si DESARROLLO.md se abandona: arquitectura del flujo ETL completo + reglas del system prompt R8–R11.

## Guía de ubicación de código nuevo

- Funcionalidad nueva no acoplada a un archivo existente → crear su propio módulo en la carpeta de la capa correspondiente (router / service / schema / model / adapter).
- Ante la duda sobre carpeta o módulo → preguntar antes de crear el archivo.
- No reorganizar ni refactorizar código existente salvo que la tarea lo pida explícitamente.

## Gestión de dependencias y entorno

**Versión de Python acordada por el equipo:** [A DEFINIR — sugerencia: 3.12]

**Entorno virtual:** cada desarrollador crea su propio `venv` local (el repo real usa `venv/`, no `.venv/`; ambos nombres están en `.gitignore`):
```bash
cd backend
python -m venv venv
venv\Scripts\activate     # Windows
# source venv/bin/activate  # Mac/Linux
```
El directorio `venv/` **nunca se commitea** — es específico del sistema operativo y del path de cada máquina.

**Dependencias — fuente de verdad: `requirements.txt`**

Flujo para agregar una dependencia:
```bash
pip install <paquete>
pip show <paquete>          # verificar versión instalada
# agregar al requirements.txt con versión exacta: paquete==X.Y.Z
```
No instalar paquetes sueltos sin actualizar `requirements.txt`. No usar rangos (`>=`) — versiones exactas (`==`) garantizan reproducibilidad.

Flujo al hacer `git pull` y `requirements.txt` cambió:
```bash
pip install -r requirements.txt   # dentro del venv activado
```
No recrear el venv entero, solo sincronizar.

**Variables de entorno:**
- `backend/.env` contiene secretos → **nunca se commitea**.
- `backend/.env.example` está en el repo → sirve de plantilla para onboarding. Al clonar el repo, copiar y completar:
```bash
cp backend/.env.example backend/.env
# editar .env con los valores reales
```
