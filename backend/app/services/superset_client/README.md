# services/superset_client

**Capa:** `infrastructure/superset/`
**Propósito:** cliente HTTP (httpx) contra la API REST de Superset — login, creación de datasets/charts/dashboard, import del ZIP armado por `superset_export/`.

## Qué entra
Credenciales de Superset (config, no las de la BD del usuario) + el ZIP producido por `services/superset_export/`.

## Qué sale
Dashboard/datasets creados en la instancia de Superset configurada. La conexión real al DWH se configura a mano en Superset (ver "Credenciales de conexión" en `CLAUDE.md`) — este cliente no la provisiona con password real.

## Archivos
| Archivo | Qué hace |
|---|---|
| `client.py` (124) | Login + wrapper HTTP base. |
| `dashboard.py` (290) | Creación/actualización de dashboard. |
| `charts.py` (190) | Creación de charts. |
| `dwh_tables.py` (178) | Resolución de tablas del DWH del lado de Superset. |
| `database.py` (132) | `get_or_create_database` — placeholder si no hay conexión real configurada. |
| `zip_tools.py` (212) | Utilidades de manejo de ZIP para el import. |
| `datasets.py` (113) | Creación de datasets. `create_datasets_from_zip` traga cualquier excepción al chequear existencia previa sin loguear — fallo silencioso conocido, `docs/auditoria/00b-fallos-silenciosos.md` sección 2.1. |
| `constants.py`, `errors.py` | Constantes y tipos de error propios. |

## Reglas que aplican
R1, R6 — es infraestructura pura; nada de acá debería ser importado por `domain/` ni `services/` salvo a través de `superset_export`/el router que expone `/superset/export`.

## Qué NO va acá
- Armado del ZIP en sí (asset YAML, selección de charts) — eso es `services/superset_export/`, un directorio al lado.
- Provisioning de la conexión real al DWH con password — decisión de diseño explícita en contra, ver `CLAUDE.md` sección "Credenciales de conexión".
