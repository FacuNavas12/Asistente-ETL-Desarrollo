# Plan — Refactor de fragmentación

**Mutable.** Se reescribe en el mismo turno en que una fase avanza. No repite estado de fase (ver `ESTADO.md`).

**Última actualización:** 2026-08-01

Deriva de [`00-objetivo.md`](00-objetivo.md) y [`01-hallazgos.md`](01-hallazgos.md), evaluado contra [`02-decisiones.md`](02-decisiones.md) — esa es la fuente de verdad cuando algo choca. Narrativa de sesión (algoritmos, investigación, reportes de cierre) vive en [`03b-reportes.md`](03b-reportes.md). El estado vigente de cada fase vive únicamente en [`ESTADO.md`](ESTADO.md) — acá no se repite, solo fases, dependencias y qué es cada una.

Consolida dos planes que llegaron por separado: **Track A** (auditoría de arquitectura, prompts en `Contexto Cambios/Arquitectura/`) y **Track F** (motor de fragmentación, `Contexto Cambios/Fragmentacion/handoff_fragmentacion_y_errores.md`).

Los dos tracks comparten un tema — el borde tipado de entrada — sin depender de él igual: `00-plan-auditoria.md` lo declaró PASO 1 obligatorio de Track A en su versión grande (H2: schema `string → object`, tipo validado por construcción). Track F no necesita esa versión grande: **D14** (`02-decisiones.md`) separó lo que el motor de corte requiere en concreto (H4, H11, H6) en una fase previa propia, F1.5, ya cerrada e independiente del borde grande de Track A.

---

## Estado vigente

Ver [`ESTADO.md`](ESTADO.md) — única fuente de estado de fase. No se repite acá.

---

## Intake de hallazgos de tests — taxonomía S/G/D/Env

Los tests de fragmentación siguen viniendo (2026-07-22: un test simple, `bitacora_etl_ventas.md`, ya trajo 12 reglas de las cuales solo 3 son corte — ver `01-hallazgos.md`, sección "Intake"). Sin un clasificador, cada test agrega H-numbers sueltos que nadie rutea. Mecanismo, adoptado de la taxonomía S/G/D/E que la propia bitácora ya usa (ahí "E" es fuerza de confirmación — log/DDL/archivo/contraste — no categoría de ruteo; acá se separan los dos ejes):

**Eje 1 — qué tipo de problema es (determina el ruteo):**

| Tag | Qué cubre | Rutea a |
|---|---|---|
| **S** | Estructural-de-corte: races, doble escritor, dimensión sin loader antes del hecho | Track F (F2/F3) |
| **G-step** | Selección de step por forma de tabla o por rol (loader vs. lookup), SCD1/SCD2, materialización de claves en el INSERT | Eje `dim_contracts`/`dimension_step_policy` (D11) — **no** Track F |
| **D-dialecto** | SQL dependiente del motor: tipos de `COALESCE`, `DISTINCT ON`, `generate_series`, alineación de tipos de clave contra el DDL | F4 (contenido generado) + cruza con D12/C.1 (plan de dialecto) |
| **D-integridad** | Completitud referencial: dimensión sin productor, claves no resueltas antes del insert del hecho | F4, algunas bloqueadas por decisión de negocio (ver Abiertos en `02-decisiones.md`) |
| **D-ddl-constraint** | Constraints que el backend podría recomendar/emitir sobre el DDL destino | Nuevo — sin dueño hasta decisión de producto |
| **Env** | Comportamiento específico del motor de ejecución/entorno (versión de PDI, pooler de conexión) que determina qué step usar | Nuevo hallazgo de entorno — destino natural es una regla en `system_etl.txt`, no código del backend |

**Eje 2 — cómo se confirmó (metadato, no determina ruteo):** archivo (análisis estático) / DDL (derivado del esquema) / log (evidencia de ejecución real) / contraste (confirmado por una segunda derivación independiente). Cuanto más fuerte la confirmación, menos discutible el hallazgo — pero no cambia a dónde va.

**Proceso de intake:** cada finding nuevo de un test se tagea con el Eje 1 al momento de registrarlo. El tag determina la fila/documento destino mecánicamente:
- **S** → celda de F2/F3, ya cerrado — cualquier hallazgo S nuevo va a H29 o a un H-number nuevo referenciado desde ahí.
- **G-step** → hallazgo en `01-hallazgos.md`, referenciado desde `dimension_step_policy.py`; si cambia el contrato de `derive_dimension_step_type` es candidato a decisión (D-numerada) en `02-decisiones.md`, no una fase de Track F.
- **D-dialecto / D-integridad** → triage de F4 (D22 en `02-decisiones.md`) o "Abiertos" en `02-decisiones.md` si necesita decisión de negocio primero.
- **D-ddl-constraint / Env** → hallazgo nuevo en `01-hallazgos.md`, sin asignar a ninguna fase existente hasta que alguien decida dónde vive esa superficie (DDL) o ese canal (prompt).

