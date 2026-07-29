Quiero un análisis a fondo de todos los JSON Schemas de salida del LLM en este
proyecto (backend/app/schemas/llm_output_schemas/*.py) para evaluar costo/beneficio
de convertir campos hoy tipados como {"type": "string"} (JSON libre, parseado con
json.loads() después) a {"type": "object"} real con schema estructurado.

Caso concreto que motivó esto: `ktr.steps[*].config` en
backend/app/schemas/llm_output_schemas/etl_output.py:103-116 es string, no objeto,
a propósito — D18 (docs/refactor/02-decisiones.md) shelveó la versión objeto porque
forzar additionalProperties por tipo de step (~40 tipos distintos, cada uno con
shape propio) requeriría un discriminador oneOf gigante. Consecuencia real
encontrada en esta sesión (H29, docs/refactor/01-hallazgos.md): sin schema que
fuerce el nombre de clave, el LLM puede escribir `table_name`/`schema_table` en vez
de `table` y nada a nivel de contrato de salida lo bloquea — el proyecto compensa
con capas manuales downstream (contracts.py::STEP_CONTRACTS.key_aliases,
required_keys) que son parche, no prevención en origen.

Preguntas a responder:
1. Inventario completo: qué campos en QUÉ schemas (etl_output.py, inference_output.py,
   validator_output.py, document_output.py, job_plan_output.py, job_explain_output.py,
   ddl_validation_output.py) son string-JSON-libre vs objeto real, y por qué cada uno
   quedó como está (¿hay una D-decisión detrás, o fue default sin discutir?).
2. Para cada caso string-libre: ¿el costo de un oneOf discriminado (tokens de schema,
   latencia, tasa de error del proveedor LLM actual con schemas grandes) es hoy menor
   que el costo de los parches downstream que existen para compensar la falta de
   estructura? Medir, no asumir — si hay logs/métricas de generación real, usarlos.
3. ¿Cambió algo desde D18 que cambie el cálculo? (proveedor default es Gemini,
   LLM_PROVIDER switchable a Anthropic — swagger/structured output soportado distinto
   por cada uno; revisar backend/app/models/gemini_llm.py y anthropic_llm.py para
   límites de schema conocidos).
4. Alternativa intermedia no evaluada todavía: schema semi-tipado — objeto con
   propiedades comunes obligatorias (ej. "table" cuando el tipo de step las requiere)
   + un campo "extra" libre para el resto. ¿Reduce el problema de H29 sin pagar el
   costo completo del oneOf?
5. Costo de migración: cuántos call-sites asumen hoy que config llega como string
   (grep "json.loads" y "parse_cfg" en backend/app/services/ktr_builder/) y qué tan
   invasivo sería el cambio.

Restricción de arquitectura del proyecto (CLAUDE.md, "Criterio de capas"): si el
análisis concluye que conviene mover parte de esta validación a domain/, recordar
que domain solo puede importar stdlib (regla direccional: nada que hable con el
mundo exterior) — un schema JSON en sí es dato, no infraestructura, pero su
enforcement contra un provider LLM específico sí lo es.

Entregable esperado: documento de decisión (D-numerada en docs/refactor/02-decisiones.md,
seguir formato existente) con veredicto por campo/schema, no una sola respuesta
genérica para "todos los schemas" — casos distintos pueden tener veredictos distintos.
