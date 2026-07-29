# Auditoría DDL — reglas, interpretación y uso en el sistema

**Tipo:** foto puntual (snapshot), no append-only — se puede reescribir libremente en próximas sesiones a medida que cambien las reglas o el código.
**Separado de `docs/auditoria/`** a pedido explícito: ese directorio pertenece a otro plan de trabajo, este archivo es independiente.
**Generado:** 2026-07-29, a partir de lectura directa de código + prompts + `docs/refactor/01-hallazgos.md`/`02-decisiones.md`.
**Objetivo:** dar una base para analizar cumplimiento de buenas prácticas de generación/manejo de DDL y detectar dónde ajustar.

⚠️ **Working tree con cambios sin commitear en el momento de este snapshot** (`git status` / `git diff --stat`):
```
backend/app/schemas/context_schemas.py             |   8 ++
backend/app/services/adapters/ddl_adapter.py       | 157 ++++++++++++++++++++-
backend/app/services/adapters/schema_to_context.py |   3 +
backend/app/services/context_builder.py            |  13 +-
backend/app/services/etl_generator.py              |   9 +-
backend/tests/test_ddl_adapter.py                  | 139 ++++++++++++++++++
docs/refactor/01-hallazgos.md                      |   4 +
docs/refactor/02-decisiones.md                     |  46 +++++-
```
Es el trabajo de **D43** (más abajo, § 7) — CHECK constraints + fix de constraints nombrados en `ddl_adapter.py`. Todo lo documentado acá ya refleja ese cambio como si estuviera aplicado (lo está, en disco) — falta el commit.

---

## 1. Mapa del flujo — dónde entra y sale el DDL

```
(a) Usuario pega DDL existente          (b) LLM infiere DDL nuevo
    InputDDL.jsx                            structure_inferrer.py
        │ POST /api/schema/from-ddl             │ system_inference.txt (Parte 1)
        ▼                                       ▼
    ddl_adapter.parse_ddl() ◄───────────────────┘  (mismo parser, ambos caminos)
        │
        ▼
    CanonicalSchema[] (fields con constraints: required/minimum/maximum/enum/PK/FK/default)
        │
        ├─► (a) confirmado por usuario → TablaOrigen.canonical_schema (tabla de ORIGEN)
        │
        └─► (b) InferResponse.stg_ddl / dwh_ddl (texto DDL, no CanonicalSchema — ver § 8, gap)
                │
                │  usuario puede refinar en lenguaje natural (refine_structures, mismo prompt)
                ▼
        ETLFromInferenceRequest.stg_definition / dwh_model  (confirmado por usuario, string)
                │
                ▼
        ddl_validation.validate_and_correct_ddl()  (Parte 3 — LLM, prompt_validacion_src.txt)
                │  audita dwh_model contra dim_contracts + invariantes I2-I9
                │  agrega lo que falte, nunca elimina/renombra/reduce
                ▼
        dwh_ddl final  ──────────────────────────────────────────┐
                │                                                 │
                ▼                                                 ▼
        etl_generator.py arma prompts KTR_2 (STG→DWH)     parse_ddl() se reusa como insumo de
        con este dwh_ddl                                  warnings/validadores (no LLM):
                │                                          - _required_columns_from_ddl
                ▼                                          - _column_types_from_ddl /
        LLM genera steps del .ktr                            _type_mismatch_warnings
                │                                          - _dim_contracts_anomaly_warning
                ▼                                          - _dims_with_inferred_member (D21)
        ktr_default_validator.py / contract_validate.py /   - _known_table_names (D40)
        error_catalog_checks.py auditan el .ktr generado
        contra ese mismo DDL (post-generación)
```

Dos LLM-calls tocan DDL directamente (Parte 1 infiere, Parte 3 audita/corrige); el resto del pipeline solo **lee** el DDL ya confirmado por el usuario, vía el mismo parser determinista (`ddl_adapter.parse_ddl`).

---

## 2. Reglas de diseño exigidas al LLM — Parte 1 (`backend/prompts/system_inference.txt`)

Este es el prompt que **genera** `stg_ddl`/`dwh_ddl`/`dim_contracts` desde `source_description + source_fields + process_goal + business_rules`. Reglas textuales completas (no resumidas — son las que hay que auditar contra buenas prácticas):

