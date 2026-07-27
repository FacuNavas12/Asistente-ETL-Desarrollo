# services/ktr_builder/steps

**Capa:** `infrastructure/pentaho/`
**Propósito:** un builder por familia de step Kettle — recibe config ya validada y arma el `<step>` XML exacto que Spoon espera para ese tipo de plugin.

## Qué entra
`canonical_type` (string ya resuelto vía `registry.STEP_TYPE_ALIASES`) + `cfg: dict` ya normalizado por `contracts.normalize_config`. Nunca recibe el `config` crudo del LLM.

## Qué sale
Un `xml.etree.ElementTree.Element` `<step>` completo, listo para `tostring()` en `build.py`.

## Archivos
| Archivo | Qué hace |
|---|---|
| `input.py` | Builders de entrada: `TableInput`, `CsvInput`, `ExcelInput`, `JsonInput`, `RowGenerator`, `TextFileInput`. |
| `output.py` | Builders de salida: `TableOutput`, `InsertUpdate`, `Update`, `Delete`, `ExcelOutput`, `JsonOutput`, `TextFileOutput`. |
| `lookups.py` | Joins/lookups: `DimensionLookup`, `CombinationLookup`, `DBLookup`, `StreamLookup`, `MergeJoin`, `MergeRows`, `JoinRows`. |
| `transform.py` | Transformaciones de fila: `Calculator`, `Formula`, `SelectValues`, `GroupBy`, `SortRows`, `Unique`, etc. (el más grande, 417 líneas). |
| `control.py` | Control de flujo: `Dummy`, `Abort`, `ExecSQL`, `SetVariable`, `GetVariable`, `WriteToLog`, `ScriptValueMod`, `DataValidator`, `BlockingStep`. |

Cada builder se registra en `services/ktr_builder/registry.py::STEP_BUILDERS` — agregar un step nuevo implica escribir el builder acá primero, importarlo en `registry.py` y sumarlo a ese mapa (+ alias en `STEP_TYPE_ALIASES` si aplica).

## Reglas que aplican
R6 — cada builder es una proyección de infraestructura de la forma canónica de `contracts.py`; no define de nuevo qué campos tiene un step, solo cómo se ven en XML.

## Qué NO va acá
- Una decisión sobre qué campos son obligatorios para un tipo de step — eso es `STEP_CONTRACTS`/`_CRITICAL_FIELDS` en `contracts.py`/`registry.py` (dominio), el builder solo serializa lo que ya llegó validado.
- Normalización de alias de clave del LLM (`returnfield` → `return_field`, etc.) — eso ya pasó en `contracts.normalize_config` antes de llegar acá.
- Lógica de corte/fragmentación — un builder nunca sabe si su step terminó en el mismo `.ktr` que otro.
