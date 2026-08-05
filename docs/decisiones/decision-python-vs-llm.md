# Dónde se decide: Python o el modelo

**Caso testigo implementado (D68), citado desde comentarios de código — falta corrida real end-to-end para darlo por cerrado.** Decide *qué resuelve el sistema solo y qué le pregunta al modelo* — distinto de qué capa aloja cada archivo (eso es `arquitectura-objetivo.md`). Un archivo puede estar en la capa correcta y seguir tomando una decisión que no le corresponde.

---

## El problema, con la cadena a la vista

Hoy, para una sola decisión — el tipo SCD de una dimensión y lo que implica para su step:

```
1. Python deriva scd_type              domain/scd.py
2. Python se lo cuenta al modelo       _format_dim_contracts → prompt
3. El modelo devuelve un step          puede contradecir el contrato
4. Python detecta la contradicción     dimension_step_policy, 8 validators
5. Python repara                       _repair_dimension_loader_fields (otra llamada al modelo)
6. Si el repair no alcanza, aborta     lookups.py, KtrBuilderError
```

**Seis estaciones para una decisión.** Cada vez que el modelo contradijo al contrato, la respuesta histórica fue agregar una estación más. Cada estación nueva es un lugar más donde vive la semántica y puede divergir de las otras cinco.

Eso no es mala suerte ni deuda acumulada: **es el motor de "arreglo un error y aparece otro".** Mientras la cadena tenga seis estaciones, un fix en cualquiera de ellas puede destapar una inconsistencia en otra.

Evidencia de que la cadena ya se rompe sola, encontrada en O0 (2026-08-03): `test_repair_dimension_loader_fields_floor_when_gate_fails` falla porque la estación 5 **acepta un `stream_field` que no existe en el stream** y degrada a `tipo="info"`. El "piso preservado" que documenta el diagnóstico de la serie fk-categoria no existe en el código.

---

## La pregunta que O3 responde

> ¿Qué parte de un `.ktr` puede derivar Python de forma determinista a partir de lo que ya tiene — `dim_contracts`, DDL del DWH, esquema canónico del origen, grafo de hops — y por lo tanto **no debería pedirle al modelo**?

Y la simétrica:

> ¿Qué requiere juicio real — mapeo origen→destino cuando los nombres no coinciden, expresiones de transformación, interpretación de reglas de negocio — y por lo tanto **sí** es trabajo del modelo?

Trazar esa línea una sola vez colapsa la cadena de seis a tres: **Python decide → el modelo completa lo que Python no puede derivar → Python verifica.** Sin estación de reparación, porque no hay nada que reparar cuando lo determinista nunca se preguntó.

---

## Por qué esto no es una idea nueva

El código ya se movió en esa dirección, sin nombrarlo:

- `_synthesize_dimension_lookup_config` (`dimension_step_policy.py`) **sintetiza** el config del step de dimensión desde el contrato, en vez de pedirlo.
- `synthesize_missing_seed_rows` (`ddl_validation.py`) sintetiza el INSERT semilla cuando el modelo no lo puso.
- `enforce_dimension_step_policy` invierte decisiones del modelo cuando contradicen el contrato.

O3 no inventa un patrón: **nombra el que ya está apareciendo solo, y decide hasta dónde llega.** Hoy cada síntesis se agregó como parche a un error puntual, sin un criterio general de qué se sintetiza y qué no — por eso conviven con cinco estaciones de verificación que existirían igual.

---

## Precondiciones — qué tiene que estar antes

1. **O1 cerrado.** No se rediseña qué decide el sistema mientras el sistema no entrega de forma estable.
2. **`referencia/scd.md`.** Qué es SCD1 y SCD2 en este producto, cuándo se aplica cada uno, qué implica para el step y para el DDL. Escrito — REF cerrada 2026-08-03. `docs/SCD/` (los 3 archivos que fusionó) borrado.
3. **`referencia/kettle-comportamiento.md`.** Destilado de `investigacion-tags-validos-por-step.md`: qué lee Kettle por step, qué vocabularios son condicionados, dónde están los centinelas que colisionan con valores válidos.
4. **`referencia/contrato-ddl.md`.** Qué garantiza el DDL, porque toda síntesis determinista depende de eso.

Sin las tres, O3 discute de memoria — y este proyecto ya tiene un caso registrado de qué pasa cuando se planifica sobre memoria en vez de sobre evidencia verificada.

---

## Decisiones que O3 tiene que tomar explícitamente

Caso testigo (decisión 1) resuelto e implementado end-to-end (sesión O3, 2026-08-04) — falta la D-N en `02-decisiones.md` (redactada por el usuario, contenido preparado por la sesión que cerró esto). Decisiones 2, 4 y 5 quedan resueltas como consecuencia directa de la 1. Decisión 3 sigue tal cual estaba — no se tocó.

