# Diagnóstico — 'Cargar dim_producto' sigue crasheando tras D57/D58

> **Temporal — borrar cuando el problema esté cubierto.** No es un H ni una D
> (no append-only, no sigue la convención de `01-hallazgos.md`/`02-decisiones.md`).
> Es handoff de una sesión a otra: diagnóstico cerrado, plan de arreglo abierto.
> Escrito 2026-08-02.

## Síntoma

Mismo error de siempre, en una corrida real (async, flujo "Generar" normal —
`generate_etl_async` → `_try_build`), DESPUÉS de aplicar D57 y D58:

```
build_ktr (KTR_2 STG→DWH) failed: DimensionLookup 'Cargar dim_producto':
campo con type='Update' fuera del vocabulario de modo N (String, Number,
Integer, BigNumber, Date, Boolean, Binary, Timestamp) — check_dimension_
lookup_fields.py debió reportar esto antes; no se emite XML con vocabulario
cruzado (D-1).
```

Precedido por 6 findings del validador (uno por campo, todos `type='Update'`
en modo N): `nombre_producto`, `fk_categoria`, `precio_lista`,
`precio_unitario`, `stock`, `bk_producto_calculado`.

## Cadena de causalidad — confirmada, no especulada

1. **DDL real de `dim_producto`** (mismo corpus de toda esta serie,
   `DDL-inferido-test-con-raw.txt` en este hilo):
   ```sql
   CREATE TABLE dim_producto (
       sk_producto, version, fecha_inicio, fecha_fin, id_producto_origen,
       bk_producto, nombre_producto, nombre_categoria, precio_unitario
   );
   ```
   Atributos de negocio reales (no clave/estructurales): **`nombre_producto`,
   `nombre_categoria`, `precio_unitario`, `bk_producto`**. Ninguna columna
   `fk_categoria`, `precio_lista` ni `stock` existe en esta tabla — esas
   pertenecen a `fact_inventario` (columnas reales ahí: `fk_categoria`,
   `precio_lista` no, pero sí `precio_unitario`/`stock`/`valor_inventario`)
   o a staging.

2. **El step `'Cargar dim_producto'` que el LLM generó** declara `fields`
   con `table_field`: `nombre_producto` (✓ existe), `fk_categoria` (✗ no
   existe — debería ser `nombre_categoria`), `precio_lista` (✗ no existe en
   `dim_producto`), `precio_unitario` (✓ existe), `stock` (✗ no existe en
   `dim_producto`), `bk_producto` vía `bk_producto_calculado` (✓ existe).
   **3 de 6 campos apuntan a columnas que no están en el DDL de esta tabla.**
   Patrón: se parecen sospechosamente a columnas de `fact_inventario`
   (`fk_categoria`, `precio_lista`, `stock` son vocabulario de hecho, no de
   dimensión) — hipótesis de trabajo: el modelo mezcló el vocabulario de
   columnas del step de hecho con el de la dimensión al generar
   `'Cargar dim_producto'`.

