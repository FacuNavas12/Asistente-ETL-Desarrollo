# Fase 4 — corridas manuales (parcial)

**Por qué parcial:** sin crédito Gemini al momento de correr — Fase 4 pedía 2+ modelos
(el que produjo Set A y el que produjo Set B, S-12 en `03c-investigacion-vocabulario-dimension-kettle.md`).
Sustituto: Sonnet vs Haiku (Anthropic), swap manual de `ANTHROPIC_MODEL` en `.env` entre corridas.
Riesgo aceptado: no prueba invariancia entre proveedores, solo entre modelos del mismo proveedor.
Ver decisión en `02-decisiones.md` [completar número D].

**Fecha inicio:** [completar]
**Caso de entrada usado (mismo en todas las corridas):** [completar — ej. catálogo de productos, mismo DDL/CSV que Set A/B]
**LLM_PROVIDER:** anthropic

---

## Checklist por corrida

- [ ] Correr hasta que el ETL quede confirmado/guardado (visible en Home)
- [ ] Home → exportar ETL completo (`downloadEtlFull`, incluye `result`: etapas, validaciones, advertencias, kjb_master, lineage — TODO lo necesario para el análisis)
- [ ] Renombrar el archivo bajado a `<modelo>-<NN>.json` (ej. `sonnet-01.json`, `haiku-02.json`) — el modelo va en el nombre, no hace falta anotarlo aparte
- [ ] Guardar todos los archivos de una tanda (mismo modelo) juntos; no hace falta subcarpeta por corrida

No hace falta `resumen.txt` ni `validaciones.md` manuales — `scd_type` por dimensión, si el corte dio 2 archivos, y los findings (`validaciones`/`advertencias_buenas_practicas`) ya están todos dentro del JSON de `downloadEtlFull`. Se extraen del archivo al analizar, no a mano.

## Qué NO se está midiendo en esta corrida parcial

- Conteos leídos/escritos por step contra DB real (S-11) — necesita ejecución en Spoon, fuera de este mínimo.
- Invariancia cross-proveedor (Gemini) — bloqueada por crédito, backlog.

## Observaciones libres

[acá anotar cualquier cosa rara corrida por corrida — no estructurado, para no perder señal por forzar formato]
