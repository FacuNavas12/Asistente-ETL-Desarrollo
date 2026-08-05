# Arquitectura objetivo

> Este archivo va al repo, en `docs/arquitectura-objetivo.md`, y se referencia desde `CLAUDE.md`.
> Es la doctrina: no describe el estado actual, describe el estado al que se converge.
> Todo prompt de auditoría o de implementación lo lee primero.

---

## Contexto del producto

Backend FastAPI + frontend React. El producto acelera la creación de procesos ETL en Pentaho.

Flujo funcional:

1. El usuario ingresa datos de entrada: orígenes, destinos, reglas de transformación.
2. El backend consume un modelo de lenguaje que devuelve una definición de *steps*.
3. El backend valida e interpreta esa respuesta.
4. A partir de los steps se generan los artefactos de Pentaho (`.ktr` / `.kjb`) y el linaje asociado.

---

## Por qué capas y no MVC

MVC nació para apps con vistas renderizadas en servidor. Con React la vista no vive en el backend, así que queda "MC", que en la práctica degenera en routers gordos con modelos anémicos.

La arquitectura objetivo es en capas con inversión de dependencias — Clean Architecture pragmática, apoyada en lo que FastAPI ya da: Pydantic como contrato de frontera y `Depends()` como mecanismo de inyección.

---

## Capas

| Capa | Contiene | Puede importar | Nunca |
|---|---|---|---|
| `api/` | Routers. Reciben request, delegan a un service, devuelven schema. | `schemas`, `services`, `core.deps` | Tocar DB, LLM o filesystem |
| `schemas/` | Modelos Pydantic. Contrato HTTP con React. | Nada del proyecto | Contener lógica de negocio |
| `services/` | Casos de uso. Orquestan el flujo. | `domain`, `ports` | Importar `fastapi`, SQLAlchemy o clientes concretos |
| `domain/` | Entidades y reglas puras: `Step`, `StepConfig`, `Transformation`, `Job`, resolución de tablas y campos. | Solo stdlib | Importar cualquier cosa de infraestructura |
| `ports/` | Interfaces (`Protocol` / ABC): `LLMProvider`, `StepRepository`, `ArtifactWriter`. | `domain` | Tener implementación |
| `infrastructure/` | Adaptadores: cliente LLM, parser y validador de su respuesta, generador XML de Pentaho, repos SQLAlchemy, lectura de uploads. | Todo | Ser importada directamente por `services` o `domain` |
| `core/` | Config, `Depends`, manejo de excepciones, logging, seguridad. | — | — |

Regla de lectura de la tabla: la dependencia siempre apunta hacia adentro. `infrastructure` conoce a `domain`; `domain` no conoce a nadie.

---

## Reglas invariantes

Están numeradas. Los reportes de auditoría citan el número.

**R1 — Dependencias hacia adentro.** Ningún módulo de `domain` o `services` importa `infrastructure`. La conexión se hace por `ports` + inyección.

**R2 — El router no toca la DB, ni el LLM, ni el disco.** Solo llama a un service.

**R3 — El service no importa `fastapi`.** Si necesita fallar, lanza una excepción de dominio; `core` la traduce a HTTP en un exception handler.

**R4 — No se saltean capas.** Si `api` llama a un repositorio directamente, es violación aunque funcione.

**R5 — Borde de entrada explícito.** Todo dato que viene de afuera del proceso — respuesta del LLM, filas de DB, uploads, configuración de usuario, variables de entorno — se parsea y valida **en `infrastructure`, en un único lugar por fuente**. Cruza hacia adentro como entidad tipada de `domain`, nunca como `dict` crudo, string con JSON adentro, ni estructura "a medio limpiar". Después del borde, el dato es válido por construcción y ningún módulo interior vuelve a chequearlo.

**R6 — Una sola representación por concepto.** Un `Step` tiene una única forma canónica en `domain`. Las variantes de transporte (JSON del LLM, fila de DB, XML de Pentaho) son proyecciones que viven en `infrastructure` y se convierten en un solo punto. Si el mismo concepto tiene dos definiciones en el código, una sobra.

**R7 — El conocimiento de dominio vive en `domain`, una sola vez.** Qué tabla toca cada step, qué campos tiene, qué alias resuelven a qué: eso es dominio. Si dos módulos tienen su propia tabla de campos, ya divergieron o van a divergir.

