# services/ktr_builder/validators

**Capa:** `domain/` — cada pass es una función pura (`ValidationContext -> list[Finding]`), sin I/O.
**Propósito:** passes pre-emisión sobre `ktr_data`, con un contrato uniforme (`base.py`) en vez de que cada validador invente su propia forma de retorno. Nace con H29 (docs/refactor/01-hallazgos.md) — ver D40 en `docs/refactor/02-decisiones.md` para el porqué.

## Qué entra
`ValidationContext(ktr_data, step_type_aliases, known_tables)`. `known_tables` es el set de nombres de tabla física reales del ETL en curso (staging + DWH vía DDL, o `dim_contracts` cuando no hay DDL — ver `etl_generator.py`).

## Qué sale
`list[Finding]` — `severity` (`"error"`/`"warning"`/`"info"`), `message`, `step_name`, `repaired` (True si el pass mutó `ktr_data` por ese finding).

## Archivos
| Archivo | Qué hace |
|---|---|
| `base.py` | `ValidationContext`, `Finding`, protocolo `KtrPass`. |
| `table_key_recovery.py` | H29 — recupera `table` cuando el LLM usó una clave no aliaseada, por coincidencia de contenido contra `known_tables`. |
| `__init__.py` | `PRE_EMIT_PASSES` (tupla) + `run_passes(ctx)`. |

## Dónde se llama
**Temprano, no solo dentro de `build_ktr()`.** `enforce_dimension_step_policy` y `fragmentation.build_rw_matrix` (vía `split_ktr_by_cut`) corren en `etl_generator.py` ANTES de `build_ktr()` — si un pass de este paquete solo corriera dentro de `build.py`, ese trabajo ya pasó sin ver la recuperación. `run_passes()` se invoca en `etl_generator.py` junto a `normalize_step_configs()` (mismo punto temprano del pipeline), y opcionalmente de nuevo dentro de `build.py` como red de seguridad para callers que invocan `build_ktr()` directo (tests, `build_etl_from_raw`).

## Reglas que aplican
D5/D15 — un pass puede mutar `ktr_data`, pero toda mutación va acompañada de un `Finding` con `repaired=True`. Nunca un `if not table: continue` sin reportar (R12, `docs/auditoria/00b-fallos-silenciosos.md`).

## Qué NO va acá
- Validadores que ya tienen su propio contrato consolidado en otro módulo (`fragmentation.py`, `dimension_step_policy.py`, `fields_validate.py`, `contract_validate.py`) — no se migran de arrastre; migran uno por uno, sesión aparte, cuando haga falta tocarlos igual.
- Reparación que necesita al LLM — eso es `repair.py`, capa `services/`, no `domain/`.