### Nomenclatura
- `snake_case`, minúsculas, sin tildes/ñ, un solo idioma, **singular siempre**, sin abreviaturas salvo `id/sk/fk/nro/pct`.
- Tablas: `stg_<sistema>_<entidad>` | `dim_<entidad>` | `fact_<proceso>` | `dwh_<entidad>`. Prohibido `stg_datos`/`stg_carga`/`stg_tabla1` — el nombre debe identificar sistema origen + entidad.
- Columnas: `sk_` surrogate | `fk_` FK a dimensión | `id_<entidad>_origen` clave natural | `es_`/`tiene_` booleanos | `<métrica>_<moneda>` importes convertidos | `stg_`/`dwh_` auditoría.
- Constraints **siempre con nombre explícito**: `pk_<tabla>`, `fk_<origen>_<destino>`, `uq_<tabla>_<cols>`, `ck_<tabla>_<regla>`.

### Documentación obligatoria
- `COMMENT ON TABLE` en toda tabla: contenido, origen, **GRANO**, modo de carga.
- `COMMENT ON COLUMN` en: derivadas/calculadas (fórmula), afectadas por regla de negocio (cita la regla), con default sustitutivo, conversiones de moneda/unidad, técnicas (SCD2, auditoría).

### STG — espejo crudo del origen
| # | Regla |
|---|---|
| S1 | Todos los campos del origen, casteados a tipos SQL estándar |
| S2 | Ninguna columna de origen lleva `NOT NULL`/`CHECK`/`UNIQUE`/`FK` **[I1]** |
| S3 | Ante duda de tipo, `VARCHAR(255)` — el casteo real va en la transformación |
| S4 | Auditoría al final, obligatoria, `NOT NULL` (única excepción a S2): `stg_fecha_carga TIMESTAMP NOT NULL DEFAULT NOW()`, `stg_origen VARCHAR(100) NOT NULL`, `stg_estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO'` |

### DWH — elección de modelo
- Objetivo analítico/BI/KPI → **ESTRELLA**.
- Objetivo de replicación/integración/migración/consolidación operacional → **NORMALIZADO** (prefijo `dwh_`, 3FN, PK/FK nombradas, clave natural `UNIQUE`, `dwh_fecha_carga`).
- Ambiguo → ESTRELLA + declarar en `assumptions`.

### SCD — criterio (ver también § 7, D37)
- Pregunta rectora: ¿hace falta ver el atributo *como era entonces* (SCD2) o *como es hoy* (SCD1)?
- El prompt recibe del backend un bloque **PRE-CHECK SCD** con veredicto por tabla:
  - `NO_HISTORY_POSSIBLE` → **vinculante**, prohibido `scd_type=2` aun con justificación.
  - `HISTORY_DECLARED` → normalmente `scd_type=2`; `attributes_scd2` no puede exceder `candidatos_scd2` del pre-check.
  - `UNDECIDED` → juicio del modelo; default sin señal = SCD1, registrado en `assumptions`.
- Señal de proyecto (alcance temporal del hecho, ej. "carga histórica") **no** es versionado de atributo — se decide dimensión por dimensión, nunca por default global. Señal de cumplimiento normativo → SCD1 prohibido, SCD2 sin excepción.
- `scd_rationale` obligatorio en todo `dim_contract`.

### ESTRELLA — dimensiones (D1-D7) y hechos (F1-F9)
Resumen de las reglas con código propio (texto completo en el archivo fuente):
- D2/F5: SK `SERIAL`/`BIGSERIAL PRIMARY KEY`.
- D3: clave natural `NOT NULL` + `UNIQUE` nombrado; en SCD2, índice nombrado sobre `(clave_natural, fecha_fin)`, **nunca índice parcial** `WHERE es_vigente`/`WHERE fecha_fin IS NULL`.
- D6: `dim_tiempo` con `UNIQUE` sobre fecha + columnas derivadas (año/trimestre/mes/día/etc).
- D7/F2/I8: fila "desconocido" sembrada por `INSERT`, SK = valor que usa el step PDI (0 por defecto); toda `fk_` del fact `NOT NULL DEFAULT <sk desconocido>`.
- F1: GRANO declarado en `COMMENT ON TABLE` — "la decisión más importante del modelo".
- F3/I5: métricas `NUMERIC(15,2)`; multi-moneda con `moneda_origen NOT NULL` sin default + `tasa_cambio_aplicada` solo si hay fuente de tasa.
- F7: un fact **nunca** se carga con `Dimension lookup/update`.
- F8/I9: clave degenerada del origen al grano, `UNIQUE` nombrado.
- F9: un índice por cada columna `fk_` (Postgres no indexa FKs solo).

