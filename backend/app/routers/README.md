# routers

**Capa:** `api`
**Propósito:** traducir HTTP a llamadas de service y de vuelta, nada más.

## Qué entra
Requests HTTP con body/query validados por `schemas/`. Todos los endpoints (menos health-check, si lo hubiera) dependen de `core.auth.require_auth`.

## Qué sale
Responses tipadas con schemas de `schemas/`. El frontend React (`src/api/*.js`) es el único consumidor.

## Archivos
| Archivo | Qué hace |
|---|---|
| `ai.py` | Flujo IA: validar/documentar/inferir/generar ETL (sync, async, SSE), reconstrucción desde raw, linaje, generación de Jobs `.kjb`. |
| `connections.py` | CRUD de `Connection` + test de conexión real + explorador de esquema. |
| `etl.py` | CRUD de `Etl` persistido (vía outbox) + reconexión de destino sin volver a llamar al LLM. |
| `job.py` | CRUD simple de `Job` persistido. |
| `schema.py` | Inferencia de esquema desde archivo (CSV/Excel) y desde DDL pegado. |

Tabla completa de endpoints con `archivo:línea` y la cadena de llamadas de cada uno: `docs/auditoria/00-inventario.md` sección 2.

## Reglas que aplican
R2 — el router no toca DB, LLM ni disco, solo llama a un service.
R4 — no se saltean capas.

**Deuda conocida, no arreglada en esta sesión:** `ai.py` y `connections.py` importan modelos ORM (`app.models.*`) directo y hacen `db.add`/`db.commit` en el propio router — violación de R2/R4 ya existente, congelada en `backend/tests/test_architecture_layers.py` (`FROZEN_R4`). Ver `docs/auditoria/00-inventario.md` sección 2 para cada endpoint puntual.

## Qué NO va acá
- Un `db.query(...)` o `session.add(...)` directo — eso es un service o un repositorio. (Ya pasa hoy en `ai.py`/`connections.py`: es deuda, no el patrón a copiar.)
- Un `try/except` que decide un default de negocio (ej. "si el LLM falla, devolver `[]`") — eso vive en el service que expone el router.
- Parseo de XML/DDL/CSV — eso entra por `infrastructure` (hoy: `services/adapters`, `services/file_schema.py`), nunca en el router.
