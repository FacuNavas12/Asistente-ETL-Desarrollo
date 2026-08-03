# O3 — Dónde se decide: Python o el modelo

**Mutable.** Lo escribe quien ejecuta el objetivo. Entrada: [`docs/README.md`](../README.md).

**Prioridad 3.** Bloqueado por O1 (el sistema tiene que entregar de forma estable antes de rediseñar qué decide) y por la escritura de `referencia/` (sin eso la discusión vuelve a ser de memoria).

**Distinto de [O2](20-arquitectura.md):** O2 decide *dónde vive* cada archivo. O3 decide *qué resuelve el sistema solo y qué le pregunta al modelo*. Un archivo puede estar en la capa correcta y seguir tomando una decisión que no le corresponde.

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
2. **`referencia/scd.md`.** Qué es SCD1 y SCD2 en este producto, cuándo se aplica cada uno, qué implica para el step y para el DDL. Hoy está disuelto entre `docs/SCD/`, `03c-investigacion-vocabulario-dimension-kettle.md` y `domain/scd.py`.
3. **`referencia/kettle-comportamiento.md`.** Destilado de `investigacion-tags-validos-por-step.md`: qué lee Kettle por step, qué vocabularios son condicionados, dónde están los centinelas que colisionan con valores válidos.
4. **`referencia/contrato-ddl.md`.** Qué garantiza el DDL, porque toda síntesis determinista depende de eso.

Sin las tres, O3 discute de memoria — y este proyecto ya tiene un caso registrado de qué pasa cuando se planifica sobre memoria en vez de sobre evidencia verificada.

---

## Decisiones que O3 tiene que tomar explícitamente

Ninguna está decidida. Se listan para que no aparezcan a mitad de camino.

| # | Decisión | Nota |
|---|---|---|
| 1 | ¿El step loader de dimensión se sintetiza completo, o se pide y se corrige? | Es el caso testigo. Si se sintetiza, desaparecen las estaciones 3-6 para ese step |
| 2 | ¿Qué entra en el prompt si el paso 1 sale "se sintetiza"? | La sección de dimensiones de `system_etl.txt` deja de tener destinatario. Es la revisión de prompts, que es consecuencia de esto, no un plan aparte |
| 3 | ¿Se ramifica por `scd_type` en la emisión? | **Cuidado: D44 ya decidió que no** — vocabulario uniforme por rol, `DimensionLookup` para todo `scd_type`, decidido leyendo fuente de Kettle. Reabrirlo necesita una D-N que la supersede explícitamente. No se puede empezar como si estuviera abierto |
| 4 | ¿Qué pasa cuando la síntesis no es posible por datos faltantes? | Hoy la respuesta es "reparar con otra llamada al modelo". La alternativa es notificar y entregar, coherente con O1 |
| 5 | ¿La verificación posterior sigue existiendo si lo determinista ya no se pregunta? | Probablemente sí, más chica: verifica lo que el modelo aportó, no lo que Python sintetizó |

---

## Criterio de terminado

1. La línea escrita como D-N: qué se sintetiza, qué se pregunta, qué se verifica.
2. Al menos el caso testigo (decisión 1) implementado end-to-end.
3. Las estaciones que dejaron de tener sentido, borradas — no desactivadas ni marcadas como deprecated.
4. `system_etl.txt` sin la sección que dejó de tener destinatario.
5. Una corrida real que muestre la cadena corta funcionando.

**El indicador:** si después de O3 sigue habiendo una estación de reparación para el mismo dato que Python ya podía derivar, la línea se trazó mal.

---

## Qué NO es O3

- No es reescribir el pipeline. Es decidir qué se pregunta.
- No es sacar al modelo del flujo. El modelo sigue haciendo lo que requiere juicio.
- No es la migración de capas — eso es [O2](20-arquitectura.md), y es independiente.
