# services

**Capa:** hoy, mezclada — mayoría `services/` (casos de uso), con dominio puro y infraestructura viviendo acá también sin separación física. Ver tabla de abajo para cuál es cuál.
**Propósito:** todo lo que no es "hablar HTTP" (`routers/`) ni "ser un tipo de dato" (`schemas/`) terminó acá, incluida bastante infraestructura e incluso reglas de dominio puras.

## Qué entra
Depende del archivo: contexto de ETL armado por el router (para los casos de uso), o config/conexión real (para lo que es infraestructura de facto: `db_connector.py`, `profiler.py`, `superset_client/`).

## Qué sale
Depende del archivo: `ETLGenerateResponse`/`JobPlan` para los casos de uso; filas/columnas reales para lo que toca DB; XML validado para los validadores.

## Archivos (top-level, sin subpaquetes — esos tienen su propio README)

| Archivo | Capa objetivo real | Qué hace |
|---|---|---|
| `etl_generator.py` (1188 líneas) | **partido** — orquestación en `services/`, ~12 funciones auxiliares de análisis candidatas a `domain/` | Orquestador central del flujo ETL. Ver propuesta de corte abajo. |
| `job_analyzer.py` | `services/` | Análisis/refinamiento/generación de Jobs PDI desde `.ktr` subidos. Importa `fastapi.UploadFile` directo (R3, congelado). |
| `db_connector.py`, `dialect.py`, `profiler.py`, `masker.py` | `infrastructure/db_inspection/` | Conexión real a la BD externa del usuario, perfilado estadístico, enmascarado de muestras. Viven acá por historia, no por capa. |
| `context_builder.py` | `services/` | Arma `ModelContext` desde los 4 caminos de entrada — único punto de serialización a texto de prompt. |
| `etl_service.py`, `job_service.py` | `services/` | CRUD de `Etl`/`Job`. Importan `fastapi.HTTPException` directo (R3, congelado). |
| `structure_inferrer.py` | `services/` | Inferencia automática de DDL STG/DWH desde 3 campos de usuario. |
| `type_mappings.py` | `infrastructure/db_inspection/` | Mapeo tipos SQL crudos → `CanonicalType`. Traduce vocabulario de un vendor concreto (Postgres/SQL Server) — importa `domain/canonical_types.py` directo, consumido solo por `db_adapter.py` (otro adaptador). Reclasificado de `domain/` a infra en la sesión de arquitectura, ver `docs/arquitectura-objetivo.md`, criterio "vocabulario PDI es dominio" en `CLAUDE.md`. |
| `file_schema.py` | `infrastructure/schema_sources/` | Inferencia de esquema desde CSV/Excel vía Frictionless. Dueño del borde de upload (O2-d): `infer_schema_from_upload(filename, chunks)` valida extensión/tamaño, spoolea a tempfile y limpia — `routers/schema.py` ya no toca disco. |
| `ddl_validation.py` | `services/` | Audita/corrige DDL DWH contra `dim_contracts` vía LLM. |
| `ktr_xml_validator.py`, `kjb_xml_validator.py` | `infrastructure/pentaho/` | Lint post-generación de `.ktr`/`.kjb` — última barrera antes de entregar el XML. |
| `masker.py` | `infrastructure/db_inspection/` | Enmascarado format-preserving de valores de muestra. |
| `documenter.py`, `validator.py` | `services/` | Documentación / validación de calidad vía LLM. |
| `sql_defaults.py` | `domain/` | Clasifica un DEFAULT SQL como literal vs. función/expresión. Puro. |
| `lineage_builder.py` | **Ejecutado (O2-c)** — `build_lineage`/`stitch_lineage_many`/`stitch_lineage` puros movidos a `domain/lineage.py`; acá queda el borde: envuelve `LineageGraphData` en `Lineage` (Pydantic) para la API y `_parse_ktr_xml` (lee XML, infra) | Construcción del grafo de linaje. |

Detalle de cada uno con línea exacta: `docs/auditoria/00-inventario.md` sección 1.

## Sobre `etl_generator.py`

Es el README más importante de esta carpeta porque es el archivo más grande y el que más mezcla. Contiene tanto orquestación real (`generate_etl_from_inference`, `generate_etl_async`, `_build_response_from_two_ktr_data`, `_build_job_plan` — coordinan LLM + `ktr_builder` + `lineage_builder`, eso es `services/` por definición) como una docena de funciones de análisis auxiliares que son reglas puras sobre un DDL o un dict de steps, sin nada de orquestación: `_required_columns_from_ddl`, `_column_types_from_ddl`/`_type_mismatch_warnings`, `_staging_table_names_from_ddl`, `_dim_contracts_anomaly_warning`, `_dims_with_inferred_member` (línea exacta de cada una: `docs/auditoria/00b-fallos-silenciosos.md` sección 3.3). Estas últimas son candidatas naturales a `domain/` — comparten el mismo defecto (parsean DDL con `sqlglot`/`ddl_adapter.parse_ddl` y degradan a `[]`/`{}` si falla, sección 3.3 del censo de fallos silenciosos) y separarlas en su propio módulo (`domain/ddl_checks.py` o similar, cuando le toque — ver "Regla de migración") las deja testeables sin levantar el resto del pipeline. **Propuesta, no ejecutada esta sesión.**

## Reglas que aplican
R3 — ningún archivo de acá debería importar `fastapi` (violado hoy en 3 archivos, congelado en `backend/tests/test_architecture_layers.py::FROZEN_R3`) ni `sqlalchemy` directo (violado en más archivos todavía, fuera del recorte de ese test — ver su docstring).
R7 — `sql_defaults.py` es pieza de conocimiento de dominio puro que ya vive acá suelta; no debería crecer con más lógica de casos de uso mezclada adentro. (`type_mappings.py` salió de este grupo — es infra, ver tabla. `validate_business_rules.py` salió del grupo — removido, D39 en `docs/refactor/02-decisiones.md`.)

## Qué NO va acá
- Una regla nueva sobre "qué tabla toca un step" o "qué campos tiene" — eso es `services/ktr_builder/contracts.py` o dominio nuevo, no una función más en `etl_generator.py` (R7: un solo lugar).
- Un cliente HTTP nuevo a un servicio externo — eso es infraestructura, aunque hoy convivan acá `db_connector.py`/`superset_client/` por historia.
- SQL armado a mano fuera de un repositorio (R9).
