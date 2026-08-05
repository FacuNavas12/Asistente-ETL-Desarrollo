# services/ktr_builder/validators

**Capa:** `domain/` — cada pass es una función pura (`ValidationContext -> list[Finding]`), sin I/O.
**Propósito:** passes pre-emisión sobre `ktr_data`, con un contrato uniforme (`base.py`) en vez de que cada validador invente su propia forma de retorno. Nace con H29 (`docs/decisiones/hallazgos.md`) — ver D40 en `docs/decisiones/decisiones.md` para el porqué.

## Qué entra
`ValidationContext(ktr_data, step_type_aliases, known_tables)`. `known_tables` es el set de nombres de tabla física reales del ETL en curso (staging + DWH vía DDL, o `dim_contracts` cuando no hay DDL — ver `etl_generator.py`).

## Qué sale
`list[Finding]` — `severity` (`"error"`/`"warning"`/`"info"`), `message`, `step_name`, `repaired` (True si el pass mutó `ktr_data` por ese finding). Si un pass quiere que su mensaje sea reconocible en `warnings` (p. ej. para que el caller lo etiquete distinto), el prefijo va DENTRO de `message` — nunca lo agrega el caller de `run_passes()`: con más de un pass en `PRE_EMIT_PASSES`, un prefijo agregado por fuera etiquetaría mal los findings de cualquier otro pass (D41 corrigió esto — `TABLE_KEY_PREFIX` se lo agregaba `etl_generator.py`/`build.py` a TODOS los findings, no solo a los de `recover_table_key`).

## Archivos
| Archivo | Qué hace |
|---|---|
| `base.py` | `ValidationContext`, `Finding`, protocolo `KtrPass`. |
| `table_key_recovery.py` | H29 — recupera `table` cuando el LLM usó una clave no aliaseada, por coincidencia de contenido contra `known_tables`. |
| `dead_computed_fields.py` | H40 — avisa (no repara) cuando un `Calculator` agrega un campo que ningún step aguas abajo consume ni mapea a tabla destino. Solo warning, nunca mutación. |
| `__init__.py` | `PRE_EMIT_PASSES` (tupla completa) + `run_passes(ctx, passes=...)`. |

## Dónde se llama
**Temprano, no solo dentro de `build_ktr()`.** La decisión de dónde vive Python vs. el modelo (`docs/decisiones/decision-python-vs-llm.md`) partió `PRE_EMIT_PASSES` en dos sub-tuplas, porque `apply_dimension_contracts` tiene que quedar SANDWICHEADA entre ellas:

1. **`TABLE_RECOVERY_PASSES`** (`recover_table_key`, solo) — corre en `etl_generator._recover_table_keys()`, ANTES de `apply_dimension_contracts` y de `fragmentation.build_rw_matrix` (vía `split_ktr_by_cut`): ambos necesitan ver `table` ya recuperado.
2. `apply_dimension_contracts` sintetiza el config de cada step de dimensión desde el contrato.
3. **`VERIFY_PASSES`** (el resto — `check_dimension_lookup_fields`, `check_narration_crosscheck`, etc.) — corre en `etl_generator._verify_emitted_ktr()`, DESPUÉS. Antes de O3 estos passes corrían junto con `recover_table_key`, inspeccionando el config que el MODELO había escrito — un finding sobre un valor a punto de ser pisado por la síntesis es una señal falsa, no ruido inocuo.

`PRE_EMIT_PASSES` se preserva como la concatenación de ambas — `build.py` sigue corriendo la tupla completa como red de seguridad para callers que invocan `build_ktr()` directo sin pasar por `apply_dimension_contracts` (tests, `build_etl_from_raw` con `dim_contracts` vacío).

## Reglas que aplican
D5/D15 — un pass puede mutar `ktr_data`, pero toda mutación va acompañada de un `Finding` con `repaired=True`. Nunca un `if not table: continue` sin reportar (R12).

## Qué NO va acá
- Validadores que ya tienen su propio contrato consolidado en otro módulo (`fragmentation.py`, `dimension_step_policy.py`, `fields_validate.py`, `contract_validate.py`) — no se migran de arrastre; migran uno por uno, sesión aparte, cuando haga falta tocarlos igual.
- Reparación que necesita al LLM — eso es `repair.py`, capa `services/`, no `domain/`.
