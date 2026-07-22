# Decisiones — Refactor de fragmentación

**Última actualización:** 2026-07-22

Este archivo es la fuente de verdad del refactor. Manda sobre cualquier análisis, plan o conclusión de sesión que lo contradiga. Cuando un análisis choca con una decisión de acá, gana la decisión y el análisis queda marcado como obsoleto.

Toda sesión que tome una decisión cierra actualizando este archivo.

---

## Objetivo

Hoy el sistema fuerza todo ETL a exactamente dos archivos KTR (Origen→Staging, Staging→DWH). **Ese forzado es la falla:** cuando un proceso necesitaba separarse, meterlo igual dentro de dos archivos produjo errores.

El refactor desacopla la fase lógica del archivo físico. El orden macro Origen→Staging / Staging→DWH se mantiene como concepto de fases, pero deja de determinar la cantidad de archivos. El backend decide, en base a reglas concretas, cómo se materializan esas fases: puede ser un KTR, pueden ser varios. Cuando son varios, se genera además un KJB que los ordena.

Fragmentar no es obligatorio ni el caso por defecto: es una decisión razonada sobre el conjunto de steps y sus dependencias. Para un ETL simple, el resultado correcto puede seguir siendo dos archivos.

**Razón:** corrección estructural — races de lectura/escritura, dimensiones consultadas pero no cargadas, doble escritor sobre la misma tabla, arreglos de KTR que fallen silenciosamente. **No** es legibilidad ni buenas prácticas de organización en general — ver D6-bis. Un KTR largo pero correcto no se parte.

Todo lo demás del proyecto es río abajo de este objetivo y se evalúa contra él.

---

## Decisiones vigentes

### D1 — Fase lógica ≠ archivo físico

La cantidad de archivos KTR deja de estar fijada. Se deriva de reglas aplicadas sobre el conjunto de steps y su grafo de dependencias.

*Por qué:* hoy los dos conceptos están mapeados 1:1 y hardcodeados, y esa es la causa raíz de los errores que motivan el refactor.

*Consecuencia:* hay que encontrar y remover la partición fija en dos, y revisar qué código asume que siempre son dos.

*Qué la invalidaría:* que se demuestre que ningún caso real requiere más de dos archivos.

### D2 — No optimizamos por preservar el comportamiento actual

Las zonas afectadas van a sufrir cambios estructurales que vuelven irrelevante si hoy funcionaban. "Esto hoy anda" no es argumento para protegerlo.

*Por qué:* el plan estaba gastando esfuerzo en conciliar comportamientos que el refactor vuelve obsoletos.

### D3 — Los datos guardados son descartables

Regenerar los ETLs desde datos base es preferible, y además sirve para volver a probar el sistema. No pedimos migración de datos ni modo permisivo por compatibilidad histórica.

*Consecuencia:* cae la objeción de "los ETLs viejos dejan de abrir". También cae la conclusión previa de que `parse_cfg` no se puede eliminar nunca — descansaba enteramente en las filas históricas.

*Qué la invalidaría:* que alguien del equipo tenga trabajo apoyado en ETLs guardados. Ver verificaciones pendientes.

### D4 — La compatibilidad hacia atrás no es requisito hasta nuevo aviso

Cuando lo sea, se decide explícitamente acá y se revisa todo lo que dependa de esto.

### D5 — Ante la duda entre tolerar y fallar, se falla

Preferimos que un cambio rompa fuerte y visible antes que degrade en silencio.

*Por qué:* no es preferencia estilística. Es el mismo principio que motiva la fragmentación —evitar arreglos de KTR que fallen silenciosamente— aplicado al código que los genera.

*Consecuencia:* nada de degradar a valores vacíos dentro de un `except`. Un input inválido produce un error explícito con contexto suficiente para ubicarlo.

### D6 — La fragmentación la decide el backend, de forma determinística

El LLM propone el ETL lógico. El backend decide la materialización física en N KTRs más el KJB.

*Por qué:* el refactor existe para reducir errores. Poner la decisión en el LLM le mete no-determinismo justo a la capa que existe para eliminarlo.

**Estado: confirmado, con evidencia en repo (re-verificado en frío, 2026-07-22).** Evidencia:

1. `_build_job_plan()` (`backend/app/services/etl_generator.py:224`) ya construye el `JobPlan` del KJB en Python puro — precedente de orquestación backend-owned.
2. Contracaso instructivo: el flujo `CreateJob` **sí** consulta al LLM, porque ahí los `.ktr` son de autoría externa y el backend no tiene grafo propio. La línea divisoria es *dónde ya vive la información*, no una preferencia general por determinismo.
3. `build_lineage()` (`backend/app/services/lineage_builder.py`) ya computa `in_deg`/`out_deg` y extrae tablas por step — exactamente la señal que necesita un algoritmo de corte.
4. `repair_ktr_steps()` (`backend/app/services/ktr_builder/repair.py:136`), `repair_integrity_gaps()` (`repair.py:230`) y `enforce_dimension_step_policy()` (`backend/app/services/ktr_builder/dimension_step_policy.py:72`) ya son mutaciones determinísticas post-LLM. El pase de fragmentación entra en ese mismo punto del pipeline.

*Qué la invalidaría:* si se diera vuelta, cambia el schema de salida entero, las reglas pasan a ser prompt engineering en vez de código testeable, y hay que revisar D1 y el plan completo. (Ya no es un riesgo abierto — queda documentado por si algo futuro lo pone en duda.)

### D6-bis — La fragmentación es un mecanismo de corrección, no de legibilidad

**La fragmentación responde únicamente a corrección estructural: races, fallas silenciosas, conflictos de lectura/escritura sobre la misma tabla. Un KTR largo pero correcto no se parte.**

*Por qué:* el proyecto acelera y busca que funcione. Está orientado a profesionales del área — si el usuario quiere reorganizar el KTR a su gusto, es su terreno y su responsabilidad, no del generador.

*Consecuencia:* **no se introducen umbrales hardcodeados** del tipo "partir si >15 steps". El backend corta por señal estructural o no corta. Esta regla frena el próximo "ya que estamos, partamos esto que es largo".

*Corolario bajo D6+D6-bis juntas:* crear una tabla nueva (ej. `dim_tiempo`), agregar una rama de validación de calidad, o reescribir SQL, nunca pudieron ser "fragmentación" — ningún análisis de grafo produce eso. Si aparecen mezclados con un corte real en algún caso histórico, son cambios que viajaron de polizón, no parte de la regla.

*Pendiente:* el material de fragmentación (`handoff_fragmentacion_y_errores.md`) ya contiene reglas de cuándo fragmentar escritas antes de esta decisión. Hay que releerlas y eliminar las que respondan a legibilidad o tamaño en vez de corrección estructural — ver `03-plan.md`, ítem bloqueante antes de diseñar el corte (Track F2).

### D7 — Las reglas de fragmentación se derivan de casos reales de falla

No se diseñan desde una lista abstracta de buenas prácticas de Pentaho. Se derivan de los casos concretos donde forzar dos archivos produjo errores: qué ETL, qué steps, qué falló, cómo se resolvió separando.

*Por qué:* tenemos evidencia empírica. Sin ella, el motor de reglas se diseña contra un problema imaginado y va a partir de más o de menos.

*Consecuencia:* cada caso histórico de falla es también un caso de prueba: debe producir la partición correcta.

### D8 — El conocimiento de dominio sobre steps tiene una sola casa

Qué tabla toca un step, con qué alias, y si lee o escribe: eso vive en un único lugar. Ningún código nuevo —incluido el motor de fragmentación— reimplementa esa noción por su cuenta.

*Por qué:* hoy está duplicado en al menos cuatro archivos y **ya divergió**. El motor de reglas sería el quinto y el más importante: construirlo sobre una base que diverge es garantizar particiones incorrectas.

*Consecuencia:* centralizamos el dato, no necesariamente la interfaz. Una sola fuente de verdad, y encima funciones separadas y finitas por cada proyección que los consumidores necesiten. No forzamos un accessor único que devuelva todo.

### D9 — Criterio de verificación: delta declarado, no diff contra el pasado

El prompt de Fase 5 (auditoría de arquitectura) pedía verificar cada paso "comparando el artefacto generado antes y después". D2 mata esa política de preservar comportamiento, pero no mata la necesidad de un criterio de verificación — solo cambia contra qué se compara.

