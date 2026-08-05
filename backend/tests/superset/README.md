# tests/superset — export a Superset

Sin costo real (LLM/API) — unitario, `SimpleNamespace` como stand-in del
modelo ORM, sin DB.

| Archivo | Valida |
|---|---|
| `test_superset_export.py` | `deterministic_uuid` matchea el hash de referencia en JS bit a bit; `build()`/`build_tables()` obtienen el schema correctamente desde `dwh_sample`, DDL parseado, o `dwhModel` legacy (y lanzan error si ninguno está disponible); la selección de charts elige métrica+fecha para fact tables. |

```bash
pytest tests/superset/ -v
```
