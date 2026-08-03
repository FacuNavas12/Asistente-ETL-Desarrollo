# Congelado — retomar después de entregar

**Mutable.** Lo escribe quien congela o descongela un ítem. Entrada: [`docs/README.md`](../README.md).

**Qué es esto:** todo lo abierto que **no** entra en [O0](00-higiene-repo.md), [O1](10-estabilizar-emision.md) ni [O2](20-arquitectura.md). Congelado por corte hacia la entrega, 2026-08-03 — no por falta de mérito.

**Cómo se usa:** al volver, se entra por acá, no por `03-plan.md` ni por `ESTADO.md`. Cada fila dice dónde vive el detalle real; este archivo indexa, no reemplaza a ninguna fuente.

**Cómo se descongela:** se saca la fila, se abre un objetivo, y la decisión se escribe como D-N en `02-decisiones.md`. Nunca se retoma un ítem "de paso" mientras se trabaja en otro — es la regla 4 de `CLAUDE.md`.

---

## Verificación sin correr — lo que envejece peor

Nada de esto lo captura la suite determinista. Cuanto más se acumula, más caro es atribuir un fallo a una regla concreta. **Es lo primero que se descongela.**

| # | Qué | Detalle en | Qué lo destraba |
|---|---|---|---|
| V1 | **Fase 4 — corrida real end-to-end.** Criterio S-12 (2+ modelos × N corridas) sin cumplir: 1 corrida de Sonnet, 0 de Haiku | `03c-investigacion-...md` Fase 4, `fase4_manual/` | Crédito de API + `uvicorn`+frontend levantados |
| V2 | **D44/D51 — vocabulario uniforme de dimensión** sin corrida que lo ejerza. Riesgo medio-alto: el `.ktr` sale limpio, findings en cero, y el FK queda mal en runtime | `04-verificacion.md` fila 4 | V1 |
| V3 | **Miembro inferido** — que el loader sobrescriba la fila placeholder cuando llega el producto real. Silencioso e irreversible si falla | `04-verificacion.md` fila 1, D21 | V1 + emisión del anti-join (T4 abajo) |
| V4 | **B17** — operandos `BigNumber` en `Calculator`/`Formula`. El checker existe; nunca corrió una generación real después de agregar la regla | `04-verificacion.md` fila 2 | V1 |
| V5 | **Aritmética Kettle detrás de B17** — ¿alcanza un operando `BigNumber` para promover a `BigDecimal`? No bloqueante: la regla actual es conservadora | `04-verificacion.md` fila 3, H27 | Leer `Calculator.java`/`ValueDataUtil.java` |
| V6 | **DDL-1 en runtime** — correr contra una dimensión vacía, con y sin sembrado | `06-contrato-ddl.md` DDL-1, D47 | V1 |

> `04-verificacion.md` fija un tope de 3 reglas sin verificar simultáneas. **Está excedido a propósito desde 2026-07-30** y O1 lo excede más. Registrado, no silencioso — pero es deuda que se cobra sola en la primera corrida que falle por causa ambigua.

---

## Trabajo decidido, sin ejecutar

| # | Qué | Detalle en | Por qué se congela |
|---|---|---|---|
| T1 | **Emisión del anti-join + `Union` de miembro inferido** (D21) — diseño cerrado, código pendiente | `03-plan.md` § Pendientes de F4, D21 | Superficie nueva de generación; no toca el crash |
| T2 | **H28(a)** — agregar `("Constant", "fields", "field", "name", "type")` a `FIELD_TYPE_SOURCES` (`error_catalog_checks.py`; `03-plan.md` la cita en `:305-317`, hoy está en `:330`). Fix de una línea | `03-plan.md` § Pendientes de F4 | Trivial, pero sin relación con O1/O2. Candidato a colar si se toca ese archivo |
| T3 | **H28(b)** — barrer los ~12 step types que declaran `type`/`value_type` por campo, confirmar si `Constant` era el único hueco | `03-plan.md` § Pendientes de F4 | Depende de T2 |
| T4 | **Tipos en el validador de contrato entre KTR** (D38 punto 3). Hoy solo compara nombres | `03-plan.md` § Pendientes de F4 | Marcado "mejora, no riesgo", sin caso real que lo pida |
| T5 | **Investigar Data Validator (PDI)** — cubriría lo que `validate_business_rules()` iba a intentar (D39). Sin nombre de plugin ni alcance todavía | `03-plan.md` § Pendientes de F4, D39 | Investigación abierta, sin dueño |
| T6 | **Migración de los 34 tests** a `unit/`/`integration/`/`manual/` (D26). Sin `conftest.py` en `backend/tests/` hoy — mover sin agregarlo rompe la colección en silencio | `03-plan.md` § Backlog, D26 | Barato, pero toca la suite justo cuando O1 la necesita estable |
| T7 | **Reforzar el prompt** en `_format_dim_contracts` para que el listado de atributos no se confunda con columnas del hecho | `diagnostico-fk-categoria...md` candidato 2 | Cambio de prompt sin corrida que lo verifique — agrava V1 |
| T8 | **Partir `etl_generator.py`** (1188 líneas, +400 en el diff actual) | `arquitectura-objetivo.md` fila `etl_generator.py` | Alto riesgo a días de entregar. Ver `20-arquitectura.md` |
| T9 | **`services/` importando SQLAlchemy y `HTTPException` directo** (9 archivos, R3) | `arquitectura-objetivo.md` fila `services/` | Deuda extendida, sin relación con el crash |
| T10 | **R10 forma positiva — `EtlDraft` inmutable** a través del pipeline | `arquitectura-objetivo.md` R10 | `EtlDraft` no existe; es un objetivo propio |
| T11 | **`warnings: list[str]` → `Notification`/`Finding`** en los ~7 call sites que quedan | `arquitectura-objetivo.md` R12 | O1 paga la parte que toca; el resto funciona |
| T12 | **Reestructurar la celda de F4 de `ESTADO.md`** (~8000 caracteres en una fila) | `00-higiene-repo.md` H-O0-3 | O0 corrige la frase desfasada; partir el archivo es otra cosa |

