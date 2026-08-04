# tests/api — HTTP end-to-end

Ejercitan los routers vía HTTP real (o `TestClient`), no las funciones de
servicio directo. Es la capa más cercana a "lo que le pasa a un usuario".

⚠️ **`test_api.py` tiene costo real.** Requiere `uvicorn app.main:app --reload`
corriendo en `localhost:8000` con `.env` apuntando a un proveedor LLM real
(`GOOGLE_API_KEY` o `ANTHROPIC_API_KEY`) — cada test que pega a
`/api/ai/etl` dispara una llamada real al modelo. **Excluido por default**
del comando "gratis" del README raíz (`--ignore=tests/api`). Correrlo a
propósito:

```bash
uvicorn app.main:app --reload      # en otra terminal
pytest tests/api/test_api.py -v
```

Los demás archivos de esta carpeta **no** tienen costo — usan SQLite en
memoria + `TestClient` + LLM mockeado, no llaman a ningún servidor externo.

| Archivo | Tipo | Valida |
|---|---|---|
| `test_api.py` | live-server, **costo real** | Superficie completa `/api/ai/etl`, `/api/v1/etl/*` — generate/validate/document/infer/refine y ~25 paths de error/validación, end-to-end contra el LLM real. |
| `test_connections_api.py` | integración (SQLite en memoria) | El password nunca se persiste ni se devuelve como columna; aislamiento estricto por owner (404 en cualquier verbo sobre recurso ajeno, `list` nunca filtra filas de otro owner); comportamiento del override de auth en modo dev. |
| `test_etl_job_crud.py` | integración (SQLite en memoria) | CRUD de Etl/Job devuelve claves camelCase, ciclo de vida completo ETL/job, borrar un ETL sincronizado/pendiente no resucita ni escribe al outbox de Supabase. |
| `test_ktr_build_job_api.py` | integración (SQLite en memoria + LLM mockeado) | Barrera de carrera modelo/conexiones dispara el build sin importar orden de llegada; fallo del modelo bloquea el build; conn_id desconocido/ajeno degrada a warning (no failure); aislamiento por owner; expiración TTL (410)/id malformado (404); un caso end-to-end real (corpus real) del flujo async. |
| `test_fase1_canonical.py` | integración (mocks + SQLite/TestClient) | El endpoint `/profile` devuelve `CanonicalSchema`; `_profile_from_db()` la arma vía `db_adapter` usando solo mocks. |

Correr solo la parte gratis de esta carpeta:

```bash
pytest tests/api/ --ignore=tests/api/test_api.py -v
```