3. **D58 (discriminador de atributos, `dimension_step_policy.py`) hizo
   exactamente lo que se decidió que hiciera**: como el step es candidato
   único para `dim_producto` y `role_of_dimension_step` lo clasifica
   `"fact_lookup"` (alimenta, vía hop, un escritor de `fact_inventario` —
   patrón normal de loader-que-alimenta-el-hecho), el discriminador exige
   que `fields` contenga el conjunto COMPLETO de atributos que
   `dim_contracts` declara para `dim_producto`. Falta `nombre_categoria`
   (el step trae `fk_categoria` en su lugar, nombre distinto) → el
   discriminador **rechaza forzar a loader**, agrega un finding
   `tipo="error"` ("...no trae en 'fields' los atributos que el contrato
   declara — falta(n): nombre_categoria... Probable loader faltante...")
   y hace `continue` **sin tocar el step**.

4. Con el step intacto (`update="N"`, `fields` en vocabulario Y), llega
   igual al emisor (`lookups.py:89-97`) → `KtrBuilderError` → mismo crash
   que antes de D57/D58, pero ahora por una razón distinta y correcta: el
   sistema se negó, a propósito, a adivinar que este step "roto" era
   igual el loader.

**No es un bug de D57/D58 — es el comportamiento diseñado (D5: ante
ambigüedad, reporta, no fuerza) exponiendo un problema de una capa
distinta: el LLM generó nombres de columna que no existen en la tabla
destino.** Corregir eso NO es responsabilidad de `dimension_step_policy.py`
(decide tipo de step + modo de escritura, no legitimidad de nombres de
columna).

## Confirmación pendiente (no bloquea el diagnóstico, sí la certeza total)

No tengo el `dim_contracts` real de esta corrida (solo el log de terminal,
que no expone los findings de `enforce_dimension_step_policy` — esos van a
`job.model_json["step_policy_conflictos"]`/`validaciones` de la respuesta
HTTP, no al logger `KTR validation:`/`KTR fidelidad:` de `build.py`). Si la
próxima sesión tiene el `dim_contracts` o el `validaciones` completo de esta
corrida: confirmar que `attributes_scd1`/`attributes_scd2` de `dim_producto`
trae `nombre_categoria` (no `fk_categoria`) y NO trae `precio_lista`/`stock`
— eso cierra la hipótesis al 100%. Muy probable dado el DDL, pero no
verificado contra el JSON real de dim_contracts de ESTA corrida puntual.

## El prompt YA prohíbe esto — y no hay gate determinístico que lo respalde

`backend/prompts/system_etl.txt:629` (checklist B10), literal:

> ¿Algún `DimensionLookup`/.../`InsertUpdate`/`TableOutput` referencia, en
> ... `fields[].table_field`, ... un nombre que NO existe como columna
> física en el DDL provisto de esa tabla (staging o DWH)? → Si SÍ: corregir
> al nombre real de la columna física (ej. `sk_cliente`, no `fk_cliente` ni
> `sk_cliente_dwh`).

El ejemplo del propio prompt (`fk_cliente` en vez de `sk_cliente`) es la
MISMA familia de error que `fk_categoria` en vez de `nombre_categoria` acá.
El modelo lo violó igual. A diferencia de casi todo el resto de reglas
K/B de este prompt, **esta no tiene ningún checker determinístico de
respaldo en el backend** — depende 100% de que el modelo se autocorrija
contra su propio checklist. Mismo patrón de gap que motivó toda la serie
D-1/D57/D58 (guía de generación sin red de seguridad backend), pero para
un caso distinto: no es vocabulario de modo (Y/N), es legitimidad del
nombre de columna contra el DDL real.

## Lugares involucrados (para no re-derivar la próxima sesión)

| Rol | Archivo:línea | Qué hace hoy |
|---|---|---|
| Emisor — gate final, bloquea | `backend/app/services/ktr_builder/steps/lookups.py:89-97` | Levanta `KtrBuilderError` si `fields[].type` no pertenece al vocabulario del modo (D-1). No sabe nada de nombres de columna. |
| Validador de vocabulario — reporta, no bloquea | `backend/app/services/ktr_builder/validators/dimension_lookup_fields.py:35` (`check_dimension_lookup_fields`) | Reporta `severity="error"` por el mismo motivo que el emisor (vocabulario de modo), ANTES de emisión. Tampoco valida nombre de columna contra DDL. |
| Policy de rol — decide tipo/modo, discrimina por atributos | `backend/app/services/ktr_builder/dimension_step_policy.py` (bloque `# D58:` dentro de `enforce_dimension_step_policy`, ~línea 322 en adelante) | Exige *que el conjunto de atributos del contrato esté presente* en `fields` para forzar loader — pero compara CONJUNTOS DE NOMBRES declarados (`dim_contracts.attributes_scd1/scd2`) contra los `table_field`/`lookup` que el step YA trae. No valida esos nombres contra el DDL en sí (usa `dim_contracts` como proxy del DDL, que es correcto, pero no hace la comparación al revés: qué campos del step NO están en el contrato en absoluto — hoy solo mira qué falta, no qué sobra). |
| Prompt — la regla ya existe, sin respaldo backend | `backend/prompts/system_etl.txt:629` (checklist B10) | Le pide al modelo autocorregir nombres de columna inexistentes. Sin checker propio. |
| Fuente de vocabulario que se le da al modelo | `backend/app/services/etl_generator.py:335-381` (`_format_dim_contracts`) | Arma el texto con `attributes_scd1`/`attributes_scd2` EXACTOS por dimensión que va al prompt de KTR_2. Confirmar acá qué recibió el modelo para `dim_producto` en esta corrida específica (requiere log/replay de la llamada, no solo el DDL). |

## Candidatos de arreglo para la próxima sesión (no decidido, no implementado)

1. **Nuevo checker determinístico** (post-emisión de este mismo hallazgo,
   pre-emisión del `.ktr`): para todo `DimensionLookup`/`CombinationLookup`
   sobre una tabla de `dim_contracts`, todo `table_field`/`lookup` en
   `fields` que NO esté en `attributes_scd1 ∪ attributes_scd2 ∪ {technical_key,
   natural_keys...}` es sospechoso — reportar, no reparar (mismo patrón que
   todo el resto del archivo). Complementa al discriminador de D58 (que
   mira qué falta) mirando qué sobra.
2. **Reforzar el prompt** en la sección "STEP DE DIMENSIONES" /
   `_format_dim_contracts` para que el listado de atributos sea aún más
   difícil de confundir con columnas de la tabla de hechos (ej. remarcar
   explícitamente qué NO es atributo de esta dimensión, si el DWH tiene
   una tabla de hechos con columnas de nombre parecido).
3. **Decisión pendiente, la más importante:** ¿este caso — step único
   candidato, contrato incompleto/con nombres ajenos — debe seguir siendo
   "reporta y no construye el `.ktr`" (estado actual, D5/D58), o el
   producto necesita que el flujo async (`_try_build`) le muestre al
   usuario ANTES de esto que hay un problema irreparable, en vez de que
   el error aparezca recién en el log de build? Hoy `_try_build` sí deja
   `job.build_status = failed` con `model_error` — falta confirmar que el
   finding de D58 ("loader faltante") llegue al usuario de forma legible
   en el frontend, no solo como log de servidor.

## Contexto rápido de la serie D57/D58 (por si la próxima sesión no la vivió)

- **D57** (`02-decisiones.md`): al reclasificar un step a `fact_lookup`,
  limpiar `fields` en vez de dejarlos con vocabulario viejo cruzado.
- **D58** (`02-decisiones.md`, pendiente de redacción final por el
  usuario — ver conversación, quedó desactualizada en una primera versión
  y se corrigió en la misma sesión): 1 solo step candidato para una tabla
  de `dim_contracts` no prueba por sí solo que sea el loader — se exige
  que `fields` traiga el conjunto COMPLETO de atributos del contrato antes
  de forzarlo a loader; si no, error, no fuerza.
- Tests de esa serie: `backend/tests/test_dimension_step_policy.py`,
  `backend/tests/test_build_ktr_emission.py` (todos verdes, 29 tests —
  no cubren este caso nuevo porque es un problema distinto: nombres de
  columna inventados, no clasificación de rol).

## Cierre (2026-08-02, misma sesión que este diagnóstico)

Vía repair, no degradación (decisión explícita del usuario — degradación
queda diferida, ver sección siguiente). Implementado:

1. **Checker (candidato 1 de arriba), embebido en el discriminador de
   `dimension_step_policy.py`** (no en `validators/` — depende de
   `dim_contracts` + topología de hops a la vez, re-derivar la condición
   aparte es drift garantizado). Reporta `missing` Y `sobra`, marca la
   finding `repairable=True`.
2. **Repair dirigido** (`etl_generator._repair_dimension_loader_fields`,
   nuevo) — una llamada acotada al LLM por step candidato, alcance de
   autoridad limitado a un solo mapeo `table_field->stream_field` (todo lo
   demás que el modelo devuelva se descarta sin avisar). Doble gate antes
   de aplicar: cubre el `missing` completo, y cada `stream_field` propuesto
   existe de verdad en el stream (`fields_validate.upstream_fields_for_step`,
   nuevo). Piso preservado: si no pasa el gate, el step queda intacto y
   `build_ktr()` aborta exactamente como antes de este cambio.
3. **Hallazgo lateral, más grave que el original — H53
   (`01-hallazgos.md`):** `_synthesize_dimension_lookup_config` (código YA
   shippeado desde D44/D51, no nuevo de esta sesión) asumía
   `stream_field==table_field` sin verificar, en 3 call sites. Confirmado
   contra el corpus real: el stream de `'Cargar dim_producto'` trae
   `categoria`, nunca `nombre_categoria` — el código viejo lo habría
   mapeado igual, produciendo `.ktr` que abre en Spoon y falla en runtime
   sin ningún aviso previo. Cerrado en la misma sesión (ver H53 para el
   detalle completo) — registrado igual porque es candidato a explicar
   fallas anteriores con el síntoma "genera, abre, no escribe" sin causa
   asignada.
4. **Parte A:** `_consumes_dimension_lookup` (`contracts.py`) extendida
   para que `validate_field_resolution`/`build.py:214` vean
   `fields[].stream_field` de `DimensionLookup` (antes solo `keys`) —
   cierra un punto ciego preexistente del grafo de campos, no exclusivo de
   este caso.

Suite completa corrida en 3 puntos de esta sesión (tras el fix de
`_synthesize`, tras Parte A, tras el repair completo): mismos 45 fallos
preexistentes (servidor no vivo / cuota Gemini / 1 test ya roto de antes),
cero regresión en ninguna corrida. Tests nuevos:
`backend/tests/test_dimension_field_repair.py` +
3 tests agregados a `backend/tests/test_dimension_step_policy.py`.

**Decisión pendiente #3 de arriba (visibilidad en frontend del finding
cuando el repair NO alcanza) sigue sin resolver** — fuera de alcance
explícito de esta sesión, no tocado.

