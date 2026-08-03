# O1 — Estabilizar la emisión

**Mutable.** Lo escribe quien ejecuta el objetivo. Entrada: [`docs/README.md`](../README.md).

**Prioridad 1.** Bloqueado por [O0](00-higiene-repo.md) — sin diff legible no se puede revisar lo que este objetivo cambia.

---

## Objetivo

**`build_ktr()` siempre entrega un archivo.** Un `.ktr` que no funciona en Pentaho pero llega al usuario con el problema descripto es un resultado aceptable. Un `KtrBuilderError` que deja al usuario sin nada, no.

Esto **no** es aflojar R11. R11 prohíbe el fallo *silencioso*, no la entrega imperfecta — y ya distingue detección (fail-fast en el borde) de emisión (mejor-esfuerzo-y-notifica), ver `arquitectura-objetivo.md` R11, párrafo "Detección vs. emisión (D15)". Lo que O1 hace es mover cuatro puntos de la columna "detección" a la columna "emisión", donde ya está la mayoría del pipeline.

Encuadre del usuario, previo a D5 y con precedencia sobre él: **crear antes de cortar.**

---

## Segundo frente — que lo entregado no mienta

Agregado 2026-08-03, tras la investigación de la sesión T (`investigacion-tags-validos-por-step.md`, 47 steps contra `readData()` real).

O1 se escribió contra un riesgo: *el sistema no entrega archivo*. T documenta el riesgo opuesto, y es más grande: **el sistema entrega archivos que abren bien en Spoon y hacen algo distinto de lo pedido, en silencio.**

Eso tensiona el primer frente. Hacer que siempre se entregue, sin arreglar esto, **aumenta el volumen de salida silenciosamente incorrecta.** Los dos frentes son la misma pregunta — si lo que sale se puede creer — y se cierran juntos.

**Lote barato (E-04 … E-08).** Fixes de una a tres líneas, evidencia ya citada con clase y línea, cero decisiones pendientes. Es el arranque más rápido de todo O1:

| Error | Step | Qué |
|---|---|---|
| E-04 | `StringOperations` | Índices numéricos donde Kettle exige palabras. **El step nunca hace nada** |
| E-05 | `Unique` | Tag inexistente + polaridad invertida. Siempre case-insensitive |
| E-06 | `ExcelInput` | Sin `spreadsheet_type` no lee `.xlsx` |
| E-07 | `JsonInput` | Sin `includeNulls`, el comportamiento depende de la máquina |
| E-08 | `TextFileOutput` | Tag en el nivel equivocado del árbol |

**Lote estructural (E-09 … E-11).** `CombinationLookup` (falta un bloque entero), `DataValidator` (mapeo invertido), `SplitFieldToRows` (alias→`<type>` no registrado). Sin decisión de diseño, pero más caros.

Un commit por step, cada uno con test contra la salida real de `build_ktr()`. Registro completo en [`errores.md`](errores.md).

**Lote barato cerrado — 2026-08-03, ver D59.** E-04…E-08 arreglados, cada uno verificado contra `readData()`/`getXML()` real de la clase `*Meta.java` en `pentaho-kettle` (clase+método citados en D59), no por analogía. 5 commits (`d0a79b9`, `3194463`, `58d4e89`, `1462d85`, `37e792d`), 5 tests nuevos en `test_build_ktr_emission.py` — uno por step, contra la salida real de `build_ktr()`, patrón exigido acá. Suite completa corrida antes del lote: 693 passed / 55 failed — los 55 preexistentes (red/API-key en `test_api.py`, LLM sin crédito, y el rojo ya conocido E-03), ninguno en los 3 archivos que este lote tocó (`steps/transform.py`, `steps/input.py`, `steps/output.py`). Los 12 tests de `test_build_ktr_emission.py` en verde tras el lote. Cero regresión medible contra la cifra de O0.

**Lote estructural cerrado — O1-c, 2026-08-03.** `CombinationLookup` (`fields><return>` faltante), `DataValidator` (`name`/`fieldname` invertidos) y `SplitFieldToRows` (`<type>` sin registrar) arreglados, cada uno verificado contra `readData()`/`getXML()` real citado en `investigacion-tags-validos-por-step.md` § A. 3 commits (`7b0a78f`, `9a15593`, `e53387e`), 3 tests nuevos en `test_build_ktr_emission.py`. Suite completa: 697 passed / 54 failed — uno menos que el corte de O1-a, sin regresión nueva (la única falla que no estaba en el mismo test antes, `test_ktr_xml_validator.py::test_build_ktr_get_system_info_without_fields_gets_default_field`, se confirmó preexistente e independiente de estos cambios vía `git stash`). Ver `errores.md`.

---

## La inconsistencia que este objetivo resuelve

El repo ya resuelve esta misma familia de problema con las dos políticas opuestas, en el mismo archivo.

**Política A — entrega con el problema documentado** (`build.py:195-220`). Comentario literal del repo:

> *"Los tres son el mismo síntoma — un .ktr que Spoon abre pero falla (o vacía el pipeline) en runtime. NO abortan el build: el .ktr se genera igual y cada error se agrega a `warnings`... Preferible entregar el archivo con el problema documentado que no entregar nada."*

`validate_field_resolution` / `validate_row_sources` / `validate_dimension_lookup_races` reportan en severidad máxima (`Validacion tipo="error"`, D15) y dejan salir el archivo.

**Política B — aborta.** Cuatro sitios, misma clase de problema:

| Sitio (símbolo, y línea al 2026-08-03) | Qué aborta | Mensaje |
|---|---|---|
| `build.py`, lista `incomplete` — `:157` | claves de config estructuralmente faltantes | "Config incompleto en '<step>'" |
| `build.py`, lista `critical_incomplete` — `:253` | campos críticos vacíos, vía `_CRITICAL_FIELDS` | — |
| `build.py`, `STEP_BUILDERS.get(canonical_type) is None` — `:383` | step type sin emisor registrado | "Tipo de step no soportado" |
| `steps/lookups.py`, `_step_DimensionLookup` — `:91` | `<field><update>` fuera del vocabulario del modo (D-1) | **el crash que motiva O1** |

**El argumento no es un principio nuevo.** Es que dos políticas opuestas conviven, escritas por el mismo equipo, para problemas de la misma naturaleza — integridad de contenido, no forma de XML. La objeción documentada en su momento fue a la **degradación silenciosa** ("un .ktr que abre pero le falta un step entero"), no a la imperfección. Política A demuestra que, para el caso más cercano, el repo ya eligió entregar y documentar.

---

## El crash

Corrida real, flujo async normal, **después** de D57 y D58:

```
build_ktr (KTR_2 STG→DWH) failed: DimensionLookup 'Cargar dim_producto':
campo con type='Update' fuera del vocabulario de modo N (String, Number,
Integer, BigNumber, Date, Boolean, Binary, Timestamp)
```

Cadena confirmada, en `diagnostico-fk-categoria-loader-faltante.md`:

1. El LLM generó `'Cargar dim_producto'` con 6 campos, de los cuales **3 apuntan a columnas que no existen** en `dim_producto` (`fk_categoria`, `precio_lista`, `stock` — vocabulario de `fact_inventario`, no de la dimensión).
2. D58 hace lo diseñado: como falta `nombre_categoria`, se niega a forzar el step a loader, reporta y hace `continue` sin tocarlo.
3. El step llega intacto al emisor (`update="N"`, `fields` en vocabulario Y) → `KtrBuilderError`.

**No es un bug de D57/D58.** Es el comportamiento diseñado exponiendo un problema de otra capa: el LLM inventó nombres de columna. `system_etl.txt:629` (checklist B10) ya lo prohíbe y no tiene checker determinístico de respaldo — el mismo gap que motivó toda la serie, para un caso distinto.

Ya se implementó un repair dirigido (`etl_generator._repair_dimension_loader_fields`, 2026-08-02) con doble gate. **Lo que falta es el piso: qué pasa cuando el repair no alcanza.** Hoy: nada, aborta.

---

## La degradación ya existe — verificada, no estaba rota (E-03, cerrado por D60)

Encontrado en O0 (2026-08-03), registrado como **E-03**: `test_repair_dimension_loader_fields_floor_when_gate_fails` fallaba, en apariencia porque `_repair_dimension_loader_fields` aceptaba un `stream_field` que no existe en el stream y bajaba el finding a `tipo="info"`.

**Verificado en O1-b (D60, `02-decisiones.md`): esa lectura era incorrecta.** El test fallaba porque reusaba el fixture de su vecino exitoso (mismo atributo faltante, resoluble por el atajo determinístico sin LLM antes de llegar al fake que simulaba la alucinación) — defecto del fixture, no del gate. El gate real (`etl_generator.py:805-815`) sí rechaza un `stream_field` inexistente; corregido el fixture, el test pasa y confirma el piso que el diagnóstico prometía. El diagnóstico de la serie fk-categoria — *"si no pasa el gate, el step queda intacto y `build_ktr()` aborta exactamente como antes"* — **es correcto**.

El criterio para distinguir degradación legítima de rota seguía haciendo falta para generalizar a los 4 sitios de aborto (no depende de que este caso puntual resultara roto), y quedó escrito en D60:

- **Legítima:** el dato salió verificado contra un inventario real (`upstream_fields_for_step()`, DDL real) — nunca porque el LLM lo afirmó. Si no es verificable, no se asume ningún valor; se omite y el finding es `error`.
- **Rota:** se acepta un dato sin verificar contra nada real, se lo trata como válido, y se baja la severidad.

Encontrado al hacer esta verificación, fuera del alcance puntual de E-03, registrado aparte: **E-16** (`errores.md`) — `_synthesize_dimension_lookup_config`, rama de grafo no resoluble, asume identidad sin verificar y sin finding. Abierto, no bloquea O1.