### Contrato "Dimension lookup/update" (Pentaho PDI) — nombres exactos, no renombrar
```
sk_<entidad>   SERIAL/BIGSERIAL PRIMARY KEY   -- acepta INSERT explícito de 0 [I2]
version        INTEGER NOT NULL DEFAULT 1     -- el step lo exige aun en SCD1
fecha_inicio   TIMESTAMP NOT NULL
fecha_fin      TIMESTAMP NULL                 -- NULLABLE obligatorio [I6]
id_<entidad>_origen                           -- keys del lookup [I3]
```
Vigente ≡ `fecha_fin IS NULL OR fecha_fin >= DATE '2199-01-01'`. `es_vigente` es opcional/solo BI (el step no la mantiene).

### Invariantes I1-I9 (preceden a toda otra regla del prompt)
| # | Invariante | Motivo si se rompe |
|---|---|---|
| I1 | STG sin `NOT NULL` en columnas de origen | Origen trae nulos legítimos, carga aborta antes de poder limpiar |
| I2 | SK con `SERIAL`/`BIGSERIAL`/`GENERATED BY DEFAULT AS IDENTITY`. Prohibido `GENERATED ALWAYS AS IDENTITY` | Postgres rechaza el INSERT explícito del step (error `428C9`) |
| I3 | Clave natural con `UNIQUE` | Sin ella el step no reconoce el registro, inserta fila nueva cada corrida |
| I4 | `dim_tiempo` con `UNIQUE` sobre fecha | Reejecutar el período duplica filas, JOIN cartesiano contra el fact |
| I5 | Multi-moneda: `moneda_origen` NOT NULL sin default; convertida solo con fuente de tasa + `tasa_cambio_aplicada` | Default en `moneda_origen` etiqueta mal filas en silencio; prometer conversión sin calcularla es peor que no ofrecerla |
| I6 | SCD2: `fecha_fin` NULLABLE | NOT NULL rompe el INSERT del primer registro de cada entidad |
| I7 | `CREATE TABLE` en orden de dependencia (dimensiones antes que hechos) | FK a tabla inexistente hace fallar el script completo |
| I8 | Fila "desconocido" sembrada + `fk_` del fact con ese DEFAULT | Hecho huérfano se descarta o rompe la FK |
| I9 | Clave degenerada del fact con `UNIQUE` al grano declarado | Reejecutar el mismo período duplica hechos en silencio (I4 del lado hechos) |

### Precedencia declarada
1. Invariantes I1-I7. 2. Reglas de negocio explícitas del usuario. 3. Reglas de capa (STG/DWH). 4. Nomenclatura y documentación.

### Autovalidación (el LLM se audita antes de responder)
JSON válido; cada `CREATE TABLE` termina en `;`; orden de dependencia [I7]; STG sin restricciones de origen [I1]; 3 columnas de auditoría STG al final; toda SK autogenerada [I2]; `fecha_fin` NULLABLE [I6]; clave natural UNIQUE [I3]; `dim_tiempo` UNIQUE sobre fecha [I4]; columna convertida solo con fuente de tasa [I5]; fila desconocido sembrada y usada como DEFAULT [I8]; clave degenerada del fact [I9]; índice por cada `fk_` [F9]; contrato dimension lookup completo; FK del fact singular [F2]; toda constraint nombrada; `COMMENT ON TABLE` con grano; `COMMENT ON COLUMN` en derivadas/reglas de negocio; nomenclatura; ningún `dim_contract` con `scd_type=2` si el pre-check marcó `NO_HISTORY_POSSIBLE`; `attributes_scd2` ⊆ `candidatos_scd2`; `scd_rationale` presente.

---

## 3. Reglas de auditoría/corrección — Parte 3 (`backend/prompts/prompt_validacion_src.txt`)