**Actualización (mismo día, 2026-08-02):** el gap "camino `build_from_raw`
sin cubrir" (listado arriba como fuera de alcance) se cerró en la misma
sesión, a pedido del usuario — es el camino que está usando para probar sin
gastar tokens regenerando desde cero (tiene el raw + DDL de una corrida ya
hecha, usa "Reutilizar respuesta"). `ai.py:build_from_raw` ahora inyecta
`llm` real (antes `None` hardcodeado, desconexión deliberada con discusión
pendiente) y `build_etl_from_raw()` corre `_repair_dimension_loader_fields`
en los dos branches (KTR_1/KTR_2 y legacy). Llamadas acotadas a un step por
vez (no regeneración) — el punto del endpoint (evitar las 2 llamadas
grandes) se preserva. `repair_ktr_steps` (el otro repair, config
incompleto) queda reactivado de paso — ya estaba diseñado para recibir
`llm`, solo el router nunca se lo pasaba. Suite completa corrida después:
mismos 45 fallos preexistentes, cero regresión (los 3 tests de
`build-from-raw` en `test_ktr_build_job_api.py` no pasan `dim_contracts`,
así que no ejercitan el repair nuevo — cobertura de ese path queda
apoyada en los tests de `_repair_dimension_loader_fields` ya escritos,
que prueban la función en sí, no el endpoint).