**R8 — El repositorio no decide.** Solo lee y escribe. Un `if` de negocio dentro de un repo pertenece a un service.

**R9 — El service no arma SQL ni abre archivos.** Si lo hace, es un repositorio disfrazado.

**R10 — Acoplamiento por tipo, no por orden de ejecución.** Si el paso B funciona solo porque el paso A corrió antes y dejó algo mutado, eso es una dependencia invisible. B debe recibir como argumento tipado lo que necesita. Prohibida la mutación in-place de estructuras compartidas para comunicar etapas.

**R10, forma positiva.** El pipeline de generación (`normalize_step_configs → repair_ktr_steps → repair_integrity_gaps → enforce_dimension_step_policy → split_ktr_by_cut → build_ktr`, ver `docs/auditoria/00-inventario.md` sección 3.6) es una secuencia de transformaciones sobre un valor inmutable: cada etapa recibe `(EtlDraft, list[Notification])` y devuelve `(EtlDraft, list[Notification])` nuevos. Ninguna etapa muta lo que recibe. El orden de ejecución deja de ser una dependencia invisible porque cada etapa declara en su firma qué necesita y qué produce — se puede leer la firma y saber si una etapa puede correr sola, sin ejecutar el pipeline completo para averiguarlo. `EtlDraft` no existe todavía; se diseña cuando esta regla se implemente (no en esta sesión — ver "Mapa capa-objetivo" abajo, fila `services/ktr_builder/*`).

**R11 — Prohibido el fallo silencioso.** Nada de `except Exception: return {}` ni `except: pass`. Un error se registra con contexto y se propaga como excepción tipada, o se maneja de forma explícita y documentada. Un default vacío que oculta un fallo convierte un bug de una capa en un síntoma tres capas más abajo.

*Detección vs. emisión (D15, `docs/refactor/02-decisiones.md`):* esta regla no prohíbe el best-effort — prohíbe el best-effort **mudo**. Hay dos formas legítimas de manejar un fallo, y un auditor que no las distinga marca como violación cada camino best-effort correcto. **Detección** es fail-fast: un dato de entrada inválido corta el flujo con una excepción tipada (ej. `ConfigParseError` en `parse_cfg`, `docs/auditoria/00-inventario.md` fila 1 de la tabla de sección 3.3). **Emisión** es mejor-esfuerzo-y-notifica: un chequeo opcional que no puede evaluarse (DDL con error de sintaxis, dataset que no existe todavía en Superset) sigue el flujo, pero dejando una entrada accionable en el canal de notificaciones (R12) — nunca solo un `logger.warning` que nadie fuera del servidor lee. Lo que R11 prohíbe es la tercera vía: un default vacío o un `continue` que no hace ninguna de las dos cosas. Censo completo de los tres casos, con ejemplos reales de cada uno: `docs/auditoria/00b-fallos-silenciosos.md`.

**R12 — El canal de notificaciones es un tipo, no una lista.** `Notification` es una entidad de `domain`: código estable, severidad, step y tabla afectados, y qué revisar. Se **devuelve** desde cada etapa (ver R10 forma positiva), no se appendea a una lista compartida que cualquier capa puede mutar. Ninguna capa modifica notificaciones producidas por otra. Un fallo que hoy se resuelve con `continue` o con un default vacío se resuelve devolviendo una notificación en su lugar.

Caso aplicado — `docs/auditoria/00b-fallos-silenciosos.md` sección 3.1 documenta el mismo `if not table: continue` sin avisar, reimplementado por separado en tres módulos (`fragmentation.py:79`, `dimension_step_policy.py:158`, `fields_validate.py:111`) que responden la misma pregunta ("¿qué tabla toca este step?") y descartan el caso vacío cada uno a su manera. Bajo R12, una sola `resolve_step_table(step) -> (tabla | None, Notification | None)` en `domain/` reemplaza a los tres — devuelve la notificación en vez de tragarla, y los tres call-sites la consumen. **No se implementa en esta sesión**: es el primer paso natural una vez que R12 se aplique, no antes (ver "Regla de migración" abajo).

---

## Mapa capa-objetivo ↔ directorio actual

