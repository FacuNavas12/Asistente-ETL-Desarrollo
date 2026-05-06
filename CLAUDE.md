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

Backend deps not in `requirements.txt` — installed manually in `backend/venv/`. Core deps: `fastapi uvicorn anthropic pydantic pydantic-settings python-dotenv`.

Backend reads `ANTHROPIC_API_KEY` from `backend/.env`. Default model: `claude-haiku-4-5-20251001` (configurable in `backend/app/core/config.py`).

## Architecture

React SPA with Auth0 auth talking to FastAPI backend. Backend proxies Claude AI via Anthropic SDK. No database — ETL state persists to `localStorage` (permanent) and `sessionStorage` (draft, 2h TTL) via `EtlContext`.

**Frontend structure:**
```
src/
  routes/AppRouter.jsx      — PrivateRoute wraps auth-gated pages
  context/EtlContext.jsx    — ETL CRUD + draft persistence
  context/ThemeContext.jsx  — dark/light toggle
  views/CreateETL.jsx       — main ETL form wizard
  views/EtlDetail.jsx       — result display + chart
  components/etl/           — form section components
  validation/               — form validation + string utilities
```

**Backend structure:**
```
app/
  main.py                   — FastAPI app, mounts routers
  routers/ai.py             — POST /api/ai/chat
  services/claude_service.py — ask_claude() wrapper
  core/config.py            — pydantic-settings (reads .env)
```

## ETL Form Data Flow

`CreateETL.jsx` owns all form state. Four sections feed into a single `validateForm()` call before `addEtl()`:

```
origenTables  → OrigenInput.jsx     (source tables + columns + sample data)
stagingDef    → StagingForm.jsx     (transformation rules per column)
dwhModel      → DwhModel.jsx        (dimension/fact table schema)
reglasNegocio → ReglasNegocio.jsx   (free-text business rules)
```

`StagingForm` links to `origenTables` — its column picker populates from the selected origin table. Schema: `{ tableName, origenVinculado, columns: [{nombre, tipo, regla, datoNoValido}] }`.

## Key Shared Utilities

**`components/etl/tableUtils.jsx`** — reused across all ETL sections:
- `useTableEditor({ emptyTable, emptyCol, tables, setTables, columnsKey })` — manages add/edit/remove state for table+column lists
- `useTableList(items, setItems)` — simpler CRUD for flat lists
- `ColumnTable` — generic column renderer, driven by `columnDefs` prop

**`validation/stringCleanersDWH.js`** — naming conventions for DWH tables/columns (uppercase, `DIM_`/`FACT_` prefixes, `SK_` surrogate key prefix).

**`validation/etlform.js`** — `validateForm({ origenTables, stagingDef, reglasNegocio, dwhModel })` returns `{ isValid, errors[] }`.

## Auth

Auth0 configured in `frontend/src/auth0/`. `PrivateRoute` wraps all ETL pages. Auth provider wraps the app in `main.jsx`.