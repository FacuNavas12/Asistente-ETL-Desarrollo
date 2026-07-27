# schemas

**Capa:** `schemas`
**Propósito:** el contrato de datos que cruza HTTP entre este backend y el frontend React (y, para `canonical.py`, el vocabulario interno compartido entre los 4 caminos de entrada de esquema).

## Qué entra
Nada — son solo definiciones de tipo. Los routers instancian estos modelos a partir del body/query de la request; los services los devuelven ya poblados.

## Qué sale
Los mismos modelos, serializados a JSON por FastAPI en la response. El frontend (`api/*.js`) los consume tal cual.

## Archivos
| Archivo | Qué hace |
|---|---|
| `canonical.py` | `CanonicalSchema`/`CanonicalField` — esquema intermedio al que convergen los 3 adapters de entrada (CSV/Excel, BD, DDL). Reexporta `CanonicalType`/`FieldFormat`/`ColumnRole` desde `domain/canonical_types.py` (excepción nombrada, no de paquete — son value objects puros de stdlib, ver ese archivo). |
| `common.py` | `CamelModel` base + `WorkflowStatus`. |
| `connection.py` | Schemas de conexión (create/update/read/test). `ConnectionRead.password` siempre `"********"` — nunca se serializa el real. |
| `context_schemas.py` | `ModelContext`/`ModelTableContext`/`ColumnStats`/`ColumnProfile` — lo que sí llega al prompt del LLM. |
| `etl.py`, `job.py` | Schemas de persistencia simple (`Etl`/`Job`). |
| `etl_schemas.py` | Contratos del flujo de generación IA: `ETLGenerateResponse`, `EtapaOutput`, `DimContract`, `StepETL`. |
| `job_schemas.py` | `JobPlan`/`JobEntry` del flujo de generación de `.kjb`. |
| `lineage.py` | `Lineage`/`LineageNode`/`LineageEdge`. |
| `llm_output_schemas/` | Subpaquete aparte — ver su propio README, es contrato de una fuente externa, no de la API. |

## Reglas que aplican
R5 — `canonical.py` es el tipo al que cruzan los 4 caminos de entrada de esquema (CSV, BD, DDL, formulario); después de eso ningún módulo interior vuelve a validar estructura.
R6 — `CanonicalSchema` es la única forma canónica del esquema de una tabla de origen. No se reinventa por camino de entrada.

## Qué NO va acá
- Una función que llama al LLM o a la DB — un schema nunca importa nada del proyecto (tabla de Capas: "Puede importar: Nada del proyecto").
- Un `@validator` que decide una regla de negocio (ej. "si el tipo es X, la longitud tiene que ser Y") — eso es dominio; el schema valida forma, no reglas de negocio.
- Una definición nueva de `CanonicalType`/`FieldFormat`/`ColumnRole` acá — viven en `domain/canonical_types.py`, este archivo solo reexporta. `type_mappings.py` (infra, reclasificado en la sesión de arquitectura) los importa directo de `domain/`, no de acá — la fachada existe para no romper a los consumidores existentes, no para que código nuevo la use.
