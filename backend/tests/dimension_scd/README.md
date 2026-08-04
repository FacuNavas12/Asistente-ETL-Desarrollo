# tests/dimension_scd — `domain/scd.py` + `dimension_step_policy`

Sin costo real (LLM/API) — todos unitarios, sin LLM involucrado (la política
de SCD es determinística por diseño, ver `apply_dimension_contracts`).

| Archivo | Valida |
|---|---|
| `test_dimension_step_policy.py` | `apply_dimension_contracts` reconstruye determinísticamente la config de DimensionLookup (update Y/N, readonly, field mapping) a partir de los contratos `scd_type`, sin importar qué emitió el LLM; casos borde de lookup huérfano y CombinationLookup. |
| `test_scd_policy.py` | Clasificación determinística SCD1 vs SCD2 — sin key/sin atributo mutable fuerza SCD1, dimensiones calendario fuerzan SCD0, interacción entre intención declarada y imposibilidad mecánica, matching de texto de `detect_history_intent`. |
| `test_scd_consequence_and_monetary_guard.py` | Emite un finding no-error nombrando la consecuencia concreta del `scd_type` elegido por dimensión; marca como error un atributo monetario/de monto versionado dentro de una dimensión SCD2. |
| `test_scd_zero_calendar_guard.py` | `scd_type=0` solo es seguro para una dimensión calendario genuina (`is_calendar_dimension`); cualquier otro caso de `scd_type=0` se reporta como error sin abortar; no-op best-effort si falta DDL o es inválido. |
| `test_inferred_member.py` | Dimensiones referenciadas por una FK NOT NULL desde una fact table se identifican como necesitadas del patrón anti-join+Union (inferred member) y se formatean correctamente para el prompt del LLM. |

```bash
pytest tests/dimension_scd/ -v
```
