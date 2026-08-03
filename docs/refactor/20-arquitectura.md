# O2 — Aplicar la arquitectura objetivo

**Mutable.** Lo escribe quien ejecuta el objetivo. Entrada: [`docs/README.md`](../README.md).

**Prioridad 2.** Fuente de verdad: [`docs/arquitectura-objetivo.md`](../arquitectura-objetivo.md) — capas, R1-R12, mapa capa↔directorio, regla de migración. Este archivo **no la repite**: dice qué se paga ahora y qué no.

---

## La regla que hace que esto no sea una reorganización

De `arquitectura-objetivo.md`, sección "Regla de migración":

> **Código nuevo nace en su capa objetivo.** Código existente se mueve **solo cuando ya se lo va a tocar por otra razón**. Nunca hay una sesión cuyo único objetivo es mover archivos.

**Consecuencia operativa a días de entregar:** O2 no abre sesiones de mudanza. O2 es la regla que se aplica **mientras se ejecuta O1**. Cada archivo que O1 toca se lleva su entrada de deuda al día en el mismo cambio; los que O1 no toca, no se mueven.

El test `backend/tests/test_architecture_layers.py` corre en modo "no empeorar": falla ante una violación **nueva** de R1/R3/R4 en su recorte, no por las que ya existen. Esas viven en las listas `FROZEN_*`, que **solo pueden achicarse** — cuando un archivo se corrige, su entrada congelada se borra en ese mismo cambio. El propio test verifica que no queden entradas que ya no reproducen (`test_frozen_lists_have_no_stale_entries`).

---

## Por qué las auditorías de Track A quedan congeladas

`03-plan.md` propone A1-A5 y A7 — auditorías de doc-vs-realidad, cumplimiento de capas, bordes, acoplamiento — como prerrequisito. **No se corren antes de entregar**, y el motivo no es solo de tiempo.

La sesión D0 encontró que los tres hallazgos estructurales del último ciclo **ya estaban previstos** en doctrina escrita antes:

- **D5/R11** ("prohibido el fallo silencioso") existía antes del ciclo, y `00b-fallos-silenciosos.md` ya la había usado para encontrar el mismo tipo de defecto. Pero el mecanismo de detección era grep manual, y no alcanzó a `validators/` — código creado después. *La doctrina estaba; el radar no cubría código que todavía no existía.*
- **`parse_cfg` fail-fast** (F1.5/H6) fijó el precedente exacto que después hubo que redescubrir para `guard_staging_layer.py`.
- **D26** apuntó a "verde no confiable" pero nunca llegó a "un test debe comparar contra la salida real de `build_ktr()`".

Los tres son el mismo meta-defecto: **el principio quedó escrito como documento, no como check ejecutable.** Correr otra auditoría antes de mecanizar lo ya encontrado reproduce exactamente ese patrón. Por eso O2 mecaniza, y las auditorías esperan.

---

## Deuda registrada — qué se paga y cuándo

Todo lo de esta tabla ya está documentado en otro lado; acá está el ruteo y la decisión de si entra ahora.

| Deuda | Dónde está documentada | Regla | ¿Ahora? |
|---|---|---|---|
| **T1 — `if not table: continue` sin notificar, en 3 módulos** (`fragmentation.build_rw_matrix`, `dimension_step_policy.enforce_dimension_step_policy`, `fields_validate.validate_dimension_lookup_races`) | `05-transversales.md` § T1 — **sus líneas están corridas, ver nota abajo** | R12 | **Sí, si O1 toca alguno.** `dimension_step_policy.py` es casi seguro que sí |
| **`common.py` partido** — `_yn`/`KtrBuilderError` son domain, `_sub` arma XML (infra) | `arquitectura-objetivo.md`, fila `common.py` | R6 | **Sí.** O1 toca `KtrBuilderError` en los 4 sitios |
| **`VALUE_META_TYPE_NAMES` sin verificar contra fuente** | `plan-reparacion-etl.md` § 1 | R7 | **Sí — es el primer paso de O1** |
| `lineage_builder.py` partido — `build_lineage`/`stitch_*` son puros, `_parse_ktr_xml` es infra | `arquitectura-objetivo.md`, fila `lineage_builder.py` | R6 | Solo si O1 lo toca |
| `etl_generator.py` partido (1188 líneas y creciendo — el diff actual le suma 400) | `arquitectura-objetivo.md` + `backend/app/services/README.md` | R6 | **No.** Partirlo ahora es alto riesgo. Congelado |
| 9 archivos de `services/` importan SQLAlchemy directo; `etl_service.py`/`job_service.py` importan `HTTPException` | `arquitectura-objetivo.md`, fila `services/`, nota de debt | R3 | **No.** Deuda extendida, sin relación con el crash. Congelado |
| R10 forma positiva — `EtlDraft` inmutable a través del pipeline | `arquitectura-objetivo.md` R10 | R10 | **No.** `EtlDraft` no existe; diseñarlo ahora es un objetivo propio. Congelado |
| R12 — `Notification` como tipo de dominio en vez de `list[str]` | `arquitectura-objetivo.md` R12 | R12 | **Parcial.** `Finding` (`validators/base.py`) ya es la forma correcta. O1 la extiende a los 4 sitios; no se migra el resto |
| `ports/` físico (`LLMProvider`, `SchemaSource`) | `arquitectura-objetivo.md` § "Sobre-especificación" | — | **No.** El documento ya dice que se justifican pero les toca "cuando alguien los toque" |

