# Fase 0.5 — Censo de fallos silenciosos

Censo de puntos del backend (`backend/app/`) donde un error se traga, se degrada a un valor por defecto, o se resuelve sin dejar rastro accionable — contra la doctrina ya fijada en `02-decisiones.md` (D5: ante la duda, fallar visible; D15: fail-fast en detección / mejor-esfuerzo-y-notifica en emisión; D9/D13: todo cambio no pedido por el usuario tiene que aparecer en el canal de warnings de la corrida) y R11 (`arquitectura-objetivo.md:70`: "Prohibido el fallo silencioso... Un default vacío que oculta un fallo convierte un bug de una capa en un síntoma tres capas más abajo"). Descriptivo, sin proponer fixes — eso es Fase 2/5 de Track A. Toda afirmación con `archivo:línea`; sin ejecutar el sistema, salvo donde se marca explícito.

**Método:** `grep` de `except`/`continue` sobre los 44 archivos de `backend/app/` que los usan (114 + ~60 ocurrencias respectivamente), cada uno leído en contexto y clasificado según a dónde va la información del fallo: a ningún lado (silencio total), a un log de servidor (invisible para el usuario final y para el propio pipeline de warnings), o al canal de `warnings`/`notifications` que D13/D15 exigen (correcto, no es hallazgo). Cruzado contra `01-hallazgos.md` para no reabrir H6/H12/H26, ya catalogados y con estado propio.

---

## 1. Taxonomía de clasificación

| Categoría | Qué significa | ¿Es hallazgo nuevo? |
|---|---|---|
| **C1 — Silencio total** | `except`/chequeo sin ningún `log`/`logger` y sin entrada en ningún `warnings`/`notifications` | Sí, la más grave |
| **C2 — Logueado, sin canal de usuario** | Hay `logger.warning`/`.error`, pero el dato del fallo no llega a ningún `warnings`/`notifications` que el pipeline devuelva — solo lo ve quien lee logs de servidor | Sí |
| **C3 — Notificado correctamente** | El fallo termina en `warnings`/`notifications` (D13/D15) o en un campo de respuesta explícito (ej. `sync_status`, `success=False`) | No — contraejemplo, listado para contraste |
| **C4 — Ya catalogado** | Ya tiene entrada propia en `01-hallazgos.md`, con estado (resuelto/abierto) | No — se referencia, no se duplica |

---

## 2. C1 — Silencio total (sin log, sin notificación)

### 2.1 `services/superset_client/datasets.py:45-57` (`create_datasets_from_zip`)

```python
already_exists = False
try:
    check = await client.get(...)
    if check.status_code == 200 and check.json().get("count", 0) > 0:
        already_exists = True
except Exception:
    pass
```

Cualquier excepción al chequear si el dataset ya existe en Superset (auth vencida, timeout, respuesta no-JSON, cambio de API) se trata exactamente igual que "el dataset todavía no existe" — el código sigue e intenta crearlo. El comentario de la línea 43-44 documenta que el operador `DatasetUUID` puede no existir en Superset 6.x y que "si falla, intentamos crear igualmente" — decisión consciente para ESE caso puntual, pero el `except Exception` de alcance amplio también traga cualquier otro fallo (red caída, 500 del lado de Superset) sin distinguirlo. Sin `logger`, ni siquiera queda rastro en el log del servidor.

### 2.2 `services/db_connector.py:169-205` (`_estimated_count`)

```python
def _estimated_count(session, schema: str, table: str, db_type: DbType) -> int:
    """... Returns -1 if statistics are not yet available or inaccessible."""
    try:
        ...
    except Exception:
        return -1
```

El docstring documenta `-1` como "estadísticas no disponibles" — pero el `except Exception` de línea 204 no distingue esa causa de cualquier otra (columna renombrada, permiso denegado, tabla borrada entre el `list_tables` y esta llamada). Sin log. El valor sí se propaga con criterio downstream (`get_table_data`, `db_connector.py:620`: `total_pages = ... if total > 0 else -1`, y `count_is_estimate=True` viaja en `TableDataResponse`) — el consumidor sabe que es estimado, pero no que la estimación específicamente *falló* en vez de simplemente no estar disponible.