Corre en `services/ddl_validation.py::validate_and_correct_ddl()`, **segunda llamada LLM**, antes de armar los prompts de KTR_2 (STG→DWH). Rol: "Auditor de DDL" — revisa `dwh_ddl` final contra `dim_contracts` + invariantes, corrige **solo lo mínimo indispensable**.

### Comportamiento crítico
- Emite **DDL completo, nunca `ALTER TABLE`** (esquema aún no desplegado — un CREATE completo es idempotente/versionable/auditable; una cadena de ALTER obliga a reconstruir mentalmente el estado final).
- Solo **agrega**: columnas, índices, constraints, o amplía un tipo. **Nunca elimina, renombra ni reduce.**
- Las invariantes preceden a cualquier pedido de un step: si un step exige algo que las viola, no se toca la tabla — se reporta el conflicto y la corrección queda del lado del step.
- Si no hay nada que ajustar: `sin_cambios=true`, DDL idéntico (evita reescrituras gratuitas que introduzcan cambios no pedidos).

### Invariantes vigentes en esta fase
Mismas I2-I9 de § 2 (I1 no aplica — es de STG, esta fase solo mira DWH).

### Validaciones V1-V6
| # | Qué verifica | Acción si falta |
|---|---|---|
| V1 | `technical_key`/`version_field`/`date_from`/`date_to` de cada `dim_contracts[i]` existen como columna física | Agrega respetando el contrato (SERIAL/BIGSERIAL PK, INTEGER NOT NULL DEFAULT 1, TIMESTAMP NOT NULL, TIMESTAMP NULL) |
| V2 | Cada `natural_key` existe y tiene `UNIQUE` (o índice compuesto I3 en SCD2) | Agrega |
| V3 | V1+V2 obligatorio para **toda** dimensión listada, sin excepción por `scd_type` | — |
| V4 | Ningún índice de vigencia usa predicado parcial | Reemplaza por índice no parcial equivalente |
| V5 | Toda `dim_*` listada tiene fila "desconocido" sembrada (`INSERT` con `technical_key = unknown_key_value`) | Agrega el INSERT |
| V6 | Coherencia `dim_contracts[i].unknown_key_value` == valor sembrado en el INSERT | **No corrige** — reporta conflicto citando ambos valores (no hay forma de saber cuál es correcto sin contexto de negocio) |

### Regla R8 — registrar todo ajuste
Todo cambio (V1/V2/V4/V5) va en `cambios_aplicados` con formato `"<tabla>: <qué> — motivo: <por qué>"`. Es instrumentación: si esta fase empieza a agregar las mismas columnas en cada corrida, la señal correcta es que la **inferencia** (Parte 1) dejó de emitir el contrato completo — el arreglo va ahí, no acá.

### Conflictos (nunca se auto-resuelven)
- Invariante violada por algo que el DDL de entrada ya declara.
- V6 (unknown_key_value no coincide).
- Cualquier corrección "obvia" que implique eliminar/renombrar/reducir algo existente.

### Short-circuit sin dim_contracts
Sin `dim_contracts` (modelo normalizado, sin dimensiones) no llama al modelo — devuelve el DDL sin tocar. **Acoplamiento documentado:** este atajo asume que "vacío" siempre significa "normalizado", nunca "contrato perdido en el camino" — esa distinción la hace `etl_generator._dim_contracts_anomaly_warning()` en otro archivo, sin llamar a esta función. Si esa advertencia se elimina, el short-circuit queda ciego a un contrato perdido.

---

## 4. Parser estructural determinista — `backend/app/services/adapters/ddl_adapter.py`

Único parser DDL del sistema — sqlglot AST → `list[CanonicalSchema]`. Usado por: endpoint `/api/schema/from-ddl` (usuario pega DDL), y **~7 funciones internas de `etl_generator.py`** que re-parsean `stg_definition`/`dwh_ddl` ya confirmados para derivar warnings (§ 5).

