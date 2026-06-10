# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Dev Commands

**Frontend** (React 19 + Vite):
```bash
cd frontend
npm run dev        # dev server → http://localhost:5173
npm run build      # production build → dist/
npm run lint       # ESLint
npm run preview    # preview production build
```

**Backend** (FastAPI):
```bash
cd backend
venv\Scripts\activate           # Windows venv
uvicorn app.main:app --reload   # → http://localhost:8000
```

Backend reads env vars from `backend/.env`. El proveedor LLM se selecciona con `LLM_PROVIDER` (default: `gemini`; usar `anthropic` para Anthropic). Gemini: `GOOGLE_API_KEY`, `GEMINI_MODEL`. Anthropic: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`. Todo configurable en `backend/app/core/config.py`.

## Architecture

React SPA with Auth0 auth talking to FastAPI backend. Backend proxies LLM (Gemini o Anthropic, switchable en runtime via `LLM_PROVIDER`) and manages schema extraction. No database — ETL state persists to `localStorage` (permanent) and `sessionStorage` (draft, 2h TTL) via `EtlContext`.

**Principio de diseño NO negociable:** al LLM solo se le envía la ESTRUCTURA de las tablas (esquema, tipos, formatos, reglas), nunca filas de datos.

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
  main.py                         — FastAPI app, mounts routers (ai, connections, schema)
  routers/
    ai.py                         — POST /api/ai/chat (ETL generation)
    connections.py                — CRUD /api/connections/* + schema explorer
    schema.py                     — POST /api/schema/infer (CSV/Excel via Frictionless)
                                    POST /api/schema/from-ddl (DDL via sqlglot)
  models/
    llm_base.py                   — BaseLLM ABC + LLMResponse dataclass (interfaz común)
    gemini_llm.py                 — GeminiLLM: retries 4× con backoff exponencial en 429/503
    anthropic_llm.py              — AnthropicLLM: ídem para Anthropic
    llm_factory.py                — build_llm(settings, role) → BaseLLM; sin singletons
    connection.py                 — Connection ORM model, DbType enum (postgresql | sqlserver)
  schemas/
    canonical.py                  — CanonicalSchema, CanonicalField, CanonicalType (central)
    etl_schemas.py                — ETLRequest, TablaOrigen (con canonical_schema), ColumnaOrigen
    connection.py                 — ColumnInfo (DTO interno), ConnectionRead, etc.
    context_schemas.py            — ColumnProfile, ColumnStats, ModelContext (prompt layer)
    job_schemas.py                — schemas del flujo CreateJob
  services/
    context_builder.py            — build_model_context() → 4 paths → ModelContext → prompt
    file_schema.py                — infer_file_schema() via Frictionless (CSV/Excel)
    type_mappings.py              — map_sql_type() PG/MSSQL string → CanonicalType
    db_connector.py               — get_columns(), get_foreign_keys(), get_sample_rows()
    profiler.py                   — fetch_db_column_stats(), compute_file_column_stats(), profile_columns() → ColumnProfile
    dialect.py                    — DialectProfiler protocol + impl PostgreSQL / SQLServer / Fake
    masker.py                     — format-preserving masking de ejemplos antes de que entren al perfil
    etl_generator.py              — construye prompt, llama LLM, parsea JSON → ETLGenerateResponse
    ktr_builder.py                — serializa ktr JSON → XML .ktr para Pentaho PDI
    validator.py                  — validación de estructuras
    documenter.py                 — generación de documentación ETL
    structure_inferrer.py         — inferencia de estructura
    job_analyzer.py               — análisis de jobs Pentaho (flujo CreateJob)
    adapters/
      db_adapter.py               — list[ColumnInfo] → CanonicalSchema
      frictionless_adapter.py     — frictionless.Schema → CanonicalSchema
      ddl_adapter.py              — sqlglot AST → list[CanonicalSchema]
      schema_to_context.py        — list[CanonicalSchema] → ModelContext
  core/
    config.py                     — pydantic-settings (reads .env); LLM_PROVIDER, tokens, temps
    dependencies.py               — FastAPI DI: get_main_llm(), get_secondary_llm(), get_settings()
    database.py                   — SQLAlchemy engine/session para conexiones almacenadas
    crypto.py                     — cifrado de credenciales de conexión
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

## Key Shared Utilities

**`pages/CreateETL/components/Tables/tableUtils.jsx`** — reused across all ETL sections:
- `useTableEditor({ emptyTable, emptyCol, tables, setTables, columnsKey })` — manages add/edit/remove state for table+column lists
- `useTableList(items, setItems)` — simpler CRUD for flat lists
- `ColumnTable` — generic column renderer, driven by `columnDefs` prop

**`pages/CreateETL/validation/stringCleaners.js`** — naming conventions for DWH tables/columns (uppercase, `DIM_`/`FACT_` prefixes, `SK_` surrogate key prefix).

**`pages/CreateETL/validation/etlform.js`** — `validateForm({ origenTables, stagingDef, reglasNegocio, dwhModel })` returns `{ isValid, errors[] }`.

## Auth

Auth0 configured in `frontend/src/auth0/`. `PrivateRoute` wraps all ETL pages. Auth provider wraps the app in `main.jsx`.

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

**Entorno virtual:** cada desarrollador crea su propio `venv` local:
```bash
cd backend
python -m venv venv
venv\Scripts\activate   # Windows
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