| # | Decisión | Nota |
|---|---|---|
| 1 | ¿El step loader de dimensión se sintetiza completo, o se pide y se corrige? | **Resuelto: se sintetiza completo.** El modelo aporta topología (dónde va el step, sus hops) + `config.table` + `keys[].stream_field`/`fields[].stream_field` (el mapeo que no es derivable). Python sintetiza SIEMPRE, incondicional — no solo al detectar discrepancia — `update`/`return_field`/`date_from`/`date_to`/`version_field`/`fields[].type`, vía `build_dimension_lookup_config()` (`dimension_step_policy.py`), llamado desde `apply_dimension_contracts()` (reemplaza `enforce_dimension_step_policy`). Las estaciones 3-6 originales colapsan: no hay "el modelo puede contradecir" cuando no se le pide escribir eso, y no hay estación de reparación (`_repair_dimension_loader_fields` borrada) |
| 2 | ¿Qué entra en el prompt si el paso 1 sale "se sintetiza"? | **Resuelto.** `system_etl.txt` § "STEP DE DIMENSIONES" reescrito: pide 4 cosas (name+hops, table, keys, fields — sin `type`) y dice explícitamente qué NO poner. `_format_dim_contracts()` (`etl_generator.py`) pasó de 11 tokens por dimensión a 4 (`columnas_destino`, `natural_keys`, `campo_sk_en_stream`, `columna_vigencia`) |
| 3 | ¿Se ramifica por `scd_type` en la emisión? | **Sin tocar — D44 sigue vigente.** Vocabulario uniforme por rol, `DimensionLookup` para todo `scd_type`. La síntesis nueva no introduce ninguna rama por tipo |
| 4 | ¿Qué pasa cuando la síntesis no es posible por datos faltantes? | **Resuelto: notifica y entrega, nunca aborta.** Atributo sin homónimo en el stream → se omite de `fields` + finding `tipo=error`; grafo no resoluble → identidad sin verificar + finding `tipo=warning` cuando el rol además se forzó (D58). Coherente con D60 |
| 5 | ¿La verificación posterior sigue existiendo si lo determinista ya no se pregunta? | **Resuelto: sí, más chica.** `VERIFY_PASSES` (`validators/__init__.py`, subconjunto de `PRE_EMIT_PASSES`) corre en `_verify_emitted_ktr()` DESPUÉS de `apply_dimension_contracts()` — verifica lo que Python sintetizó (regresiones propias) y lo que el modelo aportó en tablas sin contrato, no compara contra un config que el modelo ya no escribe |

---

## Criterio de terminado

1. La línea escrita como D-N: qué se sintetiza, qué se pregunta, qué se verifica. **Hecho** — [D68](02-decisiones.md#d68).
2. Al menos el caso testigo (decisión 1) implementado end-to-end. **Hecho.** `build_dimension_lookup_config()`/`apply_dimension_contracts()` (`dimension_step_policy.py`), 4 call sites de `etl_generator.py` actualizados, `_repair_dimension_loader_fields`/`_dimension_repair_context`/`_deterministic_field_mapping` borradas (con ellas, E-21/E-23 se cierran por construcción, no por fix). Verificado contra el corpus real (`etl-llm-raw-test-01_sonnet_fase4.json`) que el caso `nombre_categoria`→`categoria` (prefijo) y el descarte de `fk_categoria`/`precio_lista`/`stock` (vocabulario cruzado) resuelven en la pasada principal, sin llamada extra al LLM.
3. Las estaciones que dejaron de tener sentido, borradas — no desactivadas ni marcadas como deprecated. **Hecho** — ver punto 2, más el discriminador D58 por contenido de `fields` (reemplazado por regla de conteo) y el finding `repairable`.
4. `system_etl.txt` sin la sección que dejó de tener destinatario. **Hecho** — § "STEP DE DIMENSIONES" reescrita (4 tokens que el modelo sigue necesitando, en vez de 11), checklist ítems 19/19b/23/24 acotados o borrados.
5. Una corrida real que muestre la cadena corta funcionando. **Parcial** — verificado con el corpus E-01 corrido en aislamiento contra `apply_dimension_contracts()` directo (no a través de `/generate-async`). Falta la corrida end-to-end (`/generate-async`→`/connections`→`/status`) con LLM real y cuota — `backend/.env` vacío a propósito en este entorno, queda para cuando el usuario la corra.

**El indicador:** si después de O3 sigue habiendo una estación de reparación para el mismo dato que Python ya podía derivar, la línea se trazó mal. **No la hay** — la única estación de reparación que existía para esto (`_repair_dimension_loader_fields`) está borrada.

---

## Qué NO es O3

- No es reescribir el pipeline. Es decidir qué se pregunta.
- No es sacar al modelo del flujo. El modelo sigue haciendo lo que requiere juicio.
- No es la migración de capas — eso es [O2](20-arquitectura.md), y es independiente.