No se crea un H-number por cada regla — solo para información genuinamente nueva. Reglas que ya caen dentro de un mecanismo existente se anotan como referencia cruzada, no como hallazgo nuevo.

---

## Orden macro

```
D3 ✓ · D6/D6-bis ✓ · D7 ✓ (ubicación entregada) · H16 ✓ acotado · D14 ✓ (rompe circularidad F2/F3)
                                        │
Track A: retomada 2026-07-25, A0 ✓, A0.5 ✓ (H29, toca F3) ────┤── PASO 1 grande (borde tipado completo, H2) — no bloquea Track F (D14)
                                        │
Track F: F1 ✓ (2026-07-22)
         │
         │  C.2 ✓ (2026-07-22) — nada que eliminar, handoff ya cumplía D6-bis
         v
    F1.5 ✓ (código, 2026-07-24) — H4 + H11 + H6 cerrados (alcance chico de D14, no el borde grande)
         v
    F2 ✓ (diseño, 2026-07-22) — algoritmo + validado contra err1.ktr/err2.ktr (H21) + APROBADO por usuario (D17, 2026-07-23)
         v
    F2.5 ✓ (código, 2026-07-24) — soporte JobEntryJob (H7) cerrado
         v
    F3 ✓ — corte + jerarquía de jobs + V1/V2/V3. D16 camino 1 cerrado (scd_type==2 en código; 0/1 vía prompt, sin auto-repair).
         Cerrada 2026-07-27 (D28): frontend consume `etapas`/`kjb_master` (D20-punto5).
```

---

## Fases

### Track A — Auditoría de arquitectura (congelada, no reabrir)

Corrió A0 y A0.5 (salida: `docs/auditoria/00-inventario.md`, `docs/auditoria/00b-fallos-silenciosos.md` — siguen citadas). A1-A7 nunca corrieron y quedan congeladas para siempre — no por falta de tiempo: O2 (`20-arquitectura.md` § "Por qué las auditorías de Track A quedan congeladas") encontró que sus tres hallazgos estructurales ya estaban previstos en doctrina escrita antes, y mecanizó lo que A1-A7 iba a auditar en vez de correr la auditoría. Detalle del razonamiento, ahí — no repetido acá.

### Track F — Motor de fragmentación

| Fase | Objetivo | Depende de | Hallazgos |
|---|---|---|---|
| F1 | Investigar: estructura de steps pre-XML, matriz tipo→{lee,escribe}, soporte `JobEntryJob`, orden de `_build_job_plan`, costo de la matriz sin re-parsear XML | Ninguna estructural | H1, H7, H19, H20 |
| C.2 | Contrastar reglas de corte del handoff contra D6-bis, eliminar las que respondan a legibilidad en vez de corrección estructural | Ninguna | — |
| F1.5 | Centralizar dominio mínimo para el corte: alias de tabla, `DBLookup` en el linaje, fail-fast de `config` | F1 | H4, H6, H11 |
| F2 | Diseñar el corte: matriz R/W, disparadores C1/C1-bis, componentes conexos, orden topológico | F1.5, C.2 | H1, H8, H21 |
| F2.5 | Soporte `JobEntryJob` (jerarquía de 3 niveles de KJB) | F1 | H7 |
| F3 | Implementar el corte + jerarquía de jobs, wiring de servicio y de la respuesta HTTP | F2 aprobado, F2.5, D16 | H1, H8, H29 |
| F4 | Track de errores / contenido generado: 6 puntos del handoff + intake de tests (dialecto, integridad, miembro inferido) | Independiente de F1-F3 | H9, H10, H14, H16, H23, H27, H28 |
| F5 | Limpieza de bajo costo, sin dependencias | Ninguna | H12 |