**Contra qué se compara: contra el delta declarado, no contra el output viejo.** Antes de correr un paso se enumera qué va a cambiar. Después, cada diferencia observada tiene que mapear a un ítem declarado. Criterio de aprobación: **cero deltas sin explicar**. No exige que nada cambie; exige que nada cambie por sorpresa.

*Herramienta:* normalización canónica — aplanar todos los `.ktr` a una secuencia ordenada de steps con su config y hops, ignorando fronteras de archivo. Así se genera la lista de deltas de forma confiable.

*Cuatro clases de cambio, cada una con su línea base propia* (un solo "diff" mezclaba las cuatro, por eso el diff se volvía ilegible):

| Clase | Ejemplo | Se valida contra |
|---|---|---|
| Costura forzada por el corte | 2 `TableInput` para alimentar un `StreamLookup` que antes era 1 | Canónico invariante |
| Funcionalidad nueva | Un step nuevo que antes no existía | Requisito propio, explícito |
| Rediseño (sustitución de tipo de step) | `DimensionLookup` → `InsertUpdate` | Decisión explícita con su costo declarado |
| Corrección / supuesto | Fix de nombre/rename, dialecto SQL asumido | Bug fix vs. supuesto introducido, declarado como tal |

*Consecuencia sobre la Restricción 1 de Fase 5 (`fase-5-plan-remediacion.md`):* se parte en dos lecturas — A) "el artefacto sigue produciendo lo mismo": **eliminada**, es lo que D2 dice que no se protege. B) "el repo queda verde y cada paso es revertible por separado": **se mantiene**, es regla de tamaño de paso, no de preservación de comportamiento.

*Por qué:* sin este criterio, D2 se leía como "no verificamos nada", que no es lo que dice — dice que no usamos "distinto de antes" como señal de bug por sí sola.

### D10 — Sin período de convivencia entre parseo viejo y nuevo

Consecuencia directa de D3 verificado (ver Verificaciones pendientes): como nadie tiene trabajo apoyado en datos guardados, el requisito de compatibilidad no existe. El mecanismo de vuelta atrás ante un problema es revertir el commit, no sostener dos caminos en paralelo.

*Consecuencia:* la sección "Compatibilidad durante la transición" del prompt de Fase 5 (`fase-5-plan-remediacion.md`) queda sin motivo — el borde nuevo puede reemplazar el parseo viejo de una vez, sin ventana planeada de convivencia.

*Por qué importa dejarlo explícito acá:* si el resto del prompt de Fase 5 se retoma sin marcar esto, se reabre desde cero una pregunta que ya tiene evidencia (D3).

### D11 — `dim_contracts` (commit `149b836`) no choca con el refactor de fragmentación

Eje distinto: `dim_contracts` decide **qué tipo de step** carga una dimensión (SCD1 vs SCD2); la fragmentación decide **cuántos archivos**. No se pisan.

Más importante: `dim_contracts` ya usa el patrón que D6 pide — el backend deriva determinísticamente, el modelo no rejuzga en cada corrida (`dimension_step_policy.derive_dimension_step_type`). Es **precedente, no obstáculo**. No hay que tocarlo ni revertirlo.

*Consecuencia menor:* toca en chico dos cosas ya documentadas para cambiar bajo D8, ambas dentro del PASO 1 planeado — `dimension_step_policy.py:53` (copia propia de `parse_cfg`, ver H3 en `01-hallazgos.md`) y `dimension_step_policy.py:107` (alias de tabla con `or` inline en vez de `contracts.STEP_CONTRACTS.key_aliases`, ver H4).

### D12 — Dialecto SQL: Postgres por defecto, con notificación obligatoria

El SQL generado depende del motor que declara el usuario, y hasta ahora eso no estaba escrito en ningún lado — Postgres fue un supuesto implícito horneado en construcciones específicas de dialecto en el SQL generado (ej. `DISTINCT ON`) en salidas de sesiones anteriores. No hay ocurrencias de ese patrón en el backend actual (`backend/`) — el supuesto vive en el SQL que el LLM genera dentro de `config`, no en código Python.

**Decisión:** por defecto, toda query SQL se genera asumiendo PostgreSQL. Queda escrito como decisión, no como supuesto implícito.

