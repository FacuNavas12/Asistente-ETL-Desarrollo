# SCD1 en este proyecto

Ver `criterios.md` para la tabla completa de precedencia y el hueco de
diseño detectado. Este archivo es la referencia rápida de qué implica SCD1
concretamente en el código y en el DDL que debe salir.

## Qué significa acá

Sobrescribe el atributo en la fila vigente. Un reporte del pasado muestra el
valor **actual** del atributo, no el que tenía en el momento del hecho — es
el default de este proyecto (`system_inference.txt`, regla `UNDECIDED ->
SCD1` si no hay señal de proyecto aplicable).

## Cuándo se llega a SCD1

- **Default de juicio** (`classify_scd_candidates`, regla 5/`UNDECIDED`): sin
  evidencia estructural ni declaración explícita, sin señal de proyecto
  (`detect_history_intent`) aplicable a esa dimensión en particular.
- **Forzado, no elegido** (`domain/scd.py`):
  - Regla 0 — sin clave natural durable confirmada (`key_columns_trusted=True`,
    `key_columns=[]`). `forced_scd_type=1`, veredicto `NO_HISTORY_POSSIBLE`,
    vinculante incluso sobre una declaración explícita del usuario pidiendo
    SCD2: sin clave, `Dimension lookup/update` no tiene sobre qué operar.
  - Regla 1 — no hay ningún atributo mutable (todo lo no-clave es la propia
    clave natural). Versionar no produciría ninguna versión distinta.
  - Regla 2 — dimensión de calendario (colapsa a SCD1 en el step aunque el
    veredicto "de libro" sea Type 0 de Kimball — ver más abajo, Kettle no
    tiene Type 0 real).

En los casos forzados, `scd_rationale` en la salida del LLM debe citar la
razón del pre-check (obligatorio, `system_inference.txt` línea 35).

## Contrato de DDL obligatorio (D4 — igual que SCD2)

El contrato `Dimension lookup/update` es obligatorio en **toda** dimensión,
sea SCD1 o SCD2 — no hay atajo por ser SCD1:

```sql
sk_<entidad>   SERIAL PRIMARY KEY            -- acepta INSERT explícito de 0 (fila desconocido, I2)
version        INTEGER NOT NULL DEFAULT 1     -- el step lo exige aun en SCD1
fecha_inicio   TIMESTAMP NOT NULL
fecha_fin      TIMESTAMP NULL                 -- NULLABLE igual que en SCD2 (I6)
id_<entidad>_origen ...                       -- clave natural del lookup
```

`fecha_inicio`/`fecha_fin` existen en SCD1 aunque no haya versionado real:
es un rango degenerado pero cerrado (Kettle escribe `2199-12-31 23:59:59.999`
como centinela de "vigente", nunca deja `fecha_fin` en `NULL` en la práctica
— R-K2). El lookup por rango de fechas del lado del hecho funciona igual con
o sin historial real.

## Forma correcta del `UNIQUE` de la clave natural

**Simple**, no compuesto:

```sql
CONSTRAINT uq_dim_<entidad>_origen UNIQUE (id_<entidad>_origen)
```

`(id_<entidad>_origen, fecha_fin)` compuesto es la forma de **SCD2**
(`system_inference.txt` D3) — en SCD1 solo existe una fila por clave natural,
así que el compuesto es ruido, no error funcional inmediato, pero declara mal
la intención del modelo y esconde que la tabla debería tener UNIQUE simple.
**Gap conocido:** ni la inferencia ni la auditoría posterior de DDL
(`prompt_validacion_src.txt`, V2) rechazan hoy la forma compuesta en una
dimensión declarada SCD1 — ver `criterios.md` § "El hueco que causó el bug".

## Step Pentaho y modo por atributo

- Loader: `derive_dimension_loader_step(1)` → `"DimensionLookup"`, `update="Y"`.
- Modo de cada atributo no-clave: `derive_attribute_update_mode()` → siempre
  `"Update"` (en SCD1 puro, `attributes_scd2` está vacío, así que ningún
  atributo cae en la rama `"Insert"`).
- Del lado del hecho (rol `fact_lookup`, D16): el mismo step, pero
  `update="N"` — nunca escribe, solo resuelve la FK.

## Caso especial: dimensión de calendario

Kimball la trata como Type 0 (atributos fijos, derivados de la fecha). Pero
Kettle no tiene Type 0 real (R-K7): el colapso a "mismo step, modo Update"
solo es seguro acá porque el ETL **nunca carga** la dimensión de calendario
(se puebla aparte, ver `K18` en `system_etl.txt`) — el guard que lo garantiza
vive en `services/etl_generator.py` y reusa `is_calendar_dimension()` de
`domain/scd.py`.
