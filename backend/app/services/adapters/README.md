# services/adapters

**Capa:** `infrastructure/schema_sources/`
**Propósito:** convertir cada una de las 3 fuentes externas de esquema (BD real, archivo subido, DDL pegado) a la misma forma canónica, en un único punto por fuente.

## Qué entra
- `db_adapter.py`: `list[ColumnInfo]` desde `services/db_connector.py` (BD real).
- `frictionless_adapter.py`: `frictionless.Schema` desde `services/file_schema.py` (CSV/Excel).
- `ddl_adapter.py`: texto DDL crudo, parseado con `sqlglot`.
- `schema_to_context.py`: no es fuente — convierte lo que producen los otros tres a `ModelContext`.

## Qué sale
`CanonicalSchema` (`schemas/canonical.py`) en los tres primeros. `ModelContext` (`schemas/context_schemas.py`) en `schema_to_context.py`.

## Archivos
| Archivo | Qué hace |
|---|---|
| `ddl_adapter.py` (294) | `parse_ddl()` — AST sqlglot → `list[CanonicalSchema]`. Tablas/FKs que no parsean se loguean y se descartan (nunca excepción — ver `docs/referencia/contrato-ddl.md`). |
| `frictionless_adapter.py` (100) | `frictionless.Schema` → `CanonicalSchema`. |
| `schema_to_context.py` (86) | `canonical_to_model_context()` — el único puente `CanonicalSchema` → `ModelContext`. |
| `db_adapter.py` (79) | `list[ColumnInfo]` → `CanonicalSchema`, usado también para armar los badges PK/FK que ve `InputConnection.jsx`. |

## Reglas que aplican
R5 — cada adapter es, literalmente, el borde de entrada de su fuente: acá y solo acá se parsea/valida esa fuente antes de que el dato entre como `CanonicalSchema` tipado.
R6 — las tres implementaciones convergen en una sola forma canónica; si un adapter nuevo produce su propio shape en vez de `CanonicalSchema`, es violación.

## Qué NO va acá
- Perfilado estadístico de columnas (agregados, muestras) — eso es `services/profiler.py`, un directorio arriba.
- Lectura del archivo subido desde disco — eso pasa en el router (`routers/schema.py`) antes de llegar acá.
- Una cuarta fuente que no termine en `CanonicalSchema` — si no converge, no es un adapter de este paquete.