**Punto de notificación obligatorio:** cuando el flujo llegue al momento de generar SQL con dependencia de dialecto, tiene que avisar y dar contexto en vez de asumir en silencio. Es información crítica que se fija antes de generar — cambiarla después implica retocar todo lo ya generado.

*Por qué:* mismo principio que D9 — declarar antes, no explicar después.

*Fuera de alcance de esta decisión:* el soporte real multi-motor (Postgres / SQL Server según la base final elegida) no tiene plan todavía. Requiere sesión y sub-plan propios — ver "Abiertos" más abajo.

### D13 — Definición de terminado, obligatoria para toda fase del plan

Ninguna fase de `03-plan.md` (Track A o Track F) se da por cerrada sin estas tres cosas:

1. **Dos tests:** uno que haga cumplir específicamente lo que esa fase trabajó, y uno que verifique que el contrato que esa fase *expone* se sostiene (lo que la fase siguiente va a consumir) — escrito como contrato expuesto, no como "conexión con la fase siguiente", para no desactualizarse si el orden de fases cambia.
2. **El registro de deltas de esa fase** (D9), emitido como *warnings del propio pase* en el mismo punto del pipeline donde ya viven `repair_ktr_steps`, `repair_integrity_gaps` y `enforce_dimension_step_policy` — automático en cada corrida, no un documento que depende de que alguien lo escriba y lo lea. Tiene que cubrir **las dos fuentes de cambio**: lo que el backend genera determinísticamente y lo que produce una sesión de generación con el LLM. Los tests no lo reemplazan — un test afirma lo que a alguien se le ocurrió afirmar; el registro expone lo que viajó sin que nadie lo pidiera (ver "SCD tipo 2" en `01-hallazgos.md`, H9 — así se perdió esa vez).
3. **`CLAUDE.md` y un archivo de progreso actualizados:** qué cambió a nivel de convenciones/arquitectura/decisiones vigentes, y qué fase se cerró, qué queda, qué se decidió en el camino. Objetivo: el plan es retomable por cualquiera, no solo por quien lo arrancó.

*Por qué:* sin esto, el tramo "rojo" de la migración no tiene final definido fase por fase — siempre se corre un cambio más antes de reconectar.

---

## Deliberadamente no decidido

Distinguir esto de lo cerrado evita que alguien lo dé por resuelto:

- **Si el borde tipado de entrada va, y en qué fase.** Lo resuelve arquitectura. La pregunta concreta: ¿es habilitador de la fragmentación o una optimización paralela?
- **El cambio `string → object` en el schema del LLM.** Depende de un spike empírico contra Gemini y Anthropic, no de un criterio.
- **Qué hace el producto ante un raw incompleto en `build-from-raw`.** Hoy el repair loop está desconectado a propósito, con discusión pendiente. Bloquea cuán estricto puede ser ese punto de entrada.
- **El alcance exacto de las reglas de fragmentación.** Depende de D7: primero los casos, después las reglas. D7 ya confirma que los casos existen (ver Verificaciones pendientes) — falta la entrega concreta de su ubicación antes de poder escribir las reglas.
- **El plan de soporte multi-motor SQL.** D12 fija Postgres como default y exige notificación, pero no dice dónde vive la decisión de dialecto, qué construcciones son dependientes de motor más allá de `DISTINCT ON`, ni qué pasa si el usuario cambia de motor después de generar. Requiere sesión propia.

---

## Verificaciones pendientes

