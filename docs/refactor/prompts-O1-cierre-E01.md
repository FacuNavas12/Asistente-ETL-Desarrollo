# Prompts para cerrar E-01 / O1 punto 2-3

**Efímero.** Se borra cuando O1 cierre. La decisión vive en D60 y en la D-N que salga de acá.

Reemplaza los prompts previos (diagnóstico ya ejecutado, ver respuesta de Code 2026-08-03). El cambio de firma de `STEP_BUILDERS` queda **descartado**: los dos canales de finding ya existen y ninguno pasa por la firma.

---

## Estado tras el diagnóstico

| Pregunta abierta | Resuelta por | Resultado |
|---|---|---|
| ¿Cambiar la firma de `STEP_BUILDERS`? | Q4 del diagnóstico | **No.** Dos canales existentes: `dimension_step_policy.results` y `validators/dimension_lookup_fields` vía `run_passes()` |
| ¿Derivar el modo del rol del grafo? | Q2 | **Ya se hace** (`role_of_dimension_step`, BFS). El crash no es fallo de derivación |
| Vocabulario más angosto que Kettle | Q3 / D60 | No. 7 códigos modo Y, 9 nombres modo N, verificados |
| Cuántos sitios de aborto | Q5 / D60 | 4, todos contenido, cero estructurales |
| ¿Corregir o notificar? | D60 § 2, criterio pto. 2 | **Notificar.** 3 de los 6 campos no existen en el DDL — no hay inventario contra qué verificar, corregir sería inventar |

---

## PROMPT A — Convertir los 4 sitios

```
Sesión de ejecución de O1, Alcance punto 2 de `docs/refactor/10-estabilizar-emision.md`.
La política ya está decidida en D60 (`02-decisiones.md:1630`, sección 3, tabla de los 4
sitios). NO la rediscutas: ejecutala. Si encontrás evidencia que la contradice, parás y
me lo decís antes de escribir código.

Usá SÍMBOLOS, no números de línea — los de D60 y los del diagnóstico ya divergen
(`incomplete` figura como :157 y como :164 según la fuente).

BLOQUE 0 — Verificación previa, ANTES de tocar nada. Es la única parte con riesgo real.
El fix del sitio 4 es "borrar el raise porque el validador ya reporta". Eso solo es
seguro si el validador cubre TODO lo que hoy cubre el raise. Probame estas tres cosas,
con evidencia:

  0a. ¿`check_dimension_lookup_fields` (`validators/dimension_lookup_fields.py`) se
      dispara en TODOS los casos en que `lookups.py:91` levanta, o su condición es
      apenas distinta? Compará las dos condiciones término a término. Si hay UN caso
      que el raise atrapa y el validador no, borrar el raise produce salida
      silenciosamente incorrecta — exactamente el "segundo frente" de
      `10-estabilizar-emision.md:23-25`. Si hay hueco, se tapa en el validador.
  0b. ¿El validador corre siempre, o `run_passes(table_ctx)` puede saltearse para
      algún step (ej. tabla no resoluble, contexto ausente)?
  0c. Los mensajes que HOY emiten los dos canales, ¿cumplen la especificación de
      D60 para el sitio 4? D60 exige que el finding cite el vocabulario esperado del
      modo asignado Y prediga el efecto real en Kettle (modo Y → cae a
      `TYPE_UPDATE_DIM_INSERT` sin aviso, R-K7; modo N → `getIdForValueMeta` cae a
      `TYPE_NONE`). Pegame el texto literal de ambos mensajes. Si no predicen el
      efecto, hay que enriquecerlos — es parte del criterio de terminado 3, no un extra.

BLOQUE 1 — Canal canónico (decisión chica, pero tomala explícita y decímela)
Dos canales reportan la misma condición en formatos distintos:
  (a) `dimension_step_policy` → `results: list[dict]` → `job.model_json["step_policy_conflictos"]`
      → promovido a `Validacion` en `_try_build` (`etl_generator.py:1817-1822`)
  (b) `validators/dimension_lookup_fields` → `Finding` → `warnings` → tupla de `build_ktr()`
Decidí cuál es el canónico para este caso y si el otro se deduplica o se deja. Criterio:
el usuario NO debe ver el mismo problema dos veces con dos redacciones distintas — eso
erosiona la confianza en los findings más que la falta de uno. Justificá la elección.

BLOQUE 2 — Los 4 sitios, según la tabla de D60 § 3
  Sitio 4 — `steps/lookups.py::_step_DimensionLookup`: sacar el `raise`, emitir
    `field_value` literal tal como llegó. NUNCA coaccionar a un valor "corregido".
  Sitio 1 — `build.py` `incomplete` / `missing_required_keys`: emitir el step con la
    clave ausente tal cual + `Finding(error)` con step y clave.
  Sitio 2 — `build.py` `critical_incomplete` / `_CRITICAL_FIELDS`: emitir el valor
    literal, incluido el placeholder `"SELECT 1"` + `Finding(error)` diciendo que ese
    step no produce filas reales.
  Sitio 3 — `build.py` `STEP_BUILDERS.get(...) is None`: único distinto — emitir un
    step `Dummy` REAL de Kettle conservando nombre y hops + `Finding(error)` con el
    tipo original. Verificá el XML del Dummy contra `DummyTransMeta.getXML()`, no por
    analogía con otro step.

Un commit por sitio.

BLOQUE 3 — Tests
Reescribí los 7 asserts de `pytest.raises` que codifican la política vieja
(`test_build_ktr_emission.py` ×1, `test_ktr_builder_fidelity.py` ×6,
`test_ktr_step_repair.py` ×1) a "no levanta, emite Finding con severidad error".
Agregá un test por sitio contra la salida REAL de `build_ktr()` — patrón de
`test_build_ktr_emission.py`, no fixtures usadas como input (criterio de terminado 5).
El del sitio 4 usa el step real de
`fase4_manual/sonnet/etl-llm-raw-test-01_sonnet_fase4.json:770-818`.

BLOQUE 4 — Suite completa. Comparar contra el corte de O1-c: 697 passed / 54 failed.
Cero regresión. Si algo nuevo se pone rojo, `git stash` para confirmar si es
preexistente antes de atribuirlo.

NO HAGAS: cambiar la firma de `STEP_BUILDERS` (descartado, ver diagnóstico Q4);
tocar el repair o el prompt para que el LLM no invente columnas (fuera de alcance
explícito, `10-estabilizar-emision.md` § No entra); tocar E-16.
```

