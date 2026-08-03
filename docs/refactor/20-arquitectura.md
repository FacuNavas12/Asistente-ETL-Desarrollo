# O2 — Arquitectura de capas

**Mutable.** Lo escribe quien ejecuta el objetivo. Entrada: [`docs/README.md`](../README.md).

**Fuente de verdad:** [`docs/arquitectura-objetivo.md`](../arquitectura-objetivo.md) — capas, R1-R12, mapa capa↔directorio, regla de migración. Este archivo **no la repite**: dice qué se paga, en qué orden, y con qué prompt se abre cada sesión.

---

## Qué es y qué NO es este objetivo

O2 responde **una sola pregunta: dónde vive cada cosa.** Capas, dependencias hacia adentro, una representación por concepto, un canal de notificación tipado.

O2 **no** responde qué decide el sistema. Si el config de un loader de dimensión se sintetiza en Python o se le pide al modelo es una pregunta de otra naturaleza — y es la que corta la cascada de errores. Vive en [`30-decision-python-llm.md`](30-decision-python-llm.md).

Confundirlas cuesta caro: mover `dimension_step_policy.py` a `domain/` no cambia una sola de las cinco estaciones donde hoy se decide la semántica de una dimensión. Es trabajo correcto que no resuelve el problema que duele.

**Regla de migración vigente** (`arquitectura-objetivo.md`): código nuevo nace en su capa; código existente se mueve **solo cuando ya se lo va a tocar por otra razón**. O2 no abre sesiones cuyo único fin sea mover archivos — abre sesiones donde el movimiento viene pegado a un fix que igual había que hacer.

**Verificación continua:** `backend/tests/test_architecture_layers.py` corre en modo "no empeorar". Falla ante una violación **nueva** de R1/R3/R4 en su recorte. Las existentes viven en las listas `FROZEN_*`, que **solo pueden achicarse** — cuando un archivo se corrige, su entrada congelada se borra en el mismo cambio, y el propio test verifica que no queden entradas que ya no reproducen.

---

## Las tres sesiones de O2

Cada una es autónoma, chica, y termina verde. Ninguna depende de las otras. Se pueden intercalar entre las sesiones de O1 sin romper nada.

### O2-a — Partir `common.py`

**Por qué ahora:** O1 toca `KtrBuilderError` en los cuatro sitios de aborto. El archivo se abre igual.

**Qué:** `common.py` es una fila **partido** del mapa. `_yn` y `KtrBuilderError` son puros → `domain/`. `_sub` arma un `xml.etree.Element` → infraestructura. Mismo archivo, dos capas, sin que el nombre lo avise.

**Prompt:**

> Leé `docs/README.md`, `docs/refactor/20-arquitectura.md` y la fila `common.py` del mapa de `docs/arquitectura-objetivo.md`. Partí `services/ktr_builder/common.py` según esa fila: `_yn` y `KtrBuilderError` a `domain/`, `_sub` queda del lado de emisión XML. Actualizá todos los imports. Marcá la fila del mapa como ejecutada con la misma convención que usan `domain/canonical_types.py` y `step_types.py`. Si alguna entrada de `FROZEN_*` en `test_architecture_layers.py` deja de reproducir, borrala en este mismo cambio.

**Terminado:** el mapa dice ejecutado, la suite verde, `FROZEN_*` igual o más chica.

### O2-b — `resolve_step_table()` en `domain/` (T1)

**Por qué ahora:** es la deuda transversal registrada más vieja, y O1 va a tocar `dimension_step_policy.py`, uno de los tres call sites.

**Qué:** el mismo `if not table: continue` sin notificar, reimplementado por separado en `fragmentation.build_rw_matrix`, `dimension_step_policy.enforce_dimension_step_policy` y `fields_validate.validate_dimension_lookup_races`. Los tres responden la misma pregunta y descartan el caso vacío cada uno a su manera. Detalle en `05-transversales.md` § T1 — **sus números de línea están corridos, ver la nota al pie de este archivo.**

Bajo R12, una sola `resolve_step_table(step) -> (tabla | None, Notification | None)` reemplaza a los tres: devuelve la notificación en vez de tragarla.

**Cuidado, ya documentado:** D40 (`table_key_recovery.py`) atendió parcialmente esto adelantando la resolución de la causa, pero **no unificó la reacción** — los tres `continue` siguen intactos. Esta sesión hace lo que D40 no hizo, no lo repite.

**Prompt:**

