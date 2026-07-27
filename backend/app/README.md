# backend/app

Punto de entrada para alguien que nunca vio este proyecto. Cinco minutos de lectura acá deberían alcanzar para saber dónde tocar.

## Qué hace el sistema

Backend FastAPI de un producto que acelera la creación de procesos ETL en Pentaho (PDI/Spoon). El usuario describe, desde un frontend React, de dónde vienen los datos (BD, CSV/Excel, DDL pegado o formulario manual), a qué staging y DWH van, y qué reglas de negocio aplican. El backend le manda esa descripción a un LLM (Gemini o Anthropic, intercambiable), recibe una definición de *steps* de transformación, la valida/repara, y genera los artefactos físicos de Pentaho (`.ktr`/`.kjb`) más el linaje de tablas — listos para abrir en Spoon.

## El recorrido de una request, de punta a punta

```
Usuario (React) ─▶ routers/ai.py POST /generate-from-inference
                       │
                       ├─▶ services/context_builder.py     (esquema origen → texto de prompt, único punto de salida)
                       ├─▶ services/ddl_validation.py       (LLM #0: corrige DDL del DWH)
                       ├─▶ models/{gemini,anthropic}_llm.py (LLM #1: origen→STG, LLM #2: STG→DWH)
                       │       devuelve dict {ktr: {steps: [...]}} — ver "Estructuras en circulación"
                       │       en docs/auditoria/00-inventario.md sección 5
                       ├─▶ services/ktr_builder/contracts.py     (normaliza config de cada step)
                       ├─▶ services/ktr_builder/repair.py        (LLM acotado: repara steps incompletos)
                       ├─▶ services/ktr_builder/fragmentation.py (decide en cuántos .ktr se corta cada fase)
                       ├─▶ services/ktr_builder/build.py         (serializa steps → XML .ktr, 1x por archivo)
                       ├─▶ services/job_analyzer.py::build_kjb_xml (si hubo corte: .kjb que los encadena)
                       ├─▶ services/lineage_builder.py           (grafo de linaje, cose los .ktr entre sí)
                       └─▶ schemas/etl_schemas.py::ETLGenerateResponse (respuesta final al frontend)
```

Detalle completo del orden real de llamadas, con `archivo:línea`: `docs/auditoria/00-inventario.md` sección 3.6.

## Mapa de carpetas

| Carpeta | Qué es | README |
|---|---|---|
| `routers/` | Endpoints HTTP | [routers/README.md](routers/README.md) |
| `schemas/` | Contratos Pydantic (HTTP + salida LLM) | [schemas/README.md](schemas/README.md) |
| `domain/` | Entidades y vocabulario puro (primer paquete físico de esta capa) | [domain/README.md](domain/README.md) |
| `models/` | LLM clients + ORM (dos capas, un nombre — ver su README) | [models/README.md](models/README.md) |
| `services/` | Casos de uso de orquestación | [services/README.md](services/README.md) |
| `services/ktr_builder/` | Motor de serialización/reparación/corte del `.ktr` | [services/ktr_builder/README.md](services/ktr_builder/README.md) |
| `services/ktr_builder/steps/` | Un builder XML por familia de step Kettle | [services/ktr_builder/steps/README.md](services/ktr_builder/steps/README.md) |
| `services/adapters/` | Convergen en `CanonicalSchema` | [services/adapters/README.md](services/adapters/README.md) |
| `services/superset_client/` | Cliente API REST de Superset | [services/superset_client/README.md](services/superset_client/README.md) |
| `services/superset_export/` | Arma el ZIP de export a Superset | [services/superset_export/README.md](services/superset_export/README.md) |
| `repositories/` | CRUD genérico sobre SQLAlchemy | [repositories/README.md](repositories/README.md) |
| `outbox/` | Persistencia local + drenaje a Supabase | [outbox/README.md](outbox/README.md) |
| `core/` | Config, auth, DB, logging | [core/README.md](core/README.md) |

## Dónde está la doctrina

`docs/arquitectura-objetivo.md` — capas objetivo, reglas R1-R12, mapa capa↔directorio actual, y qué del diseño está sobre-especificado. Este árbol de carpetas es el estado de hoy; ese documento es a dónde converge (sin mover nada todavía — ver "Regla de migración" ahí).