Para cada directorio/archivo que existe hoy en `backend/app/`, a qué capa objetivo pertenece. Sin este mapa, cualquier auditoría de cumplimiento por capas (Fase A2, `docs/refactor/03-plan.md`) tiene que inventar el mapeo para poder calificar, y cualquier plan de remediación posterior corre el riesgo de leerse como "mover todo".

Este mapa es una fotografía de intención, no un compromiso de fecha: dice a dónde va cada archivo *cuando le toque* (ver "Regla de migración"), no que se vaya a mover ahora. Las filas marcadas **partido** son la parte más honesta del mapa — un archivo cuyo contenido ya pertenece a dos capas, sin que el código lo refleje todavía.

| Hoy | Capa objetivo | Nota |
|---|---|---|
| `routers/` | `api/` | Directo. Excepción ya corregida: `routers/schema.py::infer_schema` manejaba el tempfile del upload él mismo (R2) — **Ejecutado (O2-d)**, el borde pasó a `services/file_schema.py::infer_schema_from_upload`. `test_architecture_layers.py` no mide R2 (solo R1/R3/R4 en su recorte, ver su docstring) — por eso esto no vivía en ningún `FROZEN_*`; era un hueco del radar, no deuda registrada. `routers/ai.py` y `routers/connections.py` siguen con violaciones de R2 más amplias que R4 solo (`db.commit()`/`db.rollback()` directo en el router) — esas sí están cubiertas por `FROZEN_R4` en su parte de ORM, pero R2 en general sigue sin test. |
| `schemas/` (excepto `llm_output_schemas/`) | `schemas/` | Contrato HTTP. Directo — con la excepción nombrada de `canonical.py` reexportando `domain/canonical_types.py` (ver fila siguiente, ejecutado). |
| `schemas/llm_output_schemas/` | `infrastructure/llm/` | Es el contrato de una fuente externa, no de la API. |
| `domain/canonical_types.py` (`CanonicalType`, `FieldFormat`, `ColumnRole`) | `domain/` | **Ejecutado** (cierre de la sesión de arquitectura, split de `registry.py`): primer archivo físico de `domain/`. Movidos desde `schemas/canonical.py`, que los reexporta con excepción nombrada por símbolo (motivo: value objects puros de stdlib — `str, Enum`/`Literal`, cero Pydantic). |
| `models/anthropic_llm.py`, `gemini_llm.py`, `llm_factory.py`, `llm_base.py` | `infrastructure/llm/` | `llm_base.BaseLLM` es un ABC — hoy cumple el rol que `ports/` debería cumplir formalmente (ver "Sobre-especificación" abajo: es la prueba de que un puerto real se justifica acá). |
| `models/` (ORM: `etl`, `job`, `connection`, `ktr_build_job`, `base`) | `infrastructure/persistence/` | `models/` mezcla dos capas bajo un nombre. Ese nombre debería desaparecer. |
| `repositories/`, `core/database.py` | `infrastructure/persistence/` | |
| `outbox/` | `infrastructure/outbox/` | |
| `services/adapters/` + `file_schema.py` | `infrastructure/schema_sources/` | 3 implementaciones convergiendo en `CanonicalSchema`. |
| `services/db_connector.py`, `dialect.py`, `profiler.py`, `masker.py` | `infrastructure/db_inspection/` | |
| `services/superset_client/`, `superset_export/` | `infrastructure/superset/` | |
| `services/ktr_builder/build.py`, `steps/*`, `layout.py`, `connection.py` | `infrastructure/pentaho/` | Serialización a XML: proyección, no dominio (R6). |
| `services/ktr_xml_validator.py`, `kjb_xml_validator.py`, `ktr_builder/error_catalog_checks.py` | `infrastructure/pentaho/` | Validan XML ya serializado. `error_catalog_checks.py` (auditoría catálogo E1-E14) no estaba en la hipótesis original — mismo criterio que los otros dos: solo importa `dataclasses` y `xml.etree`, cero conocimiento de dominio, opera sobre el XML final. |
| `services/ktr_builder/contracts.py` | `domain/` | Conocimiento de dominio puro (R7). Verificado: solo importa stdlib + `common._yn` (ver fila `common.py`). |
| `services/ktr_builder/fragmentation.py` | `domain/` | Ya declarado así en este documento. Verificado: solo importa `contracts` (domain). |
| `services/ktr_builder/dimension_step_policy.py`, `validate.py`, `fields_validate.py` | `domain/` | Reglas puras, verificadas: no importan infra. `validate.py` importaba `STEP_TYPE_ALIASES` de `registry.py` (excepción real, congelada) — resuelto al ejecutar el split (fila `step_types.py`/`step_emitters.py` abajo): ahora importa `step_types.py`, domain→domain, cero excepción. |
| `services/ktr_builder/ktr_default_validator.py` | `domain/` | **No estaba en la hipótesis original.** Verificado: solo importa `contracts.parse_cfg` y `sql_defaults.looks_like_sql_function` (ambos domain), cero infra. Scrub de constantes con función SQL + chequeo de NOT NULL sin mapeo son reglas puras. |
| `services/ktr_builder/common.py` | `domain/` | **Ejecutado (O2-a).** `_yn`/`KtrBuilderError` puros, quedan acá. `_sub` (armaba `xml.etree.ElementTree.Element`) se movió a `services/ktr_builder/xml_helpers.py` → `infrastructure/pentaho/`. Igual que `step_types.py`: domain por criterio, físicamente queda en `services/ktr_builder/` — no es vocabulario compartido fuera del paquete (ver `domain/README.md`). |
| `services/ktr_builder/xml_helpers.py` | `infrastructure/pentaho/` | Mitad infra del split de `common.py` (O2-a): `_sub`, único helper de `xml.etree.ElementTree`. |
| `services/ktr_builder/step_types.py` | `domain/` | **Ejecutado.** Mitad domain de `registry.py` (borrado): `STEP_TYPE_ALIASES` (identidad de tipo) + `_CRITICAL_FIELDS` (completitud mínima, gate real en `build.py`). Cero imports de proyecto. |
| `services/ktr_builder/step_emitters.py` | `infrastructure/pentaho/` | **Ejecutado.** Mitad infra de `registry.py`: imports de `steps/*` + `STEP_BUILDERS` (tipo canónico → función XML) + `STEP_CONFIG_KEYS`/`unmapped_config_keys` — reclasificados de `domain/` a infra en el cierre de la sesión: auditan capacidad presente del builder ("qué claves SÍ mapea a XML"), no un invariante de dominio. `KNOWN_PDI_STEP_TYPES` no se movió a ningún lado: se borró — nunca se consultaba en runtime (`build.py` rechaza por `STEP_BUILDERS.get() is None`, no por whitelist); la coherencia prompt↔alias↔builder que prometía documentar sin verificar ahora la cubre `backend/tests/test_pdi_step_coherence.py`. |
| `services/lineage_builder.py` | **Ejecutado (O2-c).** `build_lineage`/`stitch_lineage_many`/`stitch_lineage` (puros sobre el dict KTR) se movieron a `domain/lineage.py`, devolviendo `LineageGraphData` (dataclass stdlib) en vez de `schemas.lineage.Lineage` (Pydantic — no puede vivir en `domain/`, ver ese README). `services/lineage_builder.py` queda como borde: envuelve `LineageGraphData` en `Lineage` para la API y conserva `_parse_ktr_xml` (lee XML ya serializado, camino inverso de `/api/ai/lineage-from-ktr`) — infra, no se movió a `infrastructure/pentaho/` físico (no existe ese paquete todavía; mismo criterio que `common.py`/`step_types.py`: domain por criterio, físico donde ya estaba). |
| `services/sql_defaults.py` | `domain/` | Verificado: solo stdlib. |
| `services/type_mappings.py` | `infrastructure/db_inspection/` | **Reclasificado (cierre de la sesión).** No es domain: traduce vocabulario de un vendor concreto (Postgres/SQL Server, alimentado por `db_connector._format_type()`) y solo lo consume otro adaptador (`db_adapter.py`) — ningún módulo de dominio depende de `map_sql_type`. Importa `CanonicalType`/`FieldFormat` directo de `domain/canonical_types.py` (infra puede importar todo). El criterio que resuelve por qué esto es infra y `STEP_TYPE_ALIASES` es domain, pese a que ambos "traducen nombres externos", está en `CLAUDE.md`: el dominio de esta aplicación es la generación de KTR — vocabulario PDI es dominio, lo externo a PDI (DB origen, proveedor LLM) es infraestructura. |
| `services/ktr_builder/repair.py` | `services/` | **Decisión de esta sesión** (la hipótesis original pedía elegir y justificar). `repair.py` llama al LLM — no puede ser dominio — pero recibe `llm: BaseLLM` **por parámetro** (`repair.py:21`, ya inyectado por el caller, nunca instanciado adentro). Eso es exactamente el patrón de un caso de uso que depende de un puerto, aunque `BaseLLM` no viva físicamente en `ports/` todavía. `services/` (no `infrastructure/llm/`) porque lo que hace — decidir qué steps reparar, reintentar, agregar warnings accionables — es orquestación de caso de uso, no el cliente LLM en sí (ese ya está en `models/anthropic_llm.py`/`gemini_llm.py`). |
| `services/etl_generator.py` (1188 líneas) | **partido** | Ver README propuesto en `backend/app/services/README.md` y el corte E4 abajo. |
| `services/etl_service.py`, `job_service.py`, `structure_inferrer.py`, `ddl_validation.py`, `context_builder.py`, `documenter.py`, `validator.py`, `job_analyzer.py` | `services/` | Casos de uso. Nota de debt no resuelta acá: `etl_service.py`/`job_service.py` importan `fastapi.HTTPException` directo (R3) y `context_builder.py`/`structure_inferrer.py`/`etl_generator.py` importan `sqlalchemy.orm.Session` directo — la tabla de Capas dice "Nunca" para ambos casos. Es deuda real, extendida (9 archivos de `services/` importan SQLAlchemy directo, ver evidencia de sesión), fuera del recorte del test de arquitectura de esta sesión (ver `backend/tests/test_architecture_layers.py`, docstring) — candidato natural para Fase A3 (bordes) o A4 (acoplamiento). |
| `core/` | `core/` | Directo. |

