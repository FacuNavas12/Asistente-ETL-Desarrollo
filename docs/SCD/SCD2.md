# SCD2 en este proyecto

Ver `criterios.md` para la tabla completa de precedencia y el hueco de
diseño detectado. Este archivo es la referencia rápida de qué implica SCD2
concretamente en el código y en el DDL que debe salir.

## Qué significa acá

Versiona el atributo: cada cambio abre una fila nueva, la vieja se cierra.
Un reporte del pasado muestra el valor que el atributo tenía **entonces**,
no el actual. El criterio real (no "¿cambia el dato?" sino "¿alguien va a
consultar el pasado de ese atributo?") está en el docstring de
`domain/scd.py` y en `system_inference.txt`, sección `## SCD: CUANDO 1 Y
CUANDO 2`.

## Cuándo se llega a SCD2

`classify_scd_candidates()` (`domain/scd.py`), en orden:

- **Regla 3 — declarado explícito**: `dwh_intent.scd_type == "2"` en la
  entrada del usuario (`TableSemantics.dwh_intent.scd_type`). Veredicto
  `HISTORY_DECLARED`.
- **Regla 3-bis — evidencia estructural en el origen**: el origen ya trae
  columnas tipo `valid_from`/`valid_to`/`vigente_desde`/`vigente_hasta`/
  `fecha_desde`/`fecha_hasta`/`current_flag`/`activo`/`version`
  (`_ORIGIN_HISTORY_COLUMNS`). D6 puro: la información ya vive en el origen,
  es lectura, no inferencia. Veredicto `HISTORY_DECLARED`.
- **Regla 5 — juicio del modelo (`UNDECIDED`)**, apoyado en una señal de
  **proyecto** (no de entidad): `detect_history_intent()` sobre
  `business_rules` + `process_goal` detecta frases como "histórico",
  "as-of", "evolución de", "trazabilidad", "vigente a la fecha", "snapshot".
  Esta señal **no decide por sí sola** a qué dimensión aplica — eso es
  juicio del modelo, documentado como tal si aplica.
- **Veto de compliance**: si la señal de proyecto incluye frases de
  `_COMPLIANCE_PHRASES` (cierre contable, auditoría, regulatorio, normativa,
  "reproducir reportes", período cerrado), **SCD1 queda prohibido** para la
  dimensión que corresponda — único caso donde el default se invierte en vez
  de solo matizarse (Kimball 2008: en entornos de cierre contable o
  regulatorios, "Type 1 changes may be outlawed").

**Nunca** puede declararse SCD2 si el pre-check marcó `NO_HISTORY_POSSIBLE`
(reglas 0/1/2 de `criterios.md`) — vinculante incluso sobre una declaración
explícita del usuario. El modelo debe citar la razón del pre-check en
`scd_rationale` si intenta justificarlo igual.

`attributes_scd2` (en `dim_contracts`) es subconjunto de `scd2_candidates`
del pre-check: atributos mutables que no son casi-únicos por fila (no
tendría sentido versionar algo que cambia en cada carga) ni constantes
(`distinct_counts <= 1`). Sin perfil estadístico disponible (DDL pegado o
formulario manual), todos los atributos mutables quedan como candidatos sin
filtrar por cardinalidad — degradación explícita, documentada en el
`reason` del `ScdPrecheck`.

## Contrato de DDL obligatorio (igual que SCD1, D4)

Mismas columnas que SCD1 (`sk_`, `version`, `fecha_inicio`, `fecha_fin`,
clave natural) — el contrato `Dimension lookup/update` no distingue por
`scd_type`. Lo que sí cambia es la forma del índice de la clave natural.

## Forma correcta del `UNIQUE` de la clave natural

**Compuesto**, nombrado, nunca UNIQUE simple ni índice parcial:

```sql
CREATE UNIQUE INDEX uq_dim_<entidad>_origen_fin
    ON dim_<entidad> (id_<entidad>_origen, fecha_fin);
```

Por qué compuesto: la clave natural se repite una vez por versión (I3). Por
qué **nunca parcial** (`WHERE es_vigente` / `WHERE fecha_fin IS NULL`):
Kettle escribe la fecha tope `2199-12-31 23:59:59.999` en la fila vigente,
nunca `NULL` — un índice parcial sobre esa condición queda vacío en la
práctica (I3, invariante que rompe producción si se ignora).

`fecha_fin` es **NULLABLE** siempre (I6) aunque en la práctica Kettle nunca
la deje en `NULL` — `NOT NULL` rompería el INSERT del primer registro de
cada entidad (todavía no tiene "fila siguiente" que la cierre).

**Gap conocido:** `prompt_validacion_src.txt` (V2) acepta esta forma
compuesta como válida para **cualquier** dimensión, sin verificar que
`scd_type` de esa tabla en `dim_contracts` sea efectivamente `2` — ver
`criterios.md` § "El hueco que causó el bug" para el caso real donde una
dimensión SCD1 salió con esta forma.

## Step Pentaho y modo por atributo

- Loader: `derive_dimension_loader_step(2)` → `"DimensionLookup"` (mismo
  step que SCD1/SCD0 desde D44/R-K7 — Kettle no distingue por config de
  step, solo por el modo de cada atributo).
- Modo por atributo (`derive_attribute_update_mode`):
  - En `attributes_scd2` → `"Insert"` (abre versión nueva).
  - En `attributes_scd1` (atributos que sí versionan la dimensión pero que
    para ESTE atributo puntual el negocio no necesita historial) →
    `"Update"`.
- Del lado del hecho (rol `fact_lookup`, D16): siempre solo-lectura
  (`update="N"`), sin importar `scd_type` — nunca escribe la dimensión desde
  el lado del fact, evita doble escritor sobre la misma tabla.

## Literales válidos de modo (Kettle)

`ATTRIBUTE_UPDATE_TYPE_CODES` en `domain/scd.py`: `Insert`, `Update`,
`Punch through`, `DateInsertedOrUpdated`, `DateInserted`, `DateUpdated`,
`LastVersion`. Cualquier string fuera de esta lista cae **silenciosamente**
en modo Insert (`TYPE_UPDATE_DIM_INSERT`) del lado de Kettle — un typo del
emisor ("SCD1", "overwrite") produce un `.ktr` válido que versiona en vez de
sobrescribir, sin error ni warning visible.
