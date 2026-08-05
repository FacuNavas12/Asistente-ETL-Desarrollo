# tests/schema_adapters — `CanonicalSchema`, adapters, dialect, profiler

Sin costo real (LLM/API) — unitarios con mocks, o `TestClient` + archivos
CSV temporales reales (sin red, sin DB real).

| Archivo | Valida |
|---|---|
| `test_canonical_schema.py` | Los paths DB/DDL/CSV convergen al mismo `CanonicalSchema` en los campos que todo origen puede conocer, dejando precision/scale/length en `None` donde CSV genuinamente no puede saberlos. |
| `test_ddl_adapter.py` | El parseo de DDL extrae columnas/PK/constraints nombrados/CHECK correctamente y `POST /api/schema/from-ddl` devuelve el `CanonicalSchema` correspondiente. |
| `test_ddl_adapter_defaults.py` | `parse_ddl` clasifica el DEFAULT de cada columna como "function" vs "literal" vs `None`, sin depender del nombre de tabla/columna. |
| `test_sql_defaults.py` | `classify_default_expr`/`looks_like_sql_function` distinguen DEFAULTs que son llamada a función SQL (`NOW()`, `gen_random_uuid()`, `nextval`) de DEFAULTs literales. |
| `test_file_schema.py` | La inferencia de schema vía Frictionless convierte a `CanonicalSchema` correctamente, round-trip contra CSVs temporales reales. |
| `test_db_connector.py` | `_build_url` arma el DSN correcto por `DbType` (incl. SSL/trust-cert); `_sanitize_error` scrubea información sensible; `qualify`/`list_tables` manejan multi-schema. |
| `test_dialect.py` | `get_dialect` devuelve la implementación Postgres/SQLServer/Fake correcta; el SQL de stats generado tiene las cláusulas correctas por dialecto (variantes de char-length, COUNT/NULL/DISTINCT), sesgo de sampling (page vs row level) y quoting de identificadores correctos por dialecto. |
| `test_profiler.py` | null%/distinct counts vienen de stats calculadas en DB, no de samples locales; ningún valor tipo PII (email/teléfono) se filtra al output del perfil; heurísticas de casing/spacing/date/enum y redacción de ejemplos enmascarados. |
| `test_connection_schemas.py` | Los schemas Pydantic de create/update/read de conexión Postgres/SqlServer aceptan/rechazan correctamente campos requeridos, valores de `ssl_mode`, y forma de `ColumnInfo`. |

```bash
pytest tests/schema_adapters/ -v
```
