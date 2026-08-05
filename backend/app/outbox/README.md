# outbox

**Capa:** `infrastructure/outbox/`
**Propósito:** patrón outbox — persistir cambios de `Etl`/`Job` localmente primero (SQLite), después drenarlos hacia Supabase en background, para que un fallo de red no pierda una escritura del usuario.

## Qué entra
Operaciones de escritura sobre `Etl`/`Job` desde `services/etl_service.py` (con outbox) — `job_service.py` no lo usa, va directo contra el repo (ver su propio README para esa asimetría).

## Qué sale
`EtlRead.sync_status` (`pending`/`synced`/`failed`) expuesto en la API — el único caso del repo donde un fallo de fondo SÍ llega al usuario en vez de quedar solo en logs (contraejemplo C3 en `docs/auditoria/00b-fallos-silenciosos.md` sección 4).

## Archivos
| Archivo | Qué hace |
|---|---|
| `sqlite_outbox.py` (134) | Persistencia local del outbox (SQLite). |
| `drainer.py` (119) | Drena hacia Supabase — distingue fallo transitorio (reintenta) de permanente (`mark_failed`). |
| `runner.py` (85) | Loop de drenaje in-process, lanzado desde `main.py` `lifespan`. |
| `port.py` (34) | Interfaz que separa el outbox de su backend concreto. |

## Reglas que aplican
R11 — es el ejemplo correcto de "emisión" (ver R11 en `docs/arquitectura-objetivo.md`): un fallo de sync no corta el flujo, pero el estado SÍ es visible para el usuario, no solo en logs de servidor.

## Qué NO va acá
- Lógica de negocio sobre cuándo un ETL "está listo" — eso es `services/etl_service.py`, el outbox solo garantiza que la escritura no se pierda.
- Un segundo outbox para `Job` "porque `Etl` ya lo tiene" — la asimetría es una decisión existente, no un olvido a copiar sin revisar por qué (ver `docs/auditoria/00-inventario.md` sección 2, fila `job.py`).
