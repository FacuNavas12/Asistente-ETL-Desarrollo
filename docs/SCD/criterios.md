# Criterios SCD1 vs SCD2 — dónde vive cada decisión en el código

Este archivo es el mapa. `SCD1.md` y `SCD2.md` detallan cada tipo; acá se
documenta el criterio de decisión y — más importante — el hueco que causó que
el mismo problema (una dimensión con `scd_type` declarado que no coincide con
la forma del DDL que realmente sale) se repitiera.

## Dos decisiones distintas, no una (D37, `docs/refactor/02-decisiones.md`)

El código las separa a propósito:

**A) `scd_type` (0/1/2) por dimensión** — decisión de negocio ("¿un reporte
del pasado debe mostrar el atributo como era ENTONCES?"), no derivable solo de
los datos. La resuelve el LLM, acotado por un pre-check determinista.
Vive en [`backend/app/domain/scd.py`](../../backend/app/domain/scd.py),
función `classify_scd_candidates()`.

**B) Qué step de Pentaho carga la dimensión** — 100% derivado de A, nunca
juicio del modelo en cada corrida. Vive en las mismas `domain/scd.py`
(`derive_dimension_loader_step`, `derive_fact_lookup_step`,
`derive_attribute_update_mode`) y se aplica en
[`backend/app/services/ktr_builder/dimension_step_policy.py`](../../backend/app/services/ktr_builder/dimension_step_policy.py)
(`enforce_dimension_step_policy`).

Antes de D37/D11/D44/D51 estas dos preguntas se resolvían de forma
independiente en momentos distintos del pipeline y podían discrepar — el
síntoma aparecía en runtime (Kettle), no al guardar el `.ktr`. Fijar B como
función pura de A cerró esa clase de bug.

## A — el pre-check determinista (`classify_scd_candidates`)

Precedencia, de mayor a menor (razonada completa en D37):

| # | Condición | Veredicto | `forced_scd_type` | Vinculante |
|---|---|---|---|---|
| 0 | Sin clave natural durable **confirmada** (`key_columns_trusted=True` y `key_columns=[]`) | `NO_HISTORY_POSSIBLE` | 1 | Sí, incluso sobre `declared_intent` |
| 1 | Ningún atributo mutable (todo lo no-clave es la propia clave) | `NO_HISTORY_POSSIBLE` | 1 | Sí |
| 2 | Dimensión de calendario (nombre + única clave tipo fecha, `is_calendar_dimension`) | `NO_HISTORY_POSSIBLE` | 0 | Sí (angosto a propósito) |
| 3 | `declared_intent == "2"` (usuario ya lo declaró en `dwh_intent.scd_type`) | `HISTORY_DECLARED` | — | Por debajo de 0-2 |
| 3-bis | Origen trae columnas tipo `valid_from`/`current_flag`/`version`/etc. | `HISTORY_DECLARED` | — | D6: la info ya vive en el origen |
| 5 | Resto | `UNDECIDED` | — | Juicio del modelo, techo = `scd2_candidates` |

`key_columns_trusted` distingue "confirmado que no hay clave" (BD/DDL) de "no
se sabe" (Formulario/CSV/Excel) — sin esa distinción la regla 0 degradaba a
SCD1 casi cualquier ETL armado a mano con origen sin metadata estructural
(bug real, cubierto en `test_refine_untouched_dimension_preserves_dim_contracts`).

`detect_history_intent()` (mismo archivo) es una señal aparte, de **alcance
proyecto** (`business_rules` + `process_goal`), no por entidad — a qué
dimensión aplica queda como juicio del modelo, nunca automático, porque
"histórico" es ambiguo entre volumen de carga y versionado de atributo (ver
comentario extenso en el código). Dentro de esa señal, las frases de
`_COMPLIANCE_PHRASES` (cierre contable, auditoría, regulatorio...) **prohíben**
SCD1 — único caso donde SCD1 no es preferencia sino veto (Kimball 2008).

Este pre-check entra al prompt de inferencia como bloque `## PRE-CHECK SCD`
(`structure_inferrer._build_scd_precheck_block`), y `system_inference.txt`
(sección `## SCD: CUANDO 1 Y CUANDO 2`) lo declara vinculante para el modelo.