### Qué reconoce hoy
| Elemento SQL | Soporte | Detalle |
|---|---|---|
| Tipos de dato | Amplio (`_SQLGLOT_TYPE_MAP`, ~45 tipos) | Integer/Number/String/Boolean/Date/Time/Datetime/Object/Binary/Array → `CanonicalType`. Tipo no mapeado → `UNKNOWN` + `logger.warning` (nunca excepción) |
| `PRIMARY KEY` (tabla o columna) | Sí, **incluyendo nombrado** (`CONSTRAINT x PRIMARY KEY(...)`) | `_unwrap_table_level_constraint` desenvuelve `exp.Constraint` — fix de D43, antes se perdían en silencio |
| `FOREIGN KEY` (tabla) | Sí, incluyendo nombrado | Extrae `fields`/`reference_resource`/`reference_fields` |
| `NOT NULL` (columna) | Sí | → `FieldConstraints.required` |
| `DEFAULT` (columna) | Sí | Clasificado vía `sql_defaults.classify_default_expr()` en `literal` vs `function` (regex, sin dialecto — `NOW()`, `CURRENT_TIMESTAMP`, `gen_random_uuid()`, etc.) |
| `CHECK` — `col OP lit` (`>=`/`<=`/`>`/`<`, cualquier orden) | Sí (D43) | → `minimum`/`maximum`. `AND` recursivo (multi-columna, cualquier profundidad) |
| `CHECK` — `BETWEEN` | Sí (D43) | → `minimum`/`maximum` directo |
| `CHECK` — `IN (...)` | Sí (D43), solo si todos los valores son literales | → `FieldConstraints.enum` |
| Operadores estrictos `>`/`<` | Solo para `CanonicalType.INTEGER` (ajuste `+1`/`-1`) | Para `NUMBER` se descarta y loggea — falta conocer la escala del tipo (diferido) |
| Precision/scale/length | Sí | Por familia de tipo (`_PRECISION_SQLGLOT_TYPES`/`_LENGTH_SQLGLOT_TYPES`) |
| UUID | Sí | `format="uuid"` |

### Qué NO reconoce (descartado y loggeado, nunca excepción)
- `CHECK` con `OR`.
- `CHECK` con funciones (`LENGTH(...)`, etc.).
- `CHECK` columna-vs-columna o con subqueries.
- Rangos sobre fecha/texto (`CHECK (fecha >= '2020-01-01')`) — **diferido explícitamente**, falta info del usuario para diseñar el enfoque.
- `NUMBER`/`NUMERIC` con operador estricto (`>`/`<`) — sin escala conocida no hay "próximo valor"; ruta trazada pero no implementada: `Decimal(1).scaleb(-scale)`.
- Todo lo demás que no matchea sqlglot AST esperado (sintaxis inválida) → `ValueError("Error de sintaxis SQL: ...")`, único punto donde `parse_ddl` sí levanta.

### Garantía de diseño
`parse_ddl()` nunca levanta excepción por un `CREATE TABLE` individual malformado — lo loggea y sigue con el resto (`except Exception: logger.warning(...)`); solo el parseo sintáctico global (`sqlglot.parse`) puede fallar duro.

---

## 5. Propagación al prompt del LLM — único exit point

Invariante del proyecto (CLAUDE.md): **`format_model_context_for_prompt()` es el único punto de salida al prompt**, whitelist de campos, nunca filas de datos.

Cadena para que `minimum`/`maximum`/`enum` del CHECK lleguen al LLM (D43, propagación — "hueco 3" del hallazgo original, sin esto quedaban poblados pero invisibles):
```
ddl_adapter.parse_ddl()          → CanonicalField.constraints (minimum/maximum/enum)
  → schema_to_context._field_to_minimal_profile()   → ColumnProfile (nuevos campos)
    → context_builder.format_model_context_for_prompt()
      → texto: "rango válido (CHECK del DDL): ..." / "valores válidos (CHECK del DDL): ..."
```
Antes de D43: `FieldConstraints.minimum`/`maximum` existían en el schema desde su creación **sin un solo escritor en todo el backend** (H38) — campo de schema muerto, no solo hueco del adapter.

---

## 6. Consumo del DDL parseado — post-confirmación, dentro de `etl_generator.py`

Todas best-effort: DDL no parseable → resultado vacío + `logger.warning`, **nunca corta el flujo**.

