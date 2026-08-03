# Transversales — hallazgos cuyo fix vive en otro lugar que el síntoma

**Append-only**, mismo criterio que `01-hallazgos.md`/`02-decisiones.md`: una entrada se agrega, no se reescribe; si su estado cambia, se edita solo la línea `**Estado:**`.

Un hallazgo transversal es uno cuyo fix vive en un lugar distinto de donde aparece el síntoma, y/o que aparece en N≥2 módulos. Prioridad más alta que un hallazgo puntual: el costo de arreglarlo una vez es casi el mismo que arreglarlo en un solo sitio, pero el valor es N — más el sitio N+1 que todavía no existe. Es evidencia de una abstracción faltante, insumo directo de A2/A3/A4 (Track A) cuando corran.

---

## T1 — `if not table: continue` sin notificar, duplicado en 3 módulos

**Síntomas:**
- `backend/app/services/ktr_builder/fragmentation.py:79-80` (`build_rw_matrix`)
- `backend/app/services/ktr_builder/dimension_step_policy.py:156-160` (`enforce_dimension_step_policy`)
- `backend/app/services/ktr_builder/fields_validate.py:418-425` (`validate_dimension_lookup_races`)

**Abstracción faltante:** una sola `resolve_step_table(step) -> (tabla | None, Notification | None)` en `domain/`, que devuelva la notificación en vez de que cada caller decida (o no decida) qué hacer cuando la tabla no resuelve.

**Capa donde debería vivir:** `domain/` según `docs/arquitectura-objetivo.md` (R12) — hoy no existe esa carpeta, el código vive en `backend/app/services/ktr_builder/`; la función centralizada aterriza ahí mientras Track A no migre la estructura.

**Fases que toca:** F3 (dueño natural de `fragmentation.py`, mismo mecanismo de `notifications` que ya usa `compute_cut()`), F4 (`dimension_step_policy.py`), A3/A4 (Track A, cuando auditen bordes/acoplamiento).

**Costo:** arreglarlo una vez en `resolve_step_table()` cubre los 3 sitios actuales + cualquier módulo nuevo que resuelva step→tabla; arreglarlo 3 veces (el estado actual) ya dejó a `fragmentation.py` contradiciendo su propio docstring (D15 promete "notifica", no lo hace — ver H29).

**Estado:** cerrado, 2026-08-03 (D62, `02-decisiones.md`, O2-b). `resolve_step_table(step_name, table_raw) -> (tabla | None, mensaje | None)` nueva en `domain/step_table.py` (sin imports de proyecto — devolver `Finding` cerraba un ciclo real con `fragmentation.py` vía `validators/__init__.py`, ver D62). Los 3 call sites la usan; cada uno reordenado para llamarla solo cuando el step ya es relevante (rol R/W en `fragmentation.py`, `DIMENSION_STEP_TYPES` en `dimension_step_policy.py`, el filtro de canonical ya existente en `fields_validate.py`) — un step sin tabla que legítimamente no la necesita (`Sort`, `FilterRows`...) sigue sin notificar; uno que sí la necesita y no la resuelve, ahora sí. `table_key_recovery.py` (D40) no se tocó — sigue adelantando la causa, esta entrada cierra la reacción que quedaba pendiente.