---

## PROMPT B — Que llegue al usuario + cierre documental

```
Sesión de cierre de O1. Alcance punto 3 de `10-estabilizar-emision.md` — el único
que sigue sin resolver, y el plan lo marca como NO opcional.

BLOQUE 1 — El finding llega al frontend
Hoy los findings de `enforce_dimension_step_policy` van a
`job.model_json["step_policy_conflictos"]` / `validaciones`, no a donde el usuario mira.
Trazá el camino completo desde el `Finding`/`results.append()` hasta lo que el frontend
renderiza, y cerrá el hueco. Decime qué campo del frontend lo muestra y con qué rótulo.
Sin esto, "entregar con el problema documentado" es entregar un archivo roto sin aviso
— peor que abortar.

BLOQUE 2 — Corrida real (criterio de terminado 3 y 4, los que importan)
Corré el caso que produjo el crash de `'Cargar dim_producto'`, flujo async normal.
Verificá, EN LA CORRIDA, no por lectura de código:
  - se genera archivo para las dos etapas
  - el .ktr abre en Spoon
  - el usuario ve el `Validacion tipo="error"` ANTES de ejecutarlo
  - los 3 campos inexistentes (`fk_categoria`, `precio_lista`, `stock`) están nombrados
    en el aviso
Pegame la evidencia: el finding tal como lo ve el usuario, y el fragmento del .ktr.

BLOQUE 3 — Capa job
Con los 4 sitios convertidos, el escenario "cero archivos" deja de ser alcanzable por
contenido. Confirmá si queda alcanzable por el borde estructural que sigue abortando a
propósito (XML mal formado, `ktr_data` no-dict — `10-estabilizar-emision.md:149-156`).
Si sí, decime si vale las ~15-25 líneas de captura por etapa en
`_build_response_from_two_ktr_data`, o si se registra como error nuevo y se difiere.
NO lo implementes sin mi OK.

BLOQUE 4 — Documentación
  - **D63** en `02-decisiones.md` (D62 es la última): registra la EJECUCIÓN de la
    política de D60 § 3, con el canal canónico elegido (Bloque 1 del prompt A), los
    commits, y el resultado de la corrida real. D60 ya hizo el supersede de D55/D-1 —
    no lo repitas, referencialo.
  - **`errores.md`**: E-01 → `cerrado (D63)`. Actualizá "Dónde vive la evidencia".
  - **`10-estabilizar-emision.md`**: marcá el Alcance punto 2 y 3 como hechos, y cada
    criterio de terminado 1-7 con su evidencia. Si alguno no se cumplió, decilo en vez
    de marcarlo.
  - Si algo del diagnóstico contradijo el plan, corregí el plan — no lo dejes divergido.

BLOQUE 5 — Decime en una línea qué queda abierto de O1 y si O2 puede arrancar.
```

---

## Nota sobre por qué notificar y no corregir

D60 § 2 punto 2 lo cierra: *sin inventario resoluble no hay verificación posible; no se asume ningún valor por default.*

El caso concreto lo confirma. De los 6 campos de `'Cargar dim_producto'`, tres (`fk_categoria`, `precio_lista`, `stock`) **no existen en el DDL de la dimensión** — vienen de `fact_inventario`. Para "corregir" el `type` habría que adivinar el value-meta de columnas que no existen en ninguna tabla contra la cual verificar. Y el modo de falla de una corrección errada es peor que el de `TYPE_NONE`: una columna mal tipada que coacciona datos en silencio es exactamente el segundo frente que el propio plan nombra como riesgo mayor (`10-estabilizar-emision.md:23-25`).

Corregir la alucinación es trabajo del repair, y mejorarlo está fuera de O1 por decisión explícita.
