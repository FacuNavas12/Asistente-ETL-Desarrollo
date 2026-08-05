# tests/ktr_builder/connections — resolución de conexiones

Sin costo real (LLM/API) — SQLite en memoria + un golden-file estático.

| Archivo | Valida |
|---|---|
| `test_ktr_connection_golden.py` | Golden-file: `tests/fixtures/connections_sample.ktr` (export real de Spoon 9.x) documenta los campos XML exactos (Postgres + SQLServer) que `_build_connection()` debe reproducir para que el `.ktr` abra en Spoon sin retocar. |
| `test_ktr_connection_resolution.py` | `resolve_real_connections()` respeta aislamiento por owner, mapea `DbType` → engine Kettle correcto, y el password **nunca** se embebe en el `.ktr` — siempre queda como variable placeholder de Kettle. |

```bash
pytest tests/ktr_builder/connections/ -v
```