---

## Auditorías de Track A

Congeladas en bloque. El motivo está en [`20-arquitectura.md`](20-arquitectura.md) § "Por qué las auditorías de Track A quedan congeladas" — resumen: correr otra auditoría antes de mecanizar lo ya encontrado reproduce el patrón que hizo fallar a las tres anteriores.

| # | Qué | Salida esperada |
|---|---|---|
| A1 | Doc vs. realidad, backend completo | `docs/auditoria/01-doc-vs-real.md` |
| A2 | Cumplimiento por capas | `docs/auditoria/02-cumplimiento.md` |
| A3 | Bordes de entrada, partes B/C/D (filas de DB, uploads, config de usuario, env vars) | `docs/auditoria/03-bordes.md` |
| A4 | Acoplamiento — cubre H5 | `docs/auditoria/04-acoplamiento.md` |
| A5 | Plan de remediación | `docs/auditoria/05-plan.md` |
| A7 | Ejecución, un PASO por sesión | — |

`A0` y `A0.5` están cerradas. `A6` (consolidar doctrina) quedó ejecutada parcial y fuera de secuencia por D27 — el criterio de capas ya vive en `CLAUDE.md`.

---

## Decisiones de producto sin tomar

Ninguna se puede resolver desde el código; todas necesitan que el usuario elija.

| # | Qué | Detalle en |
|---|---|---|
| C.1 | **Plan de variabilidad de dialecto SQL.** El DDL del DWH es Postgres-only sin excepción, aunque `sqlserver` sea motor real de *conexión* (H52). Inventario de puntos de dialecto ya escrito, para no arrancar de cero | `02-decisiones.md` § Abiertos C.1, H52, `plan-reparacion-etl.md` § MATERIAL PARA SESIÓN D |
| C.4 | **Auditoría retroactiva** de cambios no declarados en commits pasados de generación de KTR. Falta acotar hasta qué commit | `02-decisiones.md` § Abiertos C.4 |
| C.5 | **¿El backend emite/recomienda constraints DDL?** Hoy `dwh_ddl` es input, nunca output. Camino barato disponible sin abrir superficie: usar `advertencias_buenas_practicas` | `02-decisiones.md` § Abiertos C.5 |
| C.7 | **`ConnectionsMapRequest` no acepta `connection_id` string** para `conn_dwh`/`conn_staging`. Produce 6 tests rojos permanentes, ya contados como ruido conocido | `02-decisiones.md` § Abiertos C.7, H24 |
| C.8 | **`_CRITICAL_FIELDS["GetSystemInfo"]`** vuelve inalcanzable su propio fallback | `02-decisiones.md` § Abiertos C.8, H25 |
| C.11b | **`schema` obligatorio end-to-end** (multi-schema completo). C.11a cerrada por D49 | `ESTADO.md` F4, D49 |
| J1 | **Costo/beneficio de los JSON Schemas de salida del LLM** (`string` vs `object` por campo, revisita de D18). Es la causa raíz de que el nombre de clave `table` no se pueda forzar por schema. Encargo completo ya redactado — necesita spike empírico, no se decide de escritorio | `docs/costo/beneficio de JSON Schemas.md`, H29/D40 |

---

## Fuera de alcance del proyecto

No es congelado — es descartado, y se lista para que nadie lo reabra por error.

| Qué | Desde |
|---|---|
| **Superset** (`services/superset_client/`, `superset_export/`, `frontend/src/utils/supersetExport.js`). La conexión real al DWH se configura a mano en Superset | D28. Solo se corrigen gates rotos que dependan de él en código que sí está en alcance |
| **`kettle_crypto.py`** — ofuscación reversible del formato Kettle. Sin nada propio que ofuscar (el password sale siempre vacío o como `${VAR}`), el módulo se removió. El algoritmo queda en el historial de git | `CLAUDE.md` § Credenciales de conexión |
| **DDL-2 residual** — el mecanismo de calendario sigue siendo `DBLookup` (exact-match). El riesgo solo se materializa si un diseño futuro lo reemplaza por `Dimension lookup/update`; la guía de K18 ya está lista para esa transición | `06-contrato-ddl.md` DDL-2, D51 |