### 2.3 `services/db_connector.py:366-384` (`_primary_key_columns`)

```python
def _primary_key_columns(session, schema: str, table: str) -> set[str]:
    """PK vía information_schema (ANSI, PG + SQL Server). Best-effort: set vacío si falla."""
    try:
        ...
        return {r[0] for r in rows}
    except Exception:
        return set()
```

Mismo patrón: "best-effort" documentado, pero un error real de query (no solo "esta tabla no tiene PK") es indistinguible de "no tiene PK" para el caller (`db_connector.py:414`, usado para armar los badges de PK que ve `InputConnection.jsx` en el frontend). Sin log.

---

## 3. C2 — Logueado, sin canal de notificación al usuario/pipeline

### 3.1 El motor de corte (Track F) excluye steps de su propia matriz sin avisar — contradice su propio docstring

`services/ktr_builder/fragmentation.py:55-68` (`build_rw_matrix`):

```python
def build_rw_matrix(ktr_data: dict, step_type_aliases: dict[str, str]) -> dict[str, dict[str, str]]:
    """{tabla_lower: {step_name: "R"|"W"|"RW"}}. Steps sin tabla o ExecSQL no aportan."""
    matrix: dict[str, dict[str, str]] = {}
    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        table = (cfg.get("table") or "").strip()
        if not table:
            continue                      # ← sin log, sin entrada en notifications
        rw = _step_rw(canonical, cfg)
        if rw is None:
            continue                      # ← ExecSQL: ídem
        matrix.setdefault(table.lower(), {})[step.get("name", "")] = rw
    return matrix
```

El docstring del módulo (`fragmentation.py:12-14`) afirma: *"ExecSQL y steps sin tabla no participan (D15: notifica, no bloquea)."* Leído `compute_cut()` completo (`fragmentation.py:121-253`) — el único productor de `notifications` en toda la función — ninguna de sus tres ramas (V2/lookup-sin-productor, self-lookup/patológico, ciclo de orden) cubre este caso. Un step excluido acá (`table` vacío, o tipo `ExecSQL`) desaparece de `matrix` sin dejar ninguna entrada en `notifications`. La promesa del docstring ("notifica") no está implementada — solo la mitad ("no bloquea") es cierta.

**Por qué importa más que un typo de documentación:** esto es exactamente el mecanismo que `H6`/`contracts.parse_cfg` fue diseñado para prevenir — el propio docstring de `parse_cfg` (`contracts.py:43-46`) dice textualmente *"un `{}` en silencio hace que el step se vuelva invisible para la matriz R/W... exactamente el fallo silencioso que D5 prohíbe"*. H6 cerró la vía "config no parsea → `{}`". Esta es una vía distinta y no cerrada: la config parsea bien (es un dict válido), pero el campo `table` específicamente viene vacío o ausente — mismo efecto (step invisible para el corte), vía distinta, sin fix. Bajo D6-bis/D7, el motor de corte existe para detectar exactamente las races/dobles-escritores que motivaron el refactor completo (`err1.ktr`/`err2.ktr`, H21) — un step que toca una tabla real pero queda fuera de la matriz por un campo `table` no resuelto es un punto ciego estructural en la pieza más nueva del propio refactor (escrita 2026-07-24).

**Mismo patrón, duplicado en otros dos módulos que también razonan sobre "step → tabla":**

- `services/ktr_builder/dimension_step_policy.py:156-160` (dentro de `enforce_dimension_step_policy`):
  ```python
  cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
  table = (cfg.get("table") or "").strip()
  if not table:
      continue
  ```
  Un step que debería recibir su tipo SCD1/SCD2 (`derive_dimension_step_type`, D16) pero cuyo `table` viene vacío queda sin corregir, en silencio — ni un `logger.info` como los que sí existen dos líneas más abajo para el caso de override (`dimension_step_policy.py:185-188`, `238-241`).