## Precedente para la sesión de degradación (diferida, no resuelta acá)

Al evaluar la vía de degradación determinística (emitir `.ktr` con notepad
en vez de abortar cuando el repair falla), surgió un dato que vale más de
lo que parece y que la sesión futura no debería tener que re-descubrir:

**`build.py:195-220` ya resuelve la MISMA familia de problema —
integridad de campos rota— con la política opuesta a la de
`lookups.py`/D-1.** Cita literal del comentario propio del repo:

> *"Los tres son el mismo síntoma... NO abortan el build: el .ktr se genera
> igual y cada error se agrega a `warnings`... Preferible entregar el
> archivo con el problema documentado que no entregar nada."*

`validate_field_resolution`/`validate_row_sources`/
`validate_dimension_lookup_races` (las tres validaciones de integridad de
campos que corren ahí) reportan en severidad máxima (`Validacion
tipo="error"`, D15) y dejan salir el archivo igual. `lookups.py`
(vocabulario cruzado, D-1) resuelve el mismo tipo de problema —integridad
de datos rota, no de forma XML— con `KtrBuilderError`, aborta.

**El argumento no es "convencer de un principio nuevo" — es señalar una
inconsistencia interna ya escrita en el propio código, por el mismo
equipo.** Los precedentes citados en la conversación que originó este
diagnóstico (`build.py:376-385`, tipo de step no soportado; D55 ítem 1)
prohíben la **degradación silenciosa** — "fallback silencioso", "un .ktr
que abre pero le falta un step entero". La objeción documentada es a la
silenciosidad, no a la imperfección. `build.py:195-220` demuestra que,
para la clase de problema más cercana a este (integridad de campos, no
forma de step), el propio repo ya eligió "entregar con el problema
documentado" — con severidad máxima, no en silencio.

Nota de encuadre explícita del usuario, para cuando se retome: la
directiva permanente del proyecto es **crear antes de cortar**, y es
previa a D5 — cualquier revisión de esta pregunta arranca de ahí, no de D5
como default.

No se toca nada de esto en esta sesión — queda anotado para cuando se
decida retomar la vía de degradación, con datos de cuántas veces el repair
implementado arriba alcanza a resolver el caso sin necesitar ese camino.
