# O0 — Higiene de repo

**Mutable.** Lo escribe quien ejecuta el objetivo. Entrada: [`docs/README.md`](../README.md).

**Por qué es objetivo y no tarea suelta:** hoy no se puede responder "¿qué cambió?" desde git. Eso ya causó un error concreto — la sesión D0 clasificó mal cinco ítems por leer un documento de estado en vez del código. O1 y O2 son verificables solo si el diff es legible.

**Alcance:** nada de lógica. Solo que el estado real del repo sea visible.

---

## H-O0-1 — El 92% del `git status` es ruido de fin de línea

**Evidencia (2026-08-03):**

```
git status --short | grep -c '^ M'      → 271
git diff --ignore-all-space --stat      → 22 files changed
git config core.autocrlf                → false
ls .gitattributes                       → no existe
file backend/app/core/auth.py           → "with CRLF line terminators"
git show HEAD:backend/app/core/auth.py  → sin CRLF
```

El working tree pasó a CRLF; `HEAD` está en LF. Con `core.autocrlf=false` y sin `.gitattributes`, git ve **cada archivo como reescrito entero**. 249 de los 271 son churn puro.

**Consecuencia si se commitea así:** 249 archivos de ruido entran al historial. `git blame` y `git log -p` quedan inservibles para todo lo anterior a ese commit — de forma permanente, y justo sobre el código que O1 y O2 van a tocar.

**Los 22 con cambio real** (`git diff --ignore-all-space --stat`): `domain/scd.py`, `routers/ai.py`, `services/ddl_validation.py`, `services/etl_generator.py`, `ktr_builder/contracts.py`, `dimension_step_policy.py`, `fields_validate.py`, `steps/lookups.py`, `steps/transform.py`, `validators/__init__.py`, `validators/base.py`, `validators/check_constraint_filter.py`, `validators/dimension_lookup_fields.py`, `validators/guard_staging_layer.py`, `prompts/system_inference.txt`, `tests/test_dimension_step_policy.py`, y 6 de docs/frontend.

**Fix:** `.gitattributes` con normalización explícita + `git add --renormalize .` en un commit propio, separado y titulado como tal. Nada de lógica en ese commit.

---

## H-O0-2 — El árbol trackeado está roto para cualquier otro clon

**Evidencia (2026-08-03):**

`backend/app/services/ktr_builder/validators/__init__.py` está trackeado y **modificado** para importar dos módulos que están **untracked**:

```python
from app.services.ktr_builder.validators.narration_crosscheck import (...)
from app.services.ktr_builder.validators.monetary_scale import (...)
```

Los dos figuran en `PRE_EMIT_PASSES`. Ninguno de los dos archivos está en git.

**Consecuencia:** un commit que suba el `__init__.py` sin ellos produce `ImportError` al importar el paquete de validators — y ese paquete lo importa `build.py`, así que `build_ktr()` deja de funcionar por completo para todo el que haga pull.

**Untracked completos:**

| Archivo | Qué es |
|---|---|
| `backend/app/services/ktr_builder/validators/monetary_scale.py` | Ítem 8 de D55. **Cableado en `PRE_EMIT_PASSES`** |
| `backend/app/services/ktr_builder/validators/narration_crosscheck.py` | Ítem 5 de D55. **Cableado en `PRE_EMIT_PASSES`** |
| `backend/tests/test_build_ktr_emission.py` | Ítem 3 de D55 — la suite que genera en vez de consumir el golden |
| `backend/tests/test_dimension_field_repair.py` | Tests del repair de la serie fk-categoria |
| `docs/refactor/plan-reparacion-etl.md` | Plan de los 8 ítems, con 7 revisiones |
| `docs/refactor/diagnostico-fk-categoria-loader-faltante.md` | Insumo directo de O1 |
| `docs/refactor/fase4_manual/` | Corpus de corridas reales |
| `docs/SCD/` | `SCD1.md`, `SCD2.md`, `criterios.md` |

**Fix:** commitear los untracked **antes** que cualquier otra cosa. Es el único ítem de O0 con riesgo de romper a un tercero hoy mismo.

---

## H-O0-3 — `ESTADO.md` se desfasó del código y nadie lo detectó

**Evidencia:** `ESTADO.md` (escrito 2026-08-01 19:09) cierra la celda de F4 con *"Ítems 4-8 [...] siguen planificados, no ejecutados"*. Verificado contra el código el 2026-08-03: los cinco están implementados.

| Ítem D55 | `ESTADO.md` decía | Realidad |
|---|---|---|
| 4 — semilla `tk=0` | no ejecutado | `ddl_validation.py:161` `synthesize_missing_seed_rows`, cableada en `etl_generator.py:1601` y `:1899` |
| 5 — narración↔XML | no ejecutado | `validators/narration_crosscheck.py`, en `PRE_EMIT_PASSES` |
| 6 — `check_constraint_filter` bound real | no ejecutado | `validators/check_constraint_filter.py`, +62 líneas |
| 7 — `guard_staging_layer` proyección SQL | no ejecutado | `validators/guard_staging_layer.py:58` `_sql_projection_has_business_logic`, con `sqlglot` |
| 8 — escala monetaria | no ejecutado | `validators/monetary_scale.py`; `min_year`/`max_year` en `steps/lookups.py:70-71` |

**Causa mecánica:** el código de los ítems 6, 7 y 8 es de las 22:04, 22:23 y 22:30 del **mismo día** en que se escribió esa línea. El documento no se reabrió al cerrar la sesión de código.

**Fix (mínimo, sin partir el archivo):** corregir esa frase y agregar arriba de la tabla de `ESTADO.md` un puntero a `docs/README.md` con la Regla A. La reestructuración de la celda de F4 queda congelada — ver [`90-congelado.md`](90-congelado.md).

---

## Criterio de terminado

1. Los untracked de H-O0-2 están commiteados, y `python -c "import app.services.ktr_builder.validators"` funciona en un clon limpio.
2. Existe `.gitattributes`; `git status --short | grep -c '^ M'` y `git diff --ignore-all-space --stat` dan el mismo número.
3. La renormalización está en un commit propio que no toca lógica.
4. La frase desfasada de `ESTADO.md` está corregida y el puntero a `docs/README.md` agregado.
5. `pytest backend/tests/` corrido y su resultado anotado acá — hoy la última cifra registrada es 45 fallos preexistentes (servidor no vivo / cuota Gemini / 1 test ya roto de antes). Si el número cambió, se investiga antes de abrir O1.

**Orden:** 1 → 2 → 3 → 4 → 5. El punto 1 primero porque es el único con daño activo.

**Nota sobre el punto 5:** la suite no se pudo correr al escribir este documento — el `venv/` del repo es de Windows y no es reutilizable desde otro entorno. Es la primera verificación real de O0.