---

## Regla de migración (el reemplazo del big-bang)

**Código nuevo nace en su capa objetivo.** Código existente se mueve **solo cuando ya se lo va a tocar por otra razón** — un fix, una fase del plan. Nunca hay una sesión cuyo único objetivo es mover archivos. El mapa de arriba es la referencia que dice a dónde va un archivo cuando le toque, no una orden de moverlo ahora.

Consecuencia práctica: mientras dure la convivencia entre la estructura actual y la de capas, `backend/tests/test_architecture_layers.py` corre en modo "no empeorar" — falla si aparece una violación nueva de las reglas que cubre (R1/R3/R4 en su recorte, ver docstring del test), no por las que ya existen. Esas están en las listas `FROZEN_*` del test, que solo pueden achicarse: cuando un archivo se mueve o se corrige por otra razón, la entrada congelada correspondiente se borra en ese mismo cambio — nunca queda una entrada que ya no reproduce (el propio test lo verifica: `test_frozen_lists_have_no_stale_entries`).

---

## Dónde va el código nuevo

Preguntas en orden para ubicar cualquier archivo:

1. ¿Habla HTTP? → `api/` (router) o `schemas/` (contrato).
2. ¿Habla con algo fuera del proceso — DB, LLM, disco, red? → `infrastructure/`, detrás de una interfaz en `ports/`.
3. ¿Es una regla que seguiría siendo cierta si cambiara la DB y el proveedor del modelo? → `domain/`.
4. ¿Coordina varios de los anteriores para cumplir un caso de uso? → `services/`.
5. ¿Ninguna de las anteriores? Probablemente no tenés claro qué hace. Definilo antes de escribirlo.