1. ~~Confirmar que nadie del equipo tenga trabajo apoyado en ETLs guardados.~~ **Verificado 2026-07-22: nadie tiene trabajo apoyado en ETLs guardados.** D3 queda confirmado sin condición, desbloquea D10.
2. ~~Re-verificar D6 en frío.~~ **Hecho 2026-07-22** — ver evidencia bajo D6 y D6-bis arriba.
3. ~~Recolectar los casos donde forzar dos archivos falló (D7).~~ **Ubicación entregada 2026-07-22:** `C:\Users\05147\OneDrive\Escritorio\Test_Asistente_ETL\Simplificado\Sol\02\Errores\` — `err1.ktr`, `err2.ktr`. Coincide con el "corpus de regresión" que ya mencionaba el handoff de Fragmentación. Ambos archivos referencian `InsertUpdate`, `DimensionLookup` y `sk_producto` (confirmado por búsqueda de texto, no analizado en profundidad — el análisis de contenido es trabajo de Track F1/F4, no de esta sesión). D7 queda desbloqueado para F2/F3.

---

## Abiertos (no bloquean el arranque del refactor, sí bloquean ítems puntuales)

### C.1 — Plan de variabilidad de dialecto SQL

Postgres queda como default decidido (D12), pero el soporte multi-motor no tiene plan: dónde vive la decisión de dialecto, qué construcciones dependen de motor más allá de `DISTINCT ON`, qué pasa si el usuario cambia de motor después de generar, dónde exactamente se notifica. Requiere sesión y plan propios — información crítica que se fija antes de generar.

### C.2 — Contrastar las reglas de fragmentación existentes contra D6-bis

El material de fragmentación (`handoff_fragmentacion_y_errores.md`) ya trae reglas de cuándo fragmentar, escritas antes de D6-bis. Hay que releerlas y separar las que responden a corrección estructural de las que responden a legibilidad o umbrales de tamaño — esas segundas se eliminan. Barato, y **bloquea Track F2** (diseño del corte): si no se hace antes, el pase nace contradiciendo la doctrina.

### C.3 — Verificaciones contra la base real (independiente del dialecto)

```sql
-- ¿existen las columnas que el WHERE/ORDER BY asumen?
SELECT table_name, column_name
FROM information_schema.columns
WHERE column_name IN ('stg_estado', 'stg_fecha_carga');

-- ¿la BD genera el sk ahora que el step ya no lo hace?
SELECT column_name, column_default, is_identity
FROM information_schema.columns
WHERE table_name = 'dim_producto' AND column_name = 'sk_producto';
```

**Resultado (2026-07-22):** la base sí genera `sk_producto` sola —
```json
{"column_name": "sk_producto", "column_default": "nextval('dim_producto_sk_producto_seq'::regclass)", "is_identity": "NO"}
```
Secuencia vía `DEFAULT`, no `IDENTITY`. **Esto solo protege si el `INSERT` omite la columna por completo.** Verificado contra el generador: `_step_InsertUpdate` (`backend/app/services/ktr_builder/steps/output.py:43-63`) arma la lista de `<value>` directamente desde `cfg["fields"]`, sin ningún filtro que excluya una clave técnica/surrogate — si el step que carga `dim_producto` emite un mapeo hacia `sk_producto` (aunque sea con un valor vacío), ese `INSERT` incluye la columna explícita y pisa el `DEFAULT`. La pregunta real no es "¿la base genera el sk?" (sí) sino "¿el step generado por el LLM alguna vez mapea algo a esa columna?" — eso depende del contenido de cada corrida, no es verificable en abstracto. `err1.ktr`/`err2.ktr` (ver D7, arriba) referencian `InsertUpdate` y `sk_producto` — candidatos para revisar esto en concreto cuando Track F1/F4 los analice. No es más "rotura esperando genérica"; es un caso puntual a confirmar contra esos dos archivos.

### C.4 — Auditoría retroactiva de cambios no declarados

El material de fragmentación es un **autorreporte de sesión**, no evidencia independiente: describe la división de KTR, pero la pérdida de SCD2 real y tres clases de cambio no declaradas (ver tabla de D9) no salieron a la luz hasta comparar los XML generados, varias sesiones después. Si el documento las hubiera declarado, no habrían sido un hallazgo — eso es justamente lo que D9 (registro de deltas) busca prevenir hacia adelante.

Falta hacerlo hacia atrás: por cada commit que tocó generación de KTR, comparar el mensaje del commit y lo declarado en la documentación contra el diff canónico (mismo método de D9, aplicado retroactivamente, mecánico). **Falta acotar el alcance** — hasta qué commit hacia atrás tiene sentido ir.

*Evidencia de que hace falta un chequeo así:* ya apareció un caso de afirmación no verificada en el material acumulado — se documentó que `_TABLE_FIELD_KEYS` vivía "suelto en `dimension_step_policy.py`"; verificado contra el repo, vive en `ktr_default_validator.py:54` (ver H4 en `01-hallazgos.md`).