- `services/ktr_builder/fields_validate.py:418-425` (dentro de `validate_dimension_lookup_races`):
  ```python
  for step in ktr_data.get("steps", []):
      canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
      if canonical not in ("DimensionLookup", "CombinationLookup", "DBLookup"):
          continue
      cfg = _parse_cfg(step.get("config", {}))
      table = (cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or "").strip().lower()
      if not table:
          continue
  ```
  Mismo gap, en el chequeo de races de lookup de dimensión.

Los tres módulos son consumidores independientes del mismo dato (D8: "qué tabla toca un step... vive en un único lugar") y los tres reimplementan, cada uno por su cuenta, el mismo `if not table: continue` sin notificar — no hay una sola función compartida que decida "este step no resolvió tabla, hay que avisar", a pesar de que D8 ya identificó y cerró (H4) la duplicación de *cómo* se resuelve el alias de tabla. Lo que falta centralizar no es la resolución del alias (ya centralizada), sino la reacción cuando la resolución da vacío.

### 3.2 `services/adapters/ddl_adapter.py` — tablas y FKs que no parsean se descartan del resultado, no del error

- `parse_ddl` (`ddl_adapter.py:126-139`): si una sentencia `CREATE TABLE` individual falla al construir su `CanonicalSchema`, `logger.warning(...)` y sigue con la próxima — la tabla simplemente no aparece en la lista devuelta. El endpoint `POST /api/schema/from-ddl` (`routers/schema.py:104-141`) no tiene forma de decirle al usuario "pegaste 3 tablas, se devolvieron 2" — ve una lista más corta sin explicación.
- `_extract_fk_ref` (`ddl_adapter.py:269-294`): una `FOREIGN KEY` que falla al parsearse → `logger.warning(...)` + `return None` — la tabla se construye igual, sin esa FK. `InputDDL.jsx` (frontend, fuera de este censo pero consumidor directo) muestra badges de FK/PK derivados de acá; una FK perdida así es indistinguible de "el DDL nunca declaró esa FK".

### 3.3 `services/etl_generator.py` — cinco chequeos "best-effort" que se apagan juntos ante el mismo fallo de parseo

Todas comparten idéntico patrón (`try: parse_ddl(...) except Exception as exc: _log.warning(...); return []`/`{}`):

| Función | Líneas | Qué deja de reportar si el DDL no parsea |
|---|---|---|
| `_required_columns_from_ddl` | `etl_generator.py:65-85` | Columnas `NOT NULL` sin default — insumo del validador de campos obligatorios |
| `_column_types_from_ddl` (→ `_type_mismatch_warnings`) | `etl_generator.py:88-105`, `118-157` | Incoherencias de tipo string/integer/number/boolean entre STG y DWH |
| `_staging_table_names_from_ddl` | `etl_generator.py:160-173` | Nombres de tabla STG usados para alinear las 2 llamadas al LLM y costurar linaje |
| `_dim_contracts_anomaly_warning` | `etl_generator.py:207-231` | Aviso de `dim_contracts` vacío pese a que el DWH declara tablas `dim_*` |
| `_dims_with_inferred_member` | `etl_generator.py:234-247` | D21: dimensiones con FK `NOT NULL` que necesitan miembro inferido |

Cada una está documentada en su propio docstring como "best-effort, nunca corta el flujo" — decisión consciente, consistente con D15. Pero el efecto agregado no está documentado en ningún lado: **un único DDL con un error de sintaxis apaga los cinco chequeos a la vez**, y el `.ktr` resultante sale sin ninguna de esas cinco señales, indistinguible de un `.ktr` donde los cinco chequeos corrieron limpio y no encontraron nada. El `logger.warning` de cada una queda en el log de servidor; ninguna agrega una entrada a los `warnings` que sí viajan hasta el usuario (los mismos que sí usa `_dim_contracts_anomaly_warning` cuando el chequeo SÍ corre pero encuentra una anomalía). No hay un "el chequeo X no pudo evaluarse" en el vocabulario de warnings — solo "corrió y no encontró nada" o "corrió y encontró esto".

### 3.4 `services/lineage_builder.py:236-240` (`_parse_ktr_xml`) — XML inválido en el linaje devuelve grafo vacío, no error