> Leé `docs/README.md`, `docs/refactor/20-arquitectura.md` y `docs/refactor/05-transversales.md` § T1. Creá `resolve_step_table()` en `domain/` según R12 de `arquitectura-objetivo.md` y hacé que los tres call sites la usen, devolviendo notificación en vez de descartar en silencio. Los números de línea de T1 están corridos — ubicá por símbolo. No toques `table_key_recovery.py`: resuelve la causa antes, no la reacción. Actualizá el `**Estado:**` de T1 y escribí la D-N.

**Terminado:** un solo lugar responde "¿qué tabla toca este step?". Los tres `continue` mudos ya no existen.

### O2-c — Partir `lineage_builder.py`

**Por qué ahora:** es la última fila **partido** barata del mapa. `etl_generator.py` también está partido pero queda congelado — 1188 líneas y el diff actual le suma 400; partirlo a días de entregar es riesgo sin retorno.

**Qué:** `build_lineage`, `stitch_lineage_many` y `stitch_lineage` son puros sobre el dict KTR → `domain/`. `_parse_ktr_xml` lee XML ya serializado → infraestructura.

**Prompt:**

> Leé `docs/README.md`, `docs/refactor/20-arquitectura.md` y la fila `lineage_builder.py` del mapa de `docs/arquitectura-objetivo.md`. Partilo según esa fila. Marcá la fila como ejecutada. No toques `etl_generator.py` — está congelado, ver `90-congelado.md` T8.

**Terminado:** el mapa dice ejecutado, la suite verde.

---

## Lo que O2 NO hace antes de entregar

| Qué | Por qué |
|---|---|
| Mudar `ktr_builder/` entero a `infrastructure/pentaho/` + `domain/` | Es la migración grande. La regla de migración la prohíbe como sesión propia, y no arregla ningún error |
| Partir `etl_generator.py` | 1188 líneas, +400 en el diff actual. Alto riesgo, cero retorno inmediato — `90-congelado.md` T8 |
| Sacar SQLAlchemy y `HTTPException` de `services/` (R3) | 9 archivos, deuda extendida, sin relación con ningún error abierto — `90-congelado.md` T9 |
| `ports/` físico | `arquitectura-objetivo.md` ya dice que se justifican pero les toca "cuando alguien los toque" |
| R10 forma positiva — `EtlDraft` inmutable | No existe; diseñarlo es un objetivo propio — `90-congelado.md` T10 |
| Auditorías A1-A5, A7 | Ver sección siguiente |

---

## Por qué las auditorías de Track A quedan congeladas

`03-plan.md` las propone como prerrequisito. No se corren, y el motivo no es de tiempo.

D0 encontró que los tres hallazgos estructurales del último ciclo **ya estaban previstos** en doctrina escrita antes:

- **D5/R11** existía antes del ciclo, y `00b-fallos-silenciosos.md` ya la había usado para encontrar el mismo tipo de defecto — pero el radar era grep manual y no alcanzó a `validators/`, creado después.
- **`parse_cfg` fail-fast** fijó el precedente que después hubo que redescubrir para `guard_staging_layer.py`.
- **D26** apuntó a "verde no confiable" y nunca llegó a "un test debe comparar contra la salida real de `build_ktr()`".

Los tres son el mismo meta-defecto: **el principio quedó escrito como documento, no como check ejecutable.** Correr otra auditoría antes de mecanizar lo ya encontrado reproduce ese patrón exacto. Las tres sesiones de arriba mecanizan; las auditorías esperan.

---

## Criterio de terminado de O2

1. O2-a, O2-b y O2-c ejecutadas, cada una con su D-N.
2. `test_architecture_layers.py` verde y las listas `FROZEN_*` más chicas que al empezar — nunca más grandes.
3. Ningún archivo nuevo nació fuera de su capa. En particular: un checker de reglas puras nace en `domain/`, no en `services/`.
4. Cada fila del mapa que se movió está marcada como ejecutada en `arquitectura-objetivo.md`.

El indicador real lo fija `arquitectura-objetivo.md`: **si escribir el test es fácil, la arquitectura quedó bien.** No el diagrama.

---

> **Nota — las líneas citadas en documentos viejos están corridas.** Verificado 2026-08-03: las tres que da `05-transversales.md` § T1 no apuntan a ese código (`fragmentation.py:79` es un comentario, `dimension_step_policy.py:156` una firma, `fields_validate.py:418` otro `if`). Lo mismo con `error_catalog_checks.py:305-317` en `03-plan.md`, hoy `:330`. Los hallazgos son válidos; lo corrido es la cita. **Convención: se cita símbolo, no línea.**
