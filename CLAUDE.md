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

Backend reads env vars from `backend/.env`. Currently uses Google Gemini (`GOOGLE_API_KEY`, `GOOGLE_MODEL_MAIN/SECONDARY`). Claude/Anthropic integration planned (`ANTHROPIC_API_KEY`, model configurable in `backend/app/core/config.py`).

## Architecture

React SPA with Auth0 auth talking to FastAPI backend. Backend proxies LLM (Gemini / Anthropic) and manages schema extraction. No database — ETL state persists to `localStorage` (permanent) and `sessionStorage` (draft, 2h TTL) via `EtlContext`.

**Principio de diseño NO negociable:** al LLM solo se le envía la ESTRUCTURA de las tablas (esquema, tipos, formatos, reglas), nunca filas de datos.

**Frontend structure:**
```
src/
  routes/AppRouter.jsx          — PrivateRoute wraps auth-gated pages
  context/EtlContext.jsx        — ETL CRUD + draft persistence + schema_version validation
  context/ThemeContext.jsx      — dark/light toggle
  api/connections.js            — clientes HTTP para /api/connections/*
  api/schema.js                 — inferSchema(), parseDDL(), canonicalSchemaToTablaOrigen()
  pages/CreateETL/              — main ETL form wizard
    components/Input/
      InputForm.jsx             — selector de modo (formulario/CSV/Excel/Conexiones/DDL)
      InputCSV.jsx              — sube archivo → POST /api/schema/infer → CanonicalSchema
      InputExcel.jsx            — ídem para .xlsx/.xls
      InputConnection.jsx       — conexión BD → GET /profile → CanonicalSchema + PK/FK badges
      InputDDL.jsx              — textarea DDL → POST /api/schema/from-ddl → CanonicalSchema[]
      InputFormulario.jsx       — entrada manual de columnas
  pages/EtlDetail/              — result display + chart
  validation/                   — form validation + string utilities
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
  schemas/
    canonical.py                  — CanonicalSchema, CanonicalField, CanonicalType (central)
    etl_schemas.py                — ETLRequest, TablaOrigen (con canonical_schema), ColumnaOrigen
    connection.py                 — ColumnInfo (DTO interno), ConnectionRead, etc.
    context_schemas.py            — ColumnProfile, ModelContext (prompt layer)
  services/
    context_builder.py            — build_model_context() → 4 paths → ModelContext → prompt
    file_schema.py                — infer_file_schema() via Frictionless (CSV/Excel)
    type_mappings.py              — map_sql_type() PG/MSSQL string → CanonicalType
    db_connector.py               — get_columns(), get_foreign_keys(), get_sample_rows()
    profiler.py                   — fetch_column_stats(), profile_columns() → ColumnProfile
    adapters/
      db_adapter.py               — list[ColumnInfo] → CanonicalSchema
      frictionless_adapter.py     — frictionless.Schema → CanonicalSchema
      ddl_adapter.py              — sqlglot AST → list[CanonicalSchema]
      schema_to_context.py        — list[CanonicalSchema] → ModelContext
  core/config.py                  — pydantic-settings (reads .env)
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
origenTables  → OrigenInput.jsx / InputForm.jsx  (5 modos de entrada)
stagingDef    → StagingForm.jsx                  (transformation rules per column)
dwhModel      → DwhModel.jsx                     (dimension/fact table schema)
reglasNegocio → ReglasNegocio.jsx                (free-text business rules)
```

`StagingForm` links to `origenTables` — its column picker populates from the selected origin table.

## API endpoints de esquema (nuevos)

| Endpoint | Descripción |
|---|---|
| `POST /api/schema/infer` | Sube CSV o Excel, devuelve `CanonicalSchema` con tipos + perfil estadístico |
| `POST /api/schema/from-ddl` | Parsea DDL (CREATE TABLE), devuelve `list[CanonicalSchema]` |
| `GET /api/connections/{id}/schema/tables/{t}/profile` | Esquema BD + perfil estadístico → `CanonicalSchema` |
| `GET /api/connections/{id}/schema/tables/{t}/columns` | Solo estructura → `list[CanonicalField]` |

## Key Shared Utilities

**`components/etl/tableUtils.jsx`** — reused across all ETL sections:
- `useTableEditor({ emptyTable, emptyCol, tables, setTables, columnsKey })` — manages add/edit/remove state for table+column lists
- `useTableList(items, setItems)` — simpler CRUD for flat lists
- `ColumnTable` — generic column renderer, driven by `columnDefs` prop

**`validation/stringCleanersDWH.js`** — naming conventions for DWH tables/columns (uppercase, `DIM_`/`FACT_` prefixes, `SK_` surrogate key prefix).

**`validation/etlform.js`** — `validateForm({ origenTables, stagingDef, reglasNegocio, dwhModel })` returns `{ isValid, errors[] }`.

## Auth

Auth0 configured in `frontend/src/auth0/`. `PrivateRoute` wraps all ETL pages. Auth provider wraps the app in `main.jsx`.

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