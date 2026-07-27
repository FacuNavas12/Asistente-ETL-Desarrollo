# Verificación pendiente — deuda que envejece mal

**Mutable** en la columna `Estado`; el resto de cada fila es append-only (agregar contexto, no reescribir el diagnóstico).

**Qué cuenta:** todo cambio cuyo efecto no lo captura la suite determinista — reglas de `system_etl.txt`, cualquier cosa que dependa de la respuesta del LLM, supuestos sobre motores externos (Kettle, Postgres, pooler de Supabase).

**Por qué necesita mecanismo propio:** el resto de la deuda envejece bien (una decisión sin tomar sigue igual en tres meses); esta no. Una corrida real ejercita todas las reglas a la vez — cuantas más se acumulan sin verificar, más caro es atribuir un fallo a una regla concreta.

**Cómo se cierra:** no es que un humano lea el `.ktr` — son los checkers deterministas del propio backend (`error_catalog_checks`, `ktr_xml_validator`, `enforce_dimension_step_policy`, `compute_cut`). Una corrida verifica una regla solo si existe un checker que la mira. Si no existe, escribirlo primero convierte el ítem en deuda de *trabajo* (fila en `03-plan.md`), no de verificación.

**Tope: 3 reglas sin verificar simultáneas.** Al llegar al tope, la próxima sesión de F4 es una corrida de verificación, no una regla nueva. Este registro ya está en el tope con las 3 filas de abajo — no agregar una cuarta regla de prompt sin verificar sin cerrar al menos una de estas primero.

**Orden:** por irreversibilidad del daño silencioso, no por antigüedad.

| Regla | Dónde vive | Qué checker la verificaría | ¿Existe? | Daño si falla | Estado |
|---|---|---|---|---|---|
| Loader dedicado de una dimensión (upsert por clave natural) sobrescribe la fila placeholder de miembro inferido cuando el producto real llega | D21 (`02-decisiones.md`), depende de `scd_type` en `dim_contracts` | Corrida real: insertar hecho con FK inferida, cargar el producto real en un batch siguiente, confirmar que la fila placeholder se actualiza (no queda huérfana) | No | **Silencioso e irreversible** — si el loader es insert-only para alguna dimensión, el miembro inferido queda huérfano para siempre, nada lo detecta hoy | Sin verificar |
| B17 — todos los operandos de `Calculator`/`Formula` deben declararse `BigNumber`, no solo el resultado | `system_etl.txt` checklist ítem 25 | `v11_monetario_sin_bignumber` (`error_catalog_checks.py`, `MONEY_FIELD_HINTS` ya extendido) | Sí — pero nunca corrió una generación real *después* de agregar B17 (la corrida que confirmó E14 vivo fue anterior) | Visible si el checker corre (ya existe) — el riesgo es no saber todavía si B17 cambió el comportamiento real del LLM | Pendiente de corrida confirmatoria |
| Aritmética Kettle detrás de B17: ¿alcanza con que UN operando sea `BigNumber` para que Kettle promueva a `BigDecimal`, o hacen falta todos? (`Calculator.java`/`ValueDataUtil.java`/libformula real, no inferencia IEEE 754 general) | H27 (`01-hallazgos.md`) | Ninguno posible sin leer código fuente de Kettle o correr un caso real contra el motor | No | **No bloqueante** — la regla actual (todos `BigNumber`) es conservadora, nunca produce falso negativo; el daño de no verificar es como mucho sobre-ingeniería, no un dato mal calculado | Sin verificar, no urgente |
