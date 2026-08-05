# models

**Capa:** mezcla `infrastructure/llm/` e `infrastructure/persistence/` — ver "Qué NO va acá".
**Propósito:** dos cosas sin relación entre sí que comparten carpeta por historia, no por diseño.

## Qué entra
- Cliente LLM: prompt (string) + schema de salida estructurada → llamada HTTP al proveedor configurado (`LLM_PROVIDER`).
- ORM: sesión SQLAlchemy + operaciones CRUD desde `repositories/` o (hoy, deuda) directo desde algunos routers.

## Qué sale
- Cliente LLM: `LLMResponse` (`llm_base.py`) con `json_data: dict` ya parseado.
- ORM: filas de las tablas `etls`/`jobs`/`ktr_build_jobs`/`connections`.

## Archivos
| Archivo | Qué hace |
|---|---|
| `llm_base.py` | ABC `BaseLLM` + `LLMResponse`. Es, en la práctica, el puerto `LLMProvider` de la doctrina — ver `docs/arquitectura-objetivo.md` sección "Qué está sobre-especificado hoy". |
| `anthropic_llm.py` | Implementación `BaseLLM` para Anthropic. |
| `gemini_llm.py` | Implementación `BaseLLM` para Gemini. |
| `llm_factory.py` | `build_llm(settings, role)` — elige proveedor según `settings.llm_provider`, sin singleton. |
| `base.py` | `WorkflowItemMixin` — columnas compartidas por `Etl`/`Job` (ORM). |
| `connection.py` | ORM `Connection` + enums `DbType`/`TestStatus`. Nunca tiene columna de password — ver "Credenciales de conexión" en `GUIA_TECNICA.md`. |
| `etl.py`, `job.py` | ORM `Etl`/`Job`, heredan `WorkflowItemMixin`. |
| `ktr_build_job.py` | ORM `KtrBuildJob` — correlación entre generación async y conexiones destino. |

## Reglas que aplican
R1, R6 — el cliente LLM es infraestructura (adapta una fuente externa); el ORM también. Ninguno de los dos es dominio.
R5 — el ORM es uno de los bordes de entrada: filas de DB cruzan hacia adentro ya tipadas (Pydantic vía `schemas/`), nunca como `Row` crudo.

## Qué NO va acá
- Un modelo Pydantic de contrato HTTP — eso es `schemas/`.
- Lógica de negocio en un método del ORM (ej. "si `status == 'failed'`, reintentar") — eso es un service.
- Un `if` sobre `settings.llm_provider` fuera de `llm_factory.py` — el resto del código nunca sabe qué proveedor está activo, solo conoce `BaseLLM`.

**Por qué el nombre `models/` desaparece en la doctrina objetivo:** mezcla dos capas (`infrastructure/llm/` e `infrastructure/persistence/`) bajo un nombre que no dice cuál es cuál — ver `docs/arquitectura-objetivo.md`, fila correspondiente del mapa E1.