---

## `VALUE_META_TYPE_NAMES` — verificada y corregida (E-02, cerrado por D60)

`VALUE_META_TYPE_NAMES` (`domain/scd.py`) se había mergeado con esta nota (`plan-reparacion-etl.md` § 1): *"Subconjunto confirmado contra el contexto de esta serie (String, Number, Date); PENDIENTE verificar la lista completa contra `ValueMetaFactory.java` antes de mergear"* — sin esa verificación.

**Verificado en O1-b, D60 (`02-decisiones.md`).** Contra `ValueMetaInterface.java:95-128` y `ValueMetaFactory.getValueMetaNames()` (`ValueMetaFactory.java:87-96`, filtra `id>0` y excluye `TYPE_SERIALIZABLE`): faltaba **`Internet Address`** (`TYPE_INET=10`). Agregado a `VALUE_META_TYPE_NAMES`, con la cita de clase+línea en el propio símbolo. No explica el crash de E-01 — ese step traía `type='Update'` (código de modo Y), no un nombre de value-meta faltante en la lista.

El patrón del sentinel colisionado sigue siendo relevante para el sitio 4 de la tabla de abajo: `getIdForValueMeta()` (`ValueMetaFactory.java:97-103`) devuelve `TYPE_NONE` cuando **no** encuentra el tipo — el mismo id que el de `"-"`. Leer como Kettle, fallar distinto que Kettle.

---

## Alcance

### Entra

1. ~~Verificar `VALUE_META_TYPE_NAMES` contra `ValueMetaFactory.java`.~~ **Hecho — D60.** Faltaba `Internet Address`; corregido. No resolvió el crash de E-01 (causa distinta, ver D60).
2. **Convertir los cuatro abortos en entrega documentada.** Cada sitio necesita decidir qué escribe en el XML cuando el dato es inválido, y esa decisión se justifica contra el `Meta` de Kettle — no se inventa un default plausible. Si no hay valor defendible, se emite el valor tal como vino y el finding explica que el step no va a funcionar. **Política decidida en D60** (tabla de los 4 sitios, criterio de degradación legítima) — conversión en código todavía pendiente, sesión aparte.
3. **Que el problema llegue al usuario.** Es la decisión #3 del diagnóstico, hasta hoy sin resolver: los findings de `enforce_dimension_step_policy` van a `job.model_json["step_policy_conflictos"]` / `validaciones`, no al log que se estaba mirando. Sin esto, "entregar con el problema documentado" es entregar un archivo roto sin aviso — peor que abortar. **Este punto no es opcional dentro de O1.**
4. **Un test por sitio**, sobre la salida real de `build_ktr()`, no sobre fixtures usadas como input. El patrón ya existe: `test_build_ktr_emission.py`.
5. **Escribir la decisión como D-N** en `02-decisiones.md`, superseding explícito de la parte de D-1 que exige abortar. Sin esto, la próxima sesión reabre la discusión.

### No entra

- Impedir que el LLM invente nombres de columna. El repair ya existe; mejorar su tasa de acierto es otro objetivo.
- El checker "qué sobra" (candidato 2 del diagnóstico: campos del step ausentes del contrato). Se cerró parcialmente el 2026-08-02 dentro del discriminador de `dimension_step_policy.py`.
- Reforzar el prompt (candidato 2 del diagnóstico) — congelado, ver [`90-congelado.md`](90-congelado.md).

---

## Criterio de terminado

1. `VALUE_META_TYPE_NAMES` verificada contra `ValueMetaFactory.java`, con clase y línea citadas en el código.
2. Ninguno de los 4 sitios de la tabla levanta `KtrBuilderError` por contenido inválido. Un `.ktr` sale siempre.
3. Cada degradación produce un `Finding(severity="error")` que llega al frontend como `Validacion tipo="error"`, **verificado en una corrida real**, no por lectura de código.
4. La corrida que produjo el crash de `'Cargar dim_producto'` genera archivo. Se abre en Spoon. Falla en runtime si tiene que fallar — pero el usuario tenía el aviso antes de ejecutarlo.
5. Un test por sitio, contra salida real de `build_ktr()`.
6. D-N escrita en `02-decisiones.md`.
7. Suite completa corrida, comparada contra la cifra que O0 dejó registrada. Cero regresión.

**El punto 4 es el único criterio que importa de verdad.** Los demás lo sostienen.

---

## Qué sigue abortando, a propósito

No todo aborto es un defecto. Los que se conservan, con su motivo:

- **XML mal formado.** Si el resultado no es XML válido no hay archivo que entregar; la degradación no aplica.
- **`ktr_data` que no es un dict con `steps`.** Es el borde de entrada (R5), no contenido. Ahí fail-fast es lo correcto.

La línea es: **forma del artefacto → aborta; contenido del artefacto → entrega y documenta.** Los 4 sitios de la tabla son todos de contenido.