**Pendientes concretos de F4** (movidos desde `04-deuda-abierta.md`, disuelto — T4 de la reorganización documental):
- ~~Validador de contrato entre KTR~~ — implementado por D38 (`contract_validate.py`); nombres cerrados, tipos quedan gap documentado (no simulado).
- **Mejora, no riesgo** — tipos en el validador de contrato entre KTR (`contract_validate.py`, D38 punto 3). Hoy solo compara nombres; el writer no declara tipo propio, así que agregar tipo requeriría inferencia de expresión cross-file (fuera de `contracts.py` por diseño) o caer en el chequeo DDL-vs-DDL que D23 punto 1 ya excluyó como fuente de verdad de este validador. Sin caso real todavía que lo pida — retomar si aparece uno.
- ~~`validate_business_rules()`~~ — removido, sin reemplazo en backend (D39). Responsabilidad de reglas de negocio queda en DDL (ya cubierto parcialmente por el validador de contrato/tipos) + Data Validator (PDI), ítem nuevo abajo.
- **Investigar Data Validator (PDI)** — herramienta nativa de Pentaho para validar reglas de negocio en tiempo de ejecución del `.ktr`, candidata a cubrir lo que `validate_business_rules()` iba a intentar por inspección de steps (D39). Sin investigar todavía: nombre exacto del step/plugin, alcance, forma de integrarlo a la generación. Sin dueño hasta esa investigación.
- Emisión del anti-join + `Union` de miembro inferido (D21) — diseño cerrado, código pendiente.
- **H28(a)** — agregar `("Constant", "fields", "field", "name", "type")` a `FIELD_TYPE_SOURCES` (`error_catalog_checks.py:305-317`). Fix de una línea, sin riesgo.
- **H28(b)** — barrer el resto de los ~12 step types de `registry.py` que declaran `type`/`value_type` por campo, confirmar si `Constant` era el único hueco de `FIELD_TYPE_SOURCES`.
- **D55 (plan de reparación del generador ETL, 8 ítems)** — confirmado 2026-08-01, no ejecutado. Vocabulario `<field><update>` de `DimensionLookup` por modo sin condición de vacío (cierra H51), `ConcatFields` al formato real (`<ConcatFields>` anidado), suite que genera vía `build_ktr()` en vez de consumir el golden como input, semilla `tk=0` sintetizada determinísticamente en el DDL (mecanismo de D47, sin reabrirlo), contra-chequeo narración↔XML, `check_constraint_filter_rows` comparando contra el bound del CHECK, `guard_staging_layer` detectando transformación en la proyección SQL (`sqlglot`), escala `BigNumber` desde `CanonicalField.precision`/`.scale`. Detalle de implementación por ítem en [`plan-reparacion-etl.md`](plan-reparacion-etl.md) — razonamiento y correcciones de revisión en D55, `02-decisiones.md`.

**Verificaciones humanas previas** (nadie con trabajo apoyado en ETLs guardados; D6 re-verificado en frío; ubicación de `err1.ktr`/`err2.ktr` entregada) — las tres resueltas 2026-07-22, ver "Verificaciones pendientes" en `02-decisiones.md`.

---

## Requisito transversal — D13, definición de terminado

Toda fase de Track A y Track F, sin excepción, cierra solo con: (1) dos tests — uno de lo que la fase trabajó, uno del contrato que expone hacia la fase siguiente; (2) el registro de deltas de esa fase (D9), como warnings del pase; (3) `CLAUDE.md` + archivo de progreso actualizados. Detalle completo y el porqué: D13 en `02-decisiones.md`.

**"Dos tests verdes" presupone suite marcada, no suite con ruido implícito — D26** (`02-decisiones.md`): los 45 fallos preexistentes (D20) se marcan `xfail(strict=True)`/`integration` en vez de quedar como texto explicativo sin señal ejecutable; ninguna fase cierra apoyándose en "ya sabíamos que esos fallan" sin ese marcado. D26 también fija la versión chica de R1/R3 (test de arquitectura) que corre antes de que Track A migre la estructura de capas, y el criterio de separación de tests por naturaleza — no implementado todavía, solo decidido.

---

## Paralelizable

- F3 cerrada (D28). F4 (validador de contrato D23, business-rules validator) — puede avanzar en cualquier orden.
- H16 sigue abierto como riesgo genérico (la DB confirma la secuencia de `sk_producto`, pero eso no protege si el step generado mapea algo a esa columna) — no instanciado en el corpus actual, ver H16 en `01-hallazgos.md`.

---

## Backlog — fuera de alcance de este plan, con sesión propia

- **C.1** — plan de soporte multi-motor SQL (Postgres queda de default por D12, el resto no tiene plan).
- **C.4** — auditoría retroactiva de cambios no declarados en commits pasados de generación de KTR. Falta acotar hasta qué commit.
- **Migración de los 34 tests existentes** a la estructura por naturaleza que fija D26 (`unit/`/`integration/`/`manual/`) — decidido, no ejecutado. Sin `conftest.py` hoy en `backend/tests/`; mover sin agregarlo arriesga romper la colección de `pytest.ini` en silencio (mismo patrón que D5/D15 prohíben). No bloquea nada — candidato natural a Track A (A2/A3) o sesión de testing propia.
- **Costo/beneficio de los JSON Schemas de salida del LLM** (`{"type": "string"}` vs `"object"` por campo, revisita de D18) — motivado por H29/D40: `ktr.steps[*].config` (`etl_output.py:103-116`) es string libre a propósito (D18), y esa falta de estructura es la causa raíz de que el nombre de clave `table` no se pueda forzar por schema. Encargo completo ya redactado: `docs/costo/beneficio de JSON Schemas.md`. Sesión propia — necesita spike empírico contra Gemini/Anthropic, no es un criterio que se decida de escritorio.

## Qué queda fuera de este plan

Todo lo listado en "Deliberadamente no decidido" de `02-decisiones.md`: si el borde tipado *grande* (H2, `string → object`, tipo validado por construcción) va como parte de A7-PASO1 o antes, el comportamiento de `build-from-raw` ante raw incompleto, y el plan de soporte multi-motor SQL (C.1). El alcance chico que Track F sí necesitaba (H4, H11, H6) ya no está acá — lo resolvió D14, asignado a F1.5/F2.5. Este plan no fuerza ninguna de las decisiones grandes que siguen abiertas.