| Función | Ubicación | Qué hace |
|---|---|---|
| `_required_columns_from_ddl` | `etl_generator.py:76` | `{tabla: [columnas NOT NULL sin default]}` — insumo de `check_missing_required_fields` en `build_ktr()` |
| `_column_types_from_ddl` | `etl_generator.py:99` | `{columna_lower: CanonicalType}` agregando todas las tablas — insumo de `_type_mismatch_warnings` |
| `_type_mismatch_warnings` | `etl_generator.py:129` | Compara STG↔DWH: mismo nombre de columna, familia de tipo incompatible (string↔integer/number/boolean), sin `cast` explícito en `SelectValues` → warning. **No bloqueante.** No ve tipos de origen (solo STG vs DWH ya parseados) |
| `_staging_table_names_from_ddl` | `etl_generator.py:171` | Nombres de tabla STG declarados — fija los mismos nombres entre las 2 llamadas del flujo 2-KTR, insumo de costura de linaje |
| `_known_table_names` | `etl_generator.py:187` | Nombres físicos reales (lowercase, todas las tablas) — insumo de `validators.recover_table_key` (D40/H29) |
| `_dim_contracts_anomaly_warning` | `etl_generator.py:252` | `dwh_model` declara `dim_*` pero `dim_contracts` llega vacío → warning explícito (sin esto, degrada en silencio al parseo por convención de nombres — el bug que `dim_contracts` reemplaza) |
| `_dims_with_inferred_member` | `etl_generator.py:279` | FK NOT NULL de un fact hacia una dimensión → exige patrón anti-join+Union (miembro inferido, D21) — reusa `is_foreign_key`/`references`/`constraints.required` del `CanonicalField` |

## 6b. Validadores post-generación — auditan el `.ktr` YA generado contra el DDL

| Archivo | Qué hace | Relación con DDL |
|---|---|---|
| `ktr_default_validator.py` | `scrub_function_default_constants` (limpia Constants con función SQL como literal) + `check_missing_required_fields` (reporta, no repara, columnas NOT NULL sin default sin mapeo) | Consume `required_columns_by_table` derivado del DDL por el caller |
| `ktr_builder/contract_validate.py` (D23/D38) | Compara escritor↔lector **entre KTRs** (lo que un KTR escribe vs. lo que otro espera leer) | Usa DDL **solo** para saber qué columnas son NOT NULL en cada tabla — el contenido real lo compara contra el otro KTR, no contra el DDL. Gap documentado: tipos NO implementado (re-empaquetaría el mismo chequeo que `_type_mismatch_warnings`, que D23 dice explícitamente que no cuenta como este validador) |
| `ktr_builder/error_catalog_checks.py` (V5→E2) | Columnas técnicas que exige `DimensionLookup` (key/date/version/return) existen en la tabla real | DDL provisto por el caller. Standalone, no wireado a `build_ktr()` — corre como diagnóstico |

---

## 7. Track de decisiones y hallazgos relevantes

| ID | Qué | Estado |
|---|---|---|
| D21 | FK NOT NULL sin resolver → política = miembro inferido (anti-join+Union) | Ejecutado — residual en `04-verificacion.md` |
| D23 | Alcance del validador de contrato writer↔reader entre KTRs | Cerrado (implementado por D38) |
| D37 | Criterio determinista SCD1 vs SCD2 — pre-check en `domain/scd.py` + criterio en `system_inference.txt` | Ejecutado |
| D38 | Validador de contrato entre KTR implementado (nombres; tipos = gap documentado) | Ejecutado |
| D39 | `validate_business_rules()` stub removido — responsabilidad pasa a DDL + futura herramienta Data Validator (PDI) | Ejecutado. **Gap que deja abierto:** sigue sin existir verificación de que `reglasNegocio` (texto libre) se haya aplicado — DDL cubre solo lo expresable como constraint |
| D40 | H29 — recuperación determinista de `table` por contenido (no posición); nace `ktr_builder/validators/` | Ejecutado |
| D41 | H40 — pass `flag_dead_computed_fields` (warning) para `Calculator` sin consumidor downstream | Ejecutado |
| **D43** | **H38 — CHECK del DDL (`col OP lit`, `BETWEEN`, `IN`) → `minimum`/`maximum`/`enum`; fix de PK/FK con `CONSTRAINT` nombrado** | **Ejecutado esta sesión (2026-07-29), sin commitear** — ver § 4/5. 28 tests nuevos, 603 verdes, 0 regresión (verificado con `git stash` aislando los archivos tocados) |
| H29 | `build_rw_matrix()` excluía steps sin `table` sin notificar | Cerrado parcial — D40 |
| H38 | CHECK constraints nunca llegaban al LLM; `minimum`/`maximum` muerto en todo el backend | Cerrado — D43 |
| H39 | `system_etl.txt` no fijaba que validación de reglas de negocio va solo en STG→DWH (LLM duplicaba filtro en origen→staging) | Cerrado — D42 (causa raíz: bloque `## REGLAS DE NEGOCIO` se pegaba en las 2 llamadas) |
| H40 | Campo calculado sin consumidor downstream no generaba warning | Cerrado — D41 |

