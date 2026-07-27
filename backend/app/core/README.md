# core

**Capa:** `core`
**Propósito:** lo transversal que ninguna otra capa debería tener que reimplementar — config, auth, sesión de DB, logging, sanitización.

## Qué entra
Variables de entorno (`.env`), el JWT de cada request (si `AUTH_REQUIRED=true`), y llamadas de `Depends()` desde cualquier router.

## Qué sale
`Settings` tipado, una `Session` de SQLAlchemy por request, el claim `sub` del owner autenticado (o `None` en modo desarrollo).

## Archivos
| Archivo | Qué hace |
|---|---|
| `config.py` (103) | `Settings(BaseSettings)` — lee `.env`, incluye `LLM_PROVIDER`, tokens, temperaturas, `AUTH_*`. |
| `auth.py` (153) | `require_auth` (valida JWT contra JWKS solo si `AUTH_REQUIRED=true`) + `get_current_owner(payload)`. |
| `database.py` (64) | Engine/sessionmaker de SQLAlchemy, `get_db()`/`get_session_factory()` para `Depends()`. |
| `dependencies.py` (33) | DI de LLM: `get_main_llm()`, `get_secondary_llm()`. |
| `log_filters.py` (31) | Redacción de credenciales en logs. |
| `sanitize.py` (18) | Sanitización de mensajes de error antes de devolverlos al cliente. |

## Reglas que aplican
Es la única capa que no tiene "puede importar"/"nunca" en la tabla de Capas (`docs/arquitectura-objetivo.md`) — cualquier otra capa puede depender de `core`, `core` no depende de ninguna.
R3 — cuando se implemente, el exception handler que traduce excepciones de dominio a HTTP vive acá, no en cada router.

## Qué NO va acá
- Una regla de negocio (ej. "si `AUTH_REQUIRED=false`, saltear ownership") más allá de la infraestructura de auth misma — eso ya está bien acotado hoy, cuidado si crece.
- Un cliente HTTP a un servicio externo del dominio (LLM, Superset, BD del usuario) — eso es `infrastructure/`, `core` es transversal técnico, no un servicio más.
- Cifrado/ofuscación reversible de credenciales de conexión — decisión de diseño explícita en contra, ver `CLAUDE.md` sección "Credenciales de conexión" (`kettle_crypto.py`/`core/crypto.py` se sacaron por esto).
