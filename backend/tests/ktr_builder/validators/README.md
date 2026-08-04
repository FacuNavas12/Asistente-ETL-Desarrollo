# tests/ktr_builder/validators — passes de validación pre-emisión

Sin costo real (LLM/API) — unitarios + un golden-file estático.

| Archivo | Valida |
|---|---|
| `test_check_constraint_filter.py` | Exige un FilterRows que matchee cada columna con CHECK-range del DWH que un writer popula; marca mismatches de `value_type` contra el tipo de columna. |
| `test_dead_computed_fields.py` | Marca (warning, sin mutar) un campo agregado por Calculator que ningún step downstream consume/mapea a output; hops deshabilitados no cuentan como alcanzables. |
| `test_dimension_lookup_fields.py` | Detecta configs de DimensionLookup sin `date_from`/`date_to` o con `fields[].type` malformado/no reconocido que caería en default silencioso de Kettle. |
| `test_guard_staging_layer.py` | Detecta un FilterRows que, vía hops habilitados, alimenta a un writer de tabla staging (backstop de fuga de regla de negocio). |
| `test_insert_update_bypass.py` | Marca `update_bypassed=N` explícito combinado con cero campos `<value>` actualizables (UPDATE vacío, Kettle falla en la primera fila). |
| `test_table_key_recovery.py` | Recupera la clave `table` de un step cuando el LLM usó un alias no reconocido, por coincidencia de contenido contra tablas candidatas; idempotente; reporta error (nunca adivina) si hay ambigüedad/ningún candidato; no toca steps sin clave `table`. |
| `test_error_catalog_checks.py` | Golden fixture (`tests/fixtures/golden_run_base_01`) da cero findings; el check v11 (monetario) marca campos NUMBER con hint de dinero extendido, acepta BigNumber, ignora campos no monetarios. |

```bash
pytest tests/ktr_builder/validators/ -v
```