```python
try:
    root = ET.fromstring(ktr_xml)
except ET.ParseError as exc:
    logger.error("lineage: XML inválido — %s", exc)
    return {}
```

Camino usado por `POST /api/ai/lineage-from-ktr` (`routers/ai.py:407-420`, `build_lineage_from_xml`/`stitch_lineage_from_xml`). El endpoint devuelve `200 OK` con un `Lineage` vacío tanto si el `.ktr` subido no tiene steps como si el XML no pudo parsearse — el llamador no puede distinguir "grafo vacío real" de "no se pudo leer el archivo".

### 3.5 `routers/connections.py:175-190` (`test_connection`) — fallo al persistir el resultado del test se descarta

```python
conn = _get_owned_or_404(...)
result = svc_test(conn, password)
try:
    conn.last_test_status = TestStatus.success if result.success else TestStatus.failed
    conn.last_tested_at = datetime.now(timezone.utc)
    db.commit()
except Exception:
    db.rollback()
return result
```

El resultado real del test (éxito/fracaso, con mensaje) sí llega al usuario vía `result` — eso está bien. Pero si el `commit()` que graba `last_tested_at`/`last_test_status` en la conexión guardada falla (DB caída, lock), el `except` lo descarta sin log y sin cambiar la respuesta — el usuario ve "conexión exitosa" pero la ficha de la conexión no refleja que se probó.

### 3.6 `services/structure_inferrer.py:36-66` (`_safe_format_source`) — degradación en dos niveles, el segundo sin log

```python
try:
    ...
    return context_builder.format_model_context_for_prompt(ctx)
except Exception as exc:
    logger.warning("Could not parse source_structure for whitelisting: %s", exc)

try:
    parsed = json.loads(source_structure)
    ...  # strip 'data' fields
    return json.dumps(parsed, ensure_ascii=False, indent=2)
except Exception:
    return "[estructura de origen no disponible]"
```

Primer nivel de fallback logueado; segundo nivel (línea 65-66) no. El resultado final entra directo al prompt de `/api/v1/etl/infer-structures` (`_build_infer_prompt`) — si ambos niveles fallan, el LLM recibe el placeholder literal sin que quede ningún rastro de que la estructura de origen se perdió por completo para esa corrida. Nota aparte, no un hallazgo de seguridad: el fallback sí sigue cumpliendo el invariante de "nunca filas crudas al LLM" (hace `col.pop("data", None)` antes de serializar) — el problema es solo la falta de rastro cuando se llega al placeholder.

---

## 4. C3 — Notificado correctamente (contraejemplos, para contraste de diseño)

Listados porque establecen el patrón contra el que se mide todo lo de arriba — mismo tipo de degradación, con canal de aviso real:

- **`contracts.parse_cfg`** (`ktr_builder/contracts.py:38-54`) — fail-fast real: lanza `ConfigParseError` en vez de degradar (H6, resuelto). `normalize_step_configs` (`contracts.py:399-426`) es el único punto de captura, y sí agrega a `warnings`.
- **`ktr_builder/build.py:495-498, 523-526, 606-608, 619-621`** — catches de respaldo que o bien agregan a `warnings` con texto accionable ("Revisar este step antes de ejecutar en Spoon"), o re-lanzan como `KtrBuildError` con el dato crudo preservado para reintento manual.
- **`ktr_builder/connection.py:160-168`** (`resolve_real_connections`) — `conn_id` inválido o no encontrado → `warnings.append(...)` con el nombre lógico de la conexión afectada, nunca silencioso.
- **`ktr_builder/repair.py:113-133`** (`repair_step_config`) — `None` en caso de fallo, pero el caller (`repair_ktr_steps:167-178`) SÍ agrega un warning accionable si los reintentos se agotan.
- **`services/job_analyzer.py:483-501`** — un archivo `.ktr` subido que no parsea se agrega a `warnings` (visible en la respuesta) y se sigue con el resto; solo aborta (`raise ValueError`) si ninguno de los archivos parseó.
- **`outbox/drainer.py:100-119`** — distingue transitorio (reintenta, log `warning`) de permanente (`mark_failed`, log `error`) — y a diferencia de todo lo de arriba, el estado SÍ llega al usuario: `EtlRead.sync_status` (`schemas/etl.py:28-36`) expone `pending`/`synced`/`failed` en la respuesta de la API, no solo en el log.
- **`models/gemini_llm.py`/`anthropic_llm.py`** — fallback a modo texto logueado explícitamente, o `RuntimeError` final tras agotar reintentos — nunca un valor vacío silencioso.

