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

**R11 — Prohibido el fallo silencioso.** Nada de `except Exception: return {}` ni `except: pass`. Un error se registra con contexto y se propaga como excepción tipada, o se maneja de forma explícita y documentada. Un default vacío que oculta un fallo convierte un bug de una capa en un síntoma tres capas más abajo.

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

## Verificación

La arquitectura está bien si estas tres cosas son ciertas:

- Se puede testear un service con un repositorio falso, sin levantar DB ni llamar al modelo.
- Se puede agregar un conector o un tipo de step nuevo sin tocar `services/` ni `domain/`.
- Un error de datos del LLM se detecta en el borde, con mensaje que dice qué campo falló, no tres capas más abajo.

Si escribir el test es fácil, la arquitectura quedó bien. Ese es el indicador, no el diagrama.

---

## Deuda técnica aceptada

<!-- Se completa al cerrar la Fase 6. Cada entrada: qué, por qué se acepta, qué la destrabaría. -->