---

## 8. Gaps conocidos / abiertos — candidatos a revisar

1. **`InferResponse.stg_ddl`/`dwh_ddl` son texto plano, no `CanonicalSchema`.** La Parte 1 (LLM) genera DDL como string; recién se vuelve `CanonicalSchema` estructurado cuando algo lo re-parsea (`ddl_adapter.parse_ddl`, invocado internamente varias veces sobre el mismo texto en distintos puntos de `etl_generator.py`, § 6). No hay una única estructura canónica compartida entre "lo que el LLM generó" y "lo que el backend valida" — se re-parsea el mismo string repetidamente.
2. **Rangos CHECK sobre fecha/texto no soportados** (diferido, D43) — `CHECK (fecha >= '2020-01-01')` se descarta.
3. **Escala de `NUMERIC`/`NUMBER` en operadores estrictos no soportada** (diferido, D43) — ruta trazada (`Decimal(1).scaleb(-scale)`) pero no implementada.
4. **Responsabilidad de "cuál es la key de una tabla" vive partida en 2 lugares que nunca se comparan entre sí** (hallazgo lateral de D43): `ddl_adapter` (parseo del DDL declarado) y `dim_contracts[i].natural_keys` (declarado por el LLM en la inferencia, canal independiente). Candidato a unificación — ver `docs/arquitectura-objetivo-candidatos.md` § C1.
5. **C.5 (`02-decisiones.md`, abierto):** ¿el backend debería recomendar/emitir constraints DDL cuando detecta uno faltante (ej. `dim_producto` sin `UNIQUE(id_producto)` → duplicados en reprocesos concurrentes)? Hoy no hay mecanismo — camino barato disponible sin abrir superficie nueva: canal `advertencias_buenas_practicas` (ya existe, advisory-only). No decidido.
   - **A verificar en esta auditoría:** esa nota dice "el backend no emite DDL en ningún punto, `dwh_ddl` es siempre input" — a contrastar contra que la Parte 1 (`structure_inferrer.py`) sí hace que el LLM *genere* `dwh_ddl` como output de `InferResponse`. Puede ser una distinción válida (código Python del backend vs. LLM) o una nota desactualizada — no resuelto en este documento, queda para el análisis del usuario.
6. **C.1 (abierto):** soporte multi-dialecto SQL sin plan — dónde vive la decisión de dialecto, qué construcciones dependen de motor más allá de `DISTINCT ON`, qué pasa si el usuario cambia de motor después de generar. Postgres es default (D12), pero `ddl_adapter.parse_ddl()` sí acepta `dialect` (ansi/postgres/tsql/mysql) desde el endpoint — el gap es de producto/UX, no del parser.
7. **D39 sin resolver:** ninguna verificación de que `reglasNegocio` (texto libre) se haya aplicado a los steps generados — DDL cubre el subconjunto expresable como constraint, el resto queda sin verificar en ningún punto del pipeline.

---

## 9. Cobertura de tests

- `backend/tests/test_ddl_adapter.py` — suite principal del parser (incluye D43: `TestNamedConstraints`, `TestCheckConstraints`, dialectos parametrizados postgres/tsql).
- `backend/tests/test_ddl_adapter_defaults.py` — clasificación `default_kind` (literal/función).
- `backend/tests/test_canonical_schema.py` — shape `CanonicalSchema`/`CanonicalField`.
- `backend/tests/test_contract_validate.py` — validador D23/D38 (writer↔reader).
- `backend/tests/test_inferred_member.py` — D21 (miembro inferido), 13 casos incluyendo DDL vacío/inválido.
- `backend/tests/test_table_key_recovery.py` — D40 (recuperación de `table`).