---

## Ejemplo aplicado — el motor de fragmentación

Referencia de trabajo, no doctrina nueva: cómo caen las cinco preguntas de arriba sobre la decisión ya tomada en `docs/refactor/02-decisiones.md` (D6, D6-bis) de que el backend decide, de forma determinística, cuántos `.ktr` materializan cada fase lógica del ETL.

- La matriz step × tabla × {lee, escribe} y el algoritmo de corte (componentes conexos, orden por grafo de FK) son reglas que siguen siendo ciertas sin importar qué DB o qué proveedor de LLM esté detrás → **`domain/`**.
- Coordinar ese razonamiento con la lectura de `STEP_CONTRACTS` (conocimiento de dominio, R7) y disparar la escritura de N archivos `.ktr` + KJB es un caso de uso completo ("generar ETL") → **`services/`**.
- Cuántos `<transformation>` o `<job>` resultan, y cómo se serializan a XML, es una proyección de infraestructura (R6): la entidad de dominio no sabe que existe un archivo físico → **`infrastructure/`**.

**Alcance de la regla, no de la capa (D6-bis):** la fragmentación corta solo por señal estructural — una tabla escrita y leída en la misma fase, doble escritor sobre la misma tabla. No hay umbral de tamaño ni criterio de legibilidad. Ninguna cuenta de "cuántos steps tiene este archivo" pertenece a `domain/` como regla de corte; si apareciera, sería una violación de D6-bis antes que un problema de ubicación de capa.

