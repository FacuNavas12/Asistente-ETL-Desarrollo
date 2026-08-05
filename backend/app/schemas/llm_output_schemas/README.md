# schemas/llm_output_schemas

**Capa:** `infrastructure/llm/`
**Propósito:** el JSON Schema que le decimos al LLM que respete al generar salida estructurada — contrato de una fuente externa (el proveedor de LLM), no de la API HTTP.

## Qué entra
Nada en runtime — son constantes Python (dicts JSON Schema) importadas por `models/gemini_llm.py`/`anthropic_llm.py` al armar la request de "structured output".

## Qué sale
El dict `JSON Schema` se manda al SDK del proveedor. La respuesta que vuelve (`json_data`, ya validada contra este schema por el proveedor) es lo que consume `services/etl_generator.py` — sin volver a validarla con Pydantic, ver `docs/auditoria/00-inventario.md` sección 3.2.

## Archivos
| Archivo | Qué hace |
|---|---|
| `etl_output.py` | `ETL_OUTPUT_SCHEMA` — el más grande, define `ktr.steps[*] = {name, type, config: string}` (`config` explícitamente string JSON, no objeto — justificado en el propio docstring del archivo). |
| `inference_output.py` | Schema de `/infer-structures`. |
| `job_plan_output.py` | Schema de generación de `.kjb`. |
| `ddl_validation_output.py` | Schema de `validate_and_correct_ddl`. |
| `validator_output.py` | Schema de `/etl/validate`. |
| `document_output.py` | Schema de `/etl/document`. |
| `job_explain_output.py` | Schema de la explicación de Job generado. |

## Reglas que aplican
R5 — este es el borde de entrada de la fuente "LLM": el dict que vuelve del proveedor se parsea acá conceptualmente (el schema define la forma esperada), aunque la validación real de que el dict cumpla el schema la hace el SDK del proveedor, no Pydantic — ver "No verificable sin ejecutar" en `docs/auditoria/00-inventario.md` sección 4.
R6 — por qué `config` es `string` y no `object` en el schema: ver docstring de `etl_output.py:1-14`.

## Qué NO va acá
- Un schema de contrato HTTP (eso es `schemas/etl_schemas.py` y hermanos, un directorio arriba).
- Lógica de parseo del JSON que vuelve — eso es `services/ktr_builder/contracts.py::parse_cfg` (dominio) o `etl_generator.py` (orquestación), nunca acá.
