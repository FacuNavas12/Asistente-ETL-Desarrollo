# Candidatos a arquitectura objetivo — hallazgos laterales sin resolver

Mutable. Lo escribe cualquier sesión que tropiece con un hallazgo de diseño (no de bug puntual) mientras trabaja otra fase — se registra acá para contrastar más tarde contra `arquitectura-objetivo.md`, no se actúa sobre él sin decisión aparte. Ver CLAUDE.md, regla "Descubrir es libre, actuar necesita ruta".

---

## C1 — Resolución de "cuál es la key de esta tabla" vive partida en 2 lugares que no se hablan

**Qué:** durante el trabajo de H38 (`docs/refactor/01-hallazgos.md`, CHECK constraints no extraídos del DDL) se probó `ddl_adapter.py` contra un DDL real de DWH (`dim_producto`, `fact_inventario`, constraints nombrados: `CONSTRAINT pk_dim_producto PRIMARY KEY (...)`). Resultado: **0 primary keys y 0 foreign keys detectadas en las 5 tablas del archivo** — `isinstance(expr, exp.PrimaryKey)`/`exp.ForeignKey` nunca matchea porque un constraint nombrado llega envuelto en `exp.Constraint`, no como el tipo directo. Confirmado con sqlglot en los 2 dialectos (postgres/tsql), mismo AST.

Pese a esto, los `.ktr` generados escriben bien en las tablas de dimensión — porque el step `DimensionLookup`/`CombinationLookup` **nunca consulta `ddl_adapter` para saber la key**. Esa info viene de un canal completamente distinto: `dim_contracts[i].natural_keys`, declarado directo por el LLM en su salida estructurada de inferencia (`inference_output.py`), sin pasar por el DDL parseado en absoluto. `dimension_step_policy.py::enforce_dimension_step_policy` arma su lógica desde `dim_contracts`, no desde `schema.primary_key`.

**Por qué importa:** hay 2 fuentes de verdad independientes para la misma pregunta ("¿cuál es la clave de esta tabla?") que nunca se comparan ni se reconcilian:
1. `ddl_adapter` → `CanonicalSchema.primary_key` / `CanonicalField.is_primary_key` (parseado del DDL declarado)
2. LLM → `dim_contracts[i].natural_keys` (inferido, estructurado, independiente del DDL)

Hoy (1) está roto para constraints nombrados y nadie lo notó porque (2) nunca dependió de (1). Pero (1) sí tiene al menos un consumidor real: `structure_inferrer.py::_key_columns_trusted` (pre-check SCD1/SCD2, D37) usa `primary_key`/`is_primary_key` del schema de **origen** (no del DWH) como señal de confianza para `classify_scd_candidates`. Si el DDL de origen también nombra sus constraints (mismo patrón que el DDL de DWH del caso de prueba), esa señal da `key_columns=[]` — falso negativo de "no hay clave declarada" — candidato a conectar con H9 (`01-hallazgos.md`, "SCD2 real perdido"). **No confirmado como causa de H9 en esta sesión — señalado, no probado.**

**Estado:** el bug puntual de parsing (`exp.Constraint` sin desenvolver) se corrige como parte del fix de H38, en el mismo cambio — decisión del usuario, ver `02-decisiones.md`. La pregunta de diseño más grande queda abierta, sin decidir:

> ¿Debería `dim_contracts[i].natural_keys` derivarse de / validarse contra lo que el DDL realmente declara (una sola fuente de verdad), en vez de vivir como 2 canales paralelos que pueden divergir en silencio?

**Evidencia:** `backend/app/services/adapters/ddl_adapter.py:157-163` (loop que no desenvuelve `exp.Constraint`); `backend/app/services/ktr_builder/dimension_step_policy.py:155` (`derived_by_table` desde `dim_contracts`, no desde `schema.primary_key`); `backend/app/services/structure_inferrer.py:101-113` (`_key_columns`/`_key_columns_trusted`, consumidor real de `ddl_adapter.primary_key`); `backend/app/schemas/llm_output_schemas/inference_output.py:16` (`natural_keys` declarado por el LLM).

**Sesión de origen:** 2026-07-29, durante el diseño del fix de H38 (`docs/refactor/01-hallazgos.md`).