> **Nota sobre las líneas citadas en documentos viejos.** Verificado 2026-08-03: las tres líneas que `05-transversales.md` § T1 da para los `if not table: continue` ya no apuntan a ese código (`fragmentation.py:79` es un comentario, `dimension_step_policy.py:156` es una firma, `fields_validate.py:418` es otro `if`). Lo mismo con `error_catalog_checks.py:305-317` en `03-plan.md`, hoy `:330`. El hallazgo sigue siendo válido — lo que se corrió es la cita. **Convención a partir de acá: se cita símbolo (`build_rw_matrix`), no línea.** El símbolo sobrevive a un `git pull`; el número no.

---

## El punto que O1 y O2 comparten

Los cuatro sitios de aborto de O1 son **también** el caso de prueba de R12. Hoy el pipeline mezcla tres canales para decir "algo salió mal": `raise KtrBuilderError`, `warnings: list[str]` con prefijos de string (`FIELD_INTEGRITY_PREFIX`, `PRE_EMIT_ERROR_PREFIX`, `DEAD_FIELD_PREFIX`...), y `Finding` en `validators/`.

`Finding` es el único de los tres que ya cumple R12: tipo, severidad, step afectado, y `repaired`. Cuando O1 convierta un aborto en entrega documentada, **el resultado se expresa como `Finding`, no como string con prefijo**. Eso es aplicar R12 sin una sesión de migración: la regla se paga en el código que igual había que tocar.

Lo que **no** entra: convertir los `warnings: list[str]` existentes. Son ~7 call sites y funcionan. Congelado.

---

## Criterio de terminado

O2 no tiene un estado "terminado" propio — es una restricción sobre cómo se ejecuta O1. Se considera cumplido si, al cerrar O1:

1. Ningún archivo que O1 tocó quedó con la deuda de arquitectura que ya tenía registrada, **cuando esa deuda estaba en la tabla de arriba marcada "Sí"**.
2. `test_architecture_layers.py` pasa, y las listas `FROZEN_*` **se achicaron** — nunca crecieron.
3. Ningún archivo nuevo nació fuera de su capa objetivo. En particular, un checker de reglas puras nace en `domain/`, no en `services/`.
4. Todo lo que se movió está anotado en la fila correspondiente del mapa de `arquitectura-objetivo.md` como ejecutado, con la misma convención que ya usan `domain/canonical_types.py` y `step_types.py`.
5. Las decisiones de ubicación que no sean obvias quedan escritas como D-N, con el criterio de `CLAUDE.md` § "Criterio de capas" citado.

El indicador real es el que ya fija `arquitectura-objetivo.md`: **si escribir el test es fácil, la arquitectura quedó bien.** No el diagrama.

---

## Riesgo declarado

La regla de migración es lo que hace a O2 seguro a días de entregar, y también su límite: si O1 termina tocando poco código, O2 paga poca deuda. **Eso es aceptable y es el diseño**, no un fracaso del objetivo. Lo contrario — mover archivos para cumplir una tabla — es exactamente lo que la regla prohíbe, y el modo de falla que produjo la cadena de errores que originó todo este refactor: aplicar un plan de arquitectura escrito para un estado del sistema que ya no existe.
