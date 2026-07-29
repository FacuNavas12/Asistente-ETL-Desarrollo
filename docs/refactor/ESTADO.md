# Estado — Refactor de fragmentación

**Mutable.** Única fuente de estado de fase de todo el refactor — ver regla 1 en `CLAUDE.md`. Se reescribe en el mismo turno en que una fase cambia de estado. Ningún otro archivo repite estado de fase; si necesitan mencionarlo, citan este archivo.

Vocabulario cerrado: `pendiente` / `en curso` / `cerrada` / `bloqueada por <qué>`.

| Fase | Estado | Qué falta exactamente | Detalle en |
|---|---|---|---|
| A0 — Inventario | cerrada (2026-07-25) | — | `docs/auditoria/00-inventario.md` |
| A0.5 — Fallos silenciosos | cerrada (2026-07-25) | — (derivó H29, sin dueño de track) | `docs/auditoria/00b-fallos-silenciosos.md`, D25 |
| A1 — Doc vs. realidad | pendiente | Todo | `03-plan.md` tabla Track A |
| A2 — Cumplimiento por capas | pendiente | Todo | `03-plan.md` tabla Track A |
| A3 — Bordes de entrada | pendiente | Todo | `03-plan.md` tabla Track A |
| A4 — Acoplamiento | pendiente | Todo | `03-plan.md` tabla Track A |
| A5 — Plan de remediación | pendiente | Todo | `03-plan.md` tabla Track A |
| A6 — Consolidar doctrina | en curso | Falta formalizar tras A1-A5 (auditoría completa, todavía pendientes abajo). Doctrina base escrita 2026-07-27 fuera de secuencia (mapa capa↔directorio, regla de migración, R10 forma positiva + R12, ajuste a R11, sobre-especificación de `ports/`, test de arquitectura AST, READMEs por carpeta) y ampliada el mismo día (D27): `backend/app/domain/` existe físicamente por primera vez (`canonical_types.py`), `registry.py` partido en `step_types.py`/`step_emitters.py`, `KNOWN_PDI_STEP_TYPES` borrado (H30), criterio "vocabulario PDI es dominio" fijado en `CLAUDE.md`. Ver `docs/arquitectura-objetivo.md`, `backend/tests/test_architecture_layers.py`, `backend/tests/test_pdi_step_coherence.py`, D27 en `02-decisiones.md` | `docs/arquitectura-objetivo.md`, D27 |
| A7 — Ejecución | pendiente | Todo | `03-plan.md` tabla Track A |
| F1 — Investigar | cerrada (2026-07-22) | — | `03b-reportes.md#reporte-f1` |
| C.2 — Reglas de corte vs. D6-bis | cerrada (2026-07-22) | — | C.2 en `02-decisiones.md` |
| F1.5 — Dominio mínimo del corte | cerrada en código (2026-07-24) | — | H4/H6/H11 en `01-hallazgos.md` |
| F2 — Diseñar el corte | cerrada, aprobada por usuario (2026-07-23, D17) | — | `03b-reportes.md#reporte-f2` |
| F2.5 — Soporte `JobEntryJob` | cerrada en código (2026-07-24) | — | H7 en `01-hallazgos.md` |
| F3 — Implementar el corte | cerrada (2026-07-27) | — | `03b-reportes.md#estado-f3`, D19/D20/D28 en `02-decisiones.md` |
| F4 — Track de errores | en curso | Validador de contrato entre KTR (D23, ejecutado por D38 — nombres; tipos queda gap documentado, no implementado); `validate_business_rules()` removido sin reemplazo en backend, responsabilidad a DDL + Data Validator (PDI) por investigar (D39); progreso observable + checkpoint por etapa del job async (D29-D33, ejecutado); resolución de conexiones sin abortar + mapa por-ETL (D34-D36, ejecutado); criterio determinista SCD1/SCD2 (D37, ejecutado, `domain/scd.py`, verificado por test suite — falta correr un ETL real end-to-end con `uvicorn`+frontend para confirmar que el criterio resuelve en la práctica el tipo de caso que lo motivó: error de KTR y falla de DDL por decisión SCD divergente entre etapas, sin casos formales todavía escritos); H29 recuperación de `table` por contenido (D40, ejecutado, `ktr_builder/validators/` — cerrado parcial, el patrón `if not table: continue` en sí sigue triplicado, ver H29 en `01-hallazgos.md`); ver `04-verificacion.md` para lo pendiente de re-correr | D21-D23, D29-D40 en `02-decisiones.md` |
| F5 — Limpieza de bajo costo | cerrada en código (2026-07-25) | — | H12 en `01-hallazgos.md` |