Las decisiones y su evidencia viven en `docs/refactor/02-decisiones.md` — este documento no las repite, solo señala dónde caen en el modelo de capas de arriba.

---

## Qué está sobre-especificado hoy

Honestidad como parte del entregable: no todo lo que la tabla de Capas nombra se justifica siempre. Regla concreta para `ports/`: **puerto donde hay segunda implementación real o doble de test que de otro modo duela; adaptador directo en el resto.** Un `Protocol`/ABC que envuelve una sola implementación, sin que ningún test necesite reemplazarla, no separa nada — agrega un archivo a leer antes de llegar al código real.

Aplicando la regla a lo que ya existe:

- **`LLMProvider` — se justifica.** `models/llm_base.py:BaseLLM` ya es un ABC con dos implementaciones reales (`anthropic_llm.py`, `gemini_llm.py`), seleccionadas en runtime por `llm_factory.build_llm()` según `LLM_PROVIDER`. El puerto no se está proponiendo — ya existe en la práctica, solo falta el traslado físico a `ports/` (que le toca cuando alguien lo toque, no ahora).
- **`SchemaSource` — se justifica.** Tres implementaciones convergiendo en `CanonicalSchema` (`services/adapters/db_adapter.py`, `frictionless_adapter.py`, `ddl_adapter.py`), cada una con su propia fuente externa (BD real, archivo subido, DDL pegado). Mismo caso que `LLMProvider`: el puerto describe algo que el código ya hace, sin nombre formal todavía.
- **`StepRepository` sobre SQLAlchemy para `Etl`/`Job` — es ceremonia.** Verificado: `repositories/base.py` (`:10-38`) es una clase genérica concreta sobre `sqlalchemy.orm.Session`, sin `Protocol` ni implementación alternativa; `etl_repository.py`/`job_repository.py` son 4 líneas cada uno, solo instancian `BaseRepository(Etl)`/`BaseRepository(Job)`. Los tests que la ejercitan (`docs/auditoria/00-inventario.md` sección 6: `test_etl_job_crud.py`, `test_ktr_build_job_api.py`) ya corren contra un engine SQLAlchemy real en SQLite en memoria — nadie necesita un doble, porque la versión real ya es rápida y no toca red. Envolver esto en un `Protocol` de `ports/` no habilita ningún test que hoy sea imposible; sería la interfaz por la interfaz misma.
- **`ArtifactWriter`** (mencionado en la tabla de Capas como ejemplo de `ports/`) — no tiene código real detrás todavía (la escritura de `.ktr`/`.kjb` hoy es `build_ktr()`/`build_kjb_xml()` devolviendo XML en memoria, sin abstracción de dónde se persiste). No hay nada que evaluar: ni se justifica ni sobra, porque no existe. Queda nombrado en la tabla como aspiracional, no como deuda.

No se encontró sobre-especificación fuera de `ports/` en esta sesión — el resto de la doctrina (capas, R1-R12) describe restricciones, no aparato; no hay una interfaz de más que señalar en `domain/`, `services/` o `infrastructure/` tal como están descriptos hoy.

---

## Verificación

La arquitectura está bien si estas tres cosas son ciertas:

- Se puede testear un service con un repositorio falso, sin levantar DB ni llamar al modelo.
- Se puede agregar un conector o un tipo de step nuevo sin tocar `services/` ni `domain/`.
- Un error de datos del LLM se detecta en el borde, con mensaje que dice qué campo falló, no tres capas más abajo.

Si escribir el test es fácil, la arquitectura quedó bien. Ese es el indicador, no el diagrama.

---

## Deuda técnica aceptada

<!-- Se completa al cerrar la Fase 6. Cada entrada: qué, por qué se acepta, qué la destrabaría. -->