## B — derivación determinista del step (post D44/D51/R-K7)

`derive_dimension_loader_step(scd_type)` y `derive_fact_lookup_step(scd_type)`
devuelven **siempre** `"DimensionLookup"`, para todo `scd_type` (0, 1 o 2) —
Kettle no tiene un Type 0 real, y `scd_type==0` colapsa a 1 (mismo step,
mismo modo `Update`). Lo que sí cambia por atributo es el modo:
`derive_attribute_update_mode()` devuelve `"Insert"` si el atributo está en
`attributes_scd2` (nueva versión), `"Update"` en cualquier otro caso (S-8: el
modo es propiedad del ATRIBUTO, no de la dimensión).

`enforce_dimension_step_policy()` compara esto contra lo que el `.ktr`
realmente trae y corrige o reporta la discrepancia — ver docstring del
archivo para las reparaciones seguras vs. los casos que solo reporta.

## El hueco que causó el bug encontrado (C — forma del DDL, sin dueño en código)

A y B están resueltos en Python, con función nombrada y tests. Pero hay una
**tercera decisión** que hoy vive solo en texto de dos prompts distintos, sin
ninguna función en `domain/scd.py` que la exprese y sin ningún validador
Python que la chequee:

> **La forma del `UNIQUE` de la clave natural depende de `scd_type`.**
> SCD1/0: `UNIQUE(id_<entidad>_origen)` simple.
> SCD2: índice nombrado sobre `(id_<entidad>_origen, fecha_fin)`, sin
> predicado parcial (I3/I4, `system_inference.txt` línea ~45).

Esta regla está declarada en `system_inference.txt` (inferencia, D3) **y**
repetida en `prompt_validacion_src.txt` (auditoría posterior del DDL, I3/V2)
— dos prompts independientes, cada uno redactado en su propio momento. La
segunda (V2) dice literalmente: *"tiene UNIQUE (o el indice compuesto de I3
en SCD2)"* — acepta la forma compuesta **sin condicionarla a que
`scd_type == 2`**. Ningún código valida que la forma efectiva del DDL
coincida con el `scd_type` que el propio `dim_contracts` declara para esa
tabla.

Resultado observado: una dimensión con `scd_type=1` (comentario en el DDL:
"SCD1: sobreescribe sin versionar") salió con
`UNIQUE(id_categoria_origen, fecha_fin)` — la forma de SCD2 — y ni la
inferencia ni la auditoría posterior lo marcaron, porque ninguna de las dos
fases tiene ese chequeo cruzado.

### Cómo se detectó

Revisando un DDL generado a pedido del usuario (confirmando el fix de
`\n` literal en `system_inference.txt`), aparecía `dim_categoria` /
`dim_producto` con comentario `SCD1` pero constraint
`uq_dim_categoria_origen_fin UNIQUE (id_categoria_origen, fecha_fin)`. Al
cruzar contra `system_inference.txt` (D3: la forma compuesta es "si es
SCD2") y luego contra `prompt_validacion_src.txt` (V2: acepta la forma
compuesta como alternativa válida sin condición de `scd_type`), quedó claro
que ninguna de las dos fases de LLM tiene ese cruce, y que tampoco existe un
validador Python (`contract_validate.py`, `ddl_validation.py`) que lo cubra
— a diferencia de A y B, que sí tienen dueño determinista en `domain/scd.py`.

### Corrección de raíz recomendada (no aplicada todavía — requiere decisión)

Mismo patrón que D37 aplicó para A: mover la regla de texto de prompt a una
función nombrada en `domain/scd.py`, p. ej.
`natural_key_unique_shape(scd_type: int) -> Literal["simple", "composite_with_date_to"]`,
y consumirla desde un validador real (candidato natural:
`ddl_validation.py`/`contract_validate.py`, ya parsean DDL con `sqlglot` vía
`ddl_adapter`) que compare la forma del `UNIQUE`/índice contra
`dim_contracts[i].scd_type`. Hasta que eso exista, cualquier prompt nuevo que
toque DDL de dimensiones debe repetir la condición completa
("compuesto SOLO si scd_type==2") en vez de la frase corta actual — ver
abierto en `docs/refactor/02-decisiones.md` § Abiertos si se decide priorizar.