---

## 5. C4 — Ya catalogado en `01-hallazgos.md` (no se duplica acá)

| Hallazgo | Relación con este censo |
|---|---|
| **H6** | Mismo eje (config → `{}` en silencio), resuelto para el caso "parseo falla". La sección 3.1 de este censo es la variante no cubierta por ese fix: parseo exitoso, campo `table` vacío. |
| **H12** | Docstring vs. schema real de `etl_output.py` — mismo patrón de "la documentación promete algo que el código no hace" que la sección 3.1 encuentra en `fragmentation.py`, resuelto para ese archivo puntual. |
| **H26** | `documentacion` nunca puede llegar poblada bajo el schema actual, pero `ETLGenerateResponse`/`etl_generator.py` la leen con `.get("documentacion", "")` — silencio total (campo vacío sin ninguna señal), ya catalogado como abierto y ambiguo. |

---

## 6. Background tasks — clase aparte

- `main.py:62-81` (`_purge_expired_ktr_jobs`) — `except Exception: logging.getLogger(__name__).exception(...)`. Logueado con traceback completo (mejor que C1/C2 de arriba), pero es una tarea de mantenimiento sin ningún consumidor que lea ese log — si la purga falla sistemáticamente, el único síntoma visible es la acumulación de filas vencidas en `ktr_build_jobs`, nunca un aviso.
- `outbox/runner.py:63-66` — mismo patrón (`logger.exception`, backoff), para el loop de drenaje in-process.

Ninguno de los dos bloquea nada del lado de un usuario activo (son housekeeping), pero comparten la misma propiedad: el único canal de detección es grepear logs de servidor.

---

## 7. No verificable sin ejecutar

- Si la excepción silenciada en `superset_client/datasets.py:56-57` (sección 2.1) ocurre de verdad contra la versión real de Superset desplegada, o si el operador `DatasetUUID` funciona siempre en la práctica y el `except` nunca dispara — no se puede confirmar leyendo código.
- Si el frontend (`InputConnection.jsx`, `TableDataPreview.jsx`, fuera del alcance backend de A0/A0.5) distingue `total_count=-1`/`count_is_estimate=True` de una tabla realmente vacía, o de un PK-set vacío por error vs. por ausencia real de PK.
- Cuántas veces en producción los cinco chequeos de la sección 3.3 se apagaron juntos por un DDL con error de sintaxis real — no hay métricas ni log agregado que lo cuente hoy, solo los `logger.warning` individuales.

---

## Resumen

De los ~114 `except` y ~60 `continue` relevantes en `backend/app/`, la gran mayoría sigue el patrón correcto (loguear + agregar a `warnings`/`notifications`, o fallar visible con `HTTPException`/excepción tipada) — la disciplina de D5/D15 está mayormente aplicada, en particular en el código más reciente de Track F (`repair.py`, `connection.py`, `build.py`). Lo más sorprendente: la excepción está justo en la pieza más nueva del propio refactor de fragmentación. `fragmentation.py` (escrito 2026-07-24 para resolver exactamente los fallos silenciosos que motivaron todo el proyecto — races y dobles escritores no detectados) tiene, en su propia función central (`build_rw_matrix`), el mismo defecto de fondo que H6 ya había nombrado y cerrado por otra vía: un step puede volverse invisible para la matriz R/W sin dejar rastro, contradiciendo el propio docstring del módulo que promete notificación. El mismo `if not table: continue` sin aviso está duplicado, de forma independiente, en otros dos módulos que razonan sobre "qué tabla toca este step" (`dimension_step_policy.py`, `fields_validate.py`) — exactamente el síntoma que D8 identificó (conocimiento de dominio duplicado) pero para la reacción-al-vacío, no para la resolución del alias que H4 ya centralizó.
