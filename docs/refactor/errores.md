# Registro de errores

**Mutable en las columnas `Estado` y `Objetivo`; el resto de cada fila es append-only.** Lo escribe cualquier sesión que encuentre o cierre un error.

**Para qué existe:** para que "arreglo un error y aparece otro" sea visible en vez de vivir en la memoria de quien está trabajando. La columna que hace el trabajo es **`Origen`** — de qué error salió éste. Con eso, a cuatro niveles de profundidad se puede ver dónde se está parado.

> Se mueve a `registro/errores.md` cuando la reorganización de carpetas se ejecute. Hoy vive acá para no dejar dos estructuras a medio migrar.

---

## Las tres reglas

1. **Todo error se registra cuando se ve, aunque no se toque.** Registrar es gratis. Actuar necesita objetivo.
2. **`Origen` es obligatorio si apareció arreglando otro.** Si salió de una sesión de exploración o de una corrida, va vacío.
3. **Profundidad máxima 2.** Si E-01 destapa E-02 y E-02 destapa E-03, E-03 se registra y se deja: se vuelve a cerrar E-01. Sin tope, la cadena no termina.

**Cuándo se trabaja un error:** solo si está en el objetivo en curso, **o** si bloquea algo que sí lo está. Todo lo demás espera, registrado.

**Vocabulario de `Estado`:** `abierto` · `en curso` · `cerrado` · `congelado`.

---

## Tabla

| ID | Síntoma | Origen | Estado | Objetivo | Bloquea a |
|---|---|---|---|---|---|
| E-01 | `KtrBuilderError` en `Cargar dim_producto`: `type='Update'` fuera del vocabulario de modo N. No se entrega ningún archivo | — | abierto | O1 | — |
| E-02 | `VALUE_META_TYPE_NAMES` se mergeó con la nota "PENDIENTE verificar contra `ValueMetaFactory.java`" sin verificar. Si la lista está incompleta, el emisor rechaza valores legítimos | E-01 | cerrado (D60) | O1 | E-01 |
| E-03 | ~~El repair de la serie fk-categoria acepta un `stream_field` que no existe en el stream y degrada a `tipo="info"`~~ — **descartado tras verificar (D60):** el test rojo (`test_repair_dimension_loader_fields_floor_when_gate_fails`) reusaba el fixture de su vecino exitoso (mismo atributo faltante, resoluble por `_deterministic_field_mapping` sin pasar nunca por el LLM fake que simulaba la alucinación) — defecto del fixture, no de `_repair_dimension_loader_fields`. El gate real (`etl_generator.py:805-815`) sí rechaza un `stream_field` inexistente, verificado con un fixture que fuerza el camino correcto. Corregido en el mismo turno | E-01 | cerrado (D60) | O1 | E-01 |
| E-16 | `_synthesize_dimension_lookup_config` (`dimension_step_policy.py:243-244`), rama `upstream_lower is None` (grafo no resoluble): asume `stream_field = attr` por identidad **sin verificar contra ningún inventario y sin finding** — mismo patrón que el criterio de D60 prohíbe, encontrado al verificar E-03 pero fuera de su alcance puntual | E-03 | abierto | — | — |
| E-04 | `StringOperations` escribe índices numéricos donde Kettle exige palabras literales. El step **nunca recorta ni cambia mayúsculas**, con cualquier configuración | — | cerrado (D59) | O1 | — |
| E-05 | `Unique` escribe `case_sensitive`; el tag real es `case_insensitive`, con polaridad invertida. Ausente → Kettle compara sin distinguir mayúsculas **siempre** | — | cerrado (D59) | O1 | — |
| E-06 | `ExcelInput` nunca emite `spreadsheet_type` → Kettle cae al motor legado JXL, que **no lee `.xlsx`** | — | cerrado (D59) | O1 | — |
| E-07 | `JsonInput` nunca emite `includeNulls` → el comportamiento ante `null` lo define el `kettle.properties` de cada máquina. No-determinismo entre entornos | — | cerrado (D59) | O1 | — |
| E-08 | `TextFileOutput` anida `create_parent_folder` en `<file>`; Kettle lo lee como hijo directo de `<step>`. Inocuo hoy solo porque el único valor emitido coincide con el default | — | cerrado (D59) | O1 | — |
| E-09 | `CombinationLookup` nunca emite el bloque `<fields><return>`: surrogate key sin nombre real y autoincrement forzado a `true` | — | cerrado (O1-c) | O1 | — |
| E-10 | `DataValidator` invierte `name`/`fieldname`: Kettle busca un campo del stream con el nombre de la **etiqueta** de la regla. La validación queda rota siempre que etiqueta ≠ campo | — | cerrado (O1-c) | O1 | — |
| E-11 | `SplitFieldToRows` sin el "3" no es un plugin id registrado. Si el alias resuelve ahí, Spoon marca el step "missing" y la transformación no corre | — | cerrado (O1-c) | O1 | — |
| E-12 | `GroupBy` clásico con `all_rows="N"` fijo exige input pre-ordenado; sin esa garantía en el grafo, el agregado puede ser silenciosamente incorrecto | — | congelado | — | — |
| E-13 | `validators/__init__.py` importa dos módulos untracked → `ImportError` en cualquier clon | — | en curso | O0 | todo |
| E-14 | 249 de 271 archivos "modificados" son churn CRLF. El estado real no se puede leer desde git | — | en curso | O0 | O1, O2 |
| E-15 | `ESTADO.md` afirmó que 5 ítems de D55 no estaban ejecutados cuando lo estaban. Una sesión clasificó mal por leerlo | — | en curso | O0 | — |

---

## Dónde vive la evidencia

- **E-01** — `diagnostico-fk-categoria-loader-faltante.md`
- **E-02, E-03, E-16** — D60 (`02-decisiones.md`); verificación hecha en la sesión de O1-b contra `pentaho-kettle` (E-02) y `tests/test_dimension_field_repair.py` (E-03/E-16)
- **E-04 … E-12** — `investigacion-tags-validos-por-step.md` § A, con clase y línea de `pentaho-kettle`
- **E-09, E-10, E-11 (cierre)** — 3 commits (`7b0a78f`, `9a15593`, `e53387e`), 3 tests nuevos en `test_build_ktr_emission.py` (uno por step, contra salida real de `build_ktr()`). Suite completa post-fix: 697 passed / 54 failed — uno menos que el corte de O1-a (55), sin regresión nueva (verificado contra `git stash`: la única falla que cambió de posición, `test_ktr_xml_validator.py::test_build_ktr_get_system_info_without_fields_gets_default_field`, falla igual sin estos commits — preexistente, no relacionada)
- **E-13, E-14, E-15** — `00-higiene-repo.md`

---

## Nota sobre E-03 (histórica — ver D60 para el cierre)

Se pensó que era el hallazgo más incómodo del lote: que la degradación que O1 quiere generalizar ya existía rota en el camino de repair, aceptando datos alucinados en vez de rechazarlos. Verificado contra código (D60, `02-decisiones.md`): no es así — el gate real (`etl_generator.py:805-815`) rechaza correctamente un `stream_field` inexistente; el test que decía lo contrario reusaba el fixture de su vecino exitoso y nunca ejercía el camino que decía probar. El criterio que igual hacía falta para generalizar la degradación a los 4 sitios de aborto se escribió en D60, sin depender de que este caso puntual resultara roto.
