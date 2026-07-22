# Plan — Refactor de fragmentación

**Última actualización:** 2026-07-22

Deriva de [`00-objetivo.md`](00-objetivo.md) y [`01-hallazgos.md`](01-hallazgos.md), evaluado contra [`02-decisiones.md`](02-decisiones.md). Consolida dos planes que llegaron por separado y que hoy conviven sin fusionar:

- **Track A — Auditoría de arquitectura:** prompts ya escritos, fase-0 a fase-7, uno por sesión (`Contexto Cambios/Arquitectura/`). **Ninguna fase se ejecutó todavía** — `docs/arquitectura-objetivo.md` ya está en el repo (actualizada 2026-07-22 con D6/D6-bis), pero `docs/auditoria/` no existe: nadie corrió Fase 0 en adelante. `00-plan-auditoria.md` es la versión vigente; `prompt-auditoria-arquitectura.md` está marcado `SUPERSEDIDO` por el propio material, no usar.
- **Track F — Motor de fragmentación:** prompt de 3 fases + track de errores de 6 puntos (`Contexto Cambios/Fragmentacion/handoff_fragmentacion_y_errores.md`). Tampoco se ejecutó — es la Fase 1 (investigar y reportar) la que sigue, y requiere aprobación explícita antes de cada fase siguiente.

Los dos tracks convergen en el mismo punto: el borde tipado de entrada. `00-plan-auditoria.md` ya lo declaró **PASO 1 obligatorio** de su propio plan de remediación; el hallazgo de "LLM y flujo" (H2-H4, H11) llegó a la misma conclusión desde el lado de fragmentación — el motor de corte no puede construirse sobre una base de conocimiento de dominio que ya divergió (D8).

---

## Orden macro

```
D3 ✓ · D6/D6-bis ✓ · D7 ✓ (ubicación entregada) · H16 ✓ acotado
                                        │
Track A: pospuesta (A0 no arranca) ────┤
                                        ├──> convergen en el borde (PASO 1)
Track F: F1 (investigar) ──────────────┘         ← puede arrancar ya
         │
         │  bloqueado solo por C.2 (contrastar reglas de corte del handoff contra D6-bis, barato)
         v
    F2 — diseño del corte, sobre borde tipado + STEP_CONTRACTS centralizado + fixtures de D7
         v
    F3 — implementación (corte + jerarquía de jobs + V1/V2/V3)
```

D3, D6, D6-bis y D7 dejaron de bloquear nada — ver `02-decisiones.md`. Lo único que sigue como gate explícito antes de F2 es C.2. Nada bloquea que Track F1 arranque ya.

---

## Fases

### Verificaciones humanas previas — todas resueltas 2026-07-22

1. ~~Confirmar que nadie del equipo tenga trabajo apoyado en ETLs guardados.~~ **Verificado: nadie.** D3 confirmado sin condición.
2. ~~Re-verificar D6 en frío.~~ **Hecho** — D6/D6-bis resueltas en `02-decisiones.md`, backend determinístico, solo corrección estructural.
3. ~~Recolectar los casos reales donde forzar 2 archivos produjo error.~~ **Ubicación entregada:** `C:\Users\05147\OneDrive\Escritorio\Test_Asistente_ETL\Simplificado\Sol\02\Errores\` (`err1.ktr`, `err2.ktr`). Insumo listo para F2/F3 y F4 — el contenido todavía no fue analizado, eso es trabajo de esas fases, no de esta sesión.

Ninguna verificación humana previa sigue bloqueando el arranque de Track F.

---

### Track A — Auditoría de arquitectura

**Actualizado 2026-07-22: A0 se pospone, no corre en paralelo con Track F.** El argumento más fuerte para correrla ahora era que produce H1 como subproducto — y H1 quedó desinflado (ver `01-hallazgos.md`). El costo de releer un inventario completo del backend que además va a quedar desactualizado en todo lo que Track F toque no se justifica todavía. Se retoma cuando Track F esté suficientemente asentado.

| Fase | Entrada | Salida | Modifica código | Depende de |
|---|---|---|---|---|
| A0 — Fase 0 (inventario) | `arquitectura-objetivo.md` reescrito (ver nota abajo) | `docs/auditoria/00-inventario.md` | No | Pospuesta — no arranca junto con Track F |
| A0.5 — Fase 0.5 (censo fallos silenciosos) | A0 | `docs/auditoria/00b-fallos-silenciosos.md` | No | A0 |
| A1 — Fase 1 (doc vs. realidad) | A0 | `docs/auditoria/01-doc-vs-real.md` | No | A0. **Solapa con esta sesión de consolidación** — ver nota abajo |
| A2 — Fase 2 (cumplimiento por capas) | A0 | `docs/auditoria/02-cumplimiento.md` | No | A0 |
| A3 — Fase 3 (bordes de entrada y modelo de dominio) | A0, A2, A0.5 | `docs/auditoria/03-bordes.md` | No | A0.5, A2. **Parte A ya diagnosticada** por H2-H4, H6, H11 — no repetir, sí completar Partes B/C/D (otros bordes: filas de DB, uploads, config de usuario, env vars — ninguno cubierto todavía por ningún material) |
| A4 — Fase 4 (acoplamiento) | A2, A3 | `docs/auditoria/04-acoplamiento.md` | No | A2, A3. Cubre H5 (acoplamiento temporal del linaje) formalmente |
| A5 — Fase 5 (plan de remediación) | Todos los reportes previos | `docs/auditoria/05-plan.md` | No | A0-A4. **PASO 1 = el borde**, ya decidido por `00-plan-auditoria.md`. Ver "Ajustes por D1/D2" abajo — el formato de verificación de esta fase necesita modificarse antes de correrla |
| A6 — Fase 6 (consolidar doctrina) | Plan aprobado | `CLAUDE.md` + `docs/arquitectura-objetivo.md` actualizados | Solo docs | A5 aprobado |
| A7 — Fase 7 (ejecución) | A5 | Un PASO del plan por sesión | Sí | A6 (doctrina consolidada primero) |

**Nota sobre A1:** esta sesión de consolidación ya cubre una porción de lo que A1 pediría (contrastar `CLAUDE.md` contra el estado real del código) para el recorte de fragmentación específicamente. A1 sigue teniendo valor porque su alcance es el backend completo, no solo el flujo de fragmentación — pero al correrla, señalar que `docs/refactor/00-objetivo.md` y `01-hallazgos.md` ya existen para evitar duplicar diagnóstico.

**Nota sobre `docs/arquitectura-objetivo.md` — hecho 2026-07-22:** escrita al repo con una sección nueva ("Ejemplo aplicado — el motor de fragmentación") que incorpora D6 y D6-bis, situando la fragmentación en el modelo de capas sin duplicar el contenido de las decisiones. Sigue sin commitear a git — ver nota de cierre de esta sesión. A0 sigue pospuesta igual: que la doctrina esté escrita no obliga a correr el inventario todavía.

---

### Track F — Motor de fragmentación

| Fase | Objetivo | Depende de | Hallazgos que toca |
|---|---|---|---|
| F1 — Investigar (Fase 1 del handoff) | Responder las 5 preguntas ya escritas: estructura de steps pre-XML, matriz tipo→{lee,escribe}, soporte de `JobEntryJob`, orden de `_build_job_plan`, costo de construir la matriz sin re-parsear XML | Ninguna estructural. **H7 ya adelanta la pregunta 3** (hoy no hay `JobEntryJob` — falta el costo de agregarlo). **La pregunta 4 (orden de `_build_job_plan`) queda parcialmente pre-respondida por D6**: la función existe y ya orquesta el KJB en Python puro (`etl_generator.py:224`) — falta confirmar si ordena por grafo de FK o por orden fijo, eso sigue abierto | H1, H7 |
| C.2 (gate, no numerada F) — Contrastar reglas de corte del handoff contra D6-bis | Releer las reglas de fragmentación ya escritas en `handoff_fragmentacion_y_errores.md` y eliminar las que respondan a legibilidad/tamaño en vez de corrección estructural | Ninguna — barato. **Bloquea F2**: sin esto el pase nace contradiciendo D6-bis | — |
| F2 — Diseñar el corte (Fase 2 del handoff) | Algoritmo de matriz R/W → componentes conexos → validadores V1/V2/V3 | F1 aprobada, C.2 hecho, borde tipado + `STEP_CONTRACTS` centralizado. Fixtures ya ubicadas (D7: `err1.ktr`/`err2.ktr`) | H1, H4, H8, H11 |
| F3 — Implementar el corte (Fase 3 del handoff) | Corte + jerarquía de jobs (`job_origen_stg.kjb`, `job_stg_dwh.kjb`, `job_master.kjb`) + V1/V2/V3 extendiendo `ktr_xml_validator.py`/`error_catalog_checks.py` (H8), gate antes de emitir | F2 aprobado, **H7 resuelto** (sin `JobEntryJob` no hay jerarquía de 3 niveles que anidar) | H1, H7, H8 |
| F4 — Track de errores (6 puntos del handoff §2) | Decidir estrategia de fix (derivación determinista desde `dim_contracts` vs. parche de prompt — evidencia apunta a lo primero), resolver E3, key vacía, E14, confirmar E1/E2, validador de contrato staging→DWH | Independiente de F1-F3 — son fixes puntuales sobre el generador ya existente, pueden correr en paralelo. `dim_contracts` (149b836) confirmado como precedente compatible, no como obstáculo (D11) | H9, H10, H14 |
| F5 — Limpieza de bajo costo, sin dependencias | Dedup de los 4 `_parse_cfg`/`_parse_config` restantes (H3), fix docstring `etl_output.py` (H12), `s["name"]` sin `.get()` en `validate.py` | Ninguna — "cero riesgo" según el propio material de origen | H3, H12 |

**Nota sobre H16 (acotada 2026-07-22):** la base sí autogenera `sk_producto` (secuencia vía `DEFAULT`), pero solo si el `INSERT` omite la columna — `_step_InsertUpdate` no filtra claves técnicas del mapeo. Confirmar contra `err1.ktr`/`err2.ktr` (D7) si el caso real llegó a mapear algo a `sk_producto` es trabajo de F1/F4, no un bloqueo aparte. Ver H16 en `01-hallazgos.md`.

---

## Ajustes por D1/D2 al material recibido — resueltos 2026-07-22

El material de Track A fue escrito antes de que D1 y D2 quedaran fijadas. Dos puntos del prompt de **Fase 5 (`fase-5-plan-remediacion.md`)** perdían sentido tal como estaban escritos — ya no son candidatos especulativos, se resolvieron con D9 y D10 en `02-decisiones.md`:

**1. El criterio de verificación "comparación de artefacto generado antes y después" → resuelto por D9.**
D2 mata la política de preservar comportamiento, no la necesidad de verificar. Reemplazo fijado: **contra qué se compara es el delta declarado, no el output viejo** — se enumera qué va a cambiar antes de correr el paso, y cero deltas sin explicar es el criterio de aprobación. Herramienta: normalización canónica (aplanar todos los `.ktr` a una secuencia de steps ignorando fronteras de archivo) para generar la lista de deltas de forma confiable. D9 también separa cuatro clases de cambio (costura del corte / funcionalidad nueva / rediseño / corrección) que un diff ingenuo mezclaba sin distinguir.

**2. La sección "Compatibilidad durante la transición" → eliminada por D10.**
D3 quedó verificado (nadie usa datos guardados), así que el requisito de compatibilidad no existe. Sin período de convivencia entre parseo viejo y nuevo — el mecanismo de vuelta atrás es revertir el commit.

**3. La tensión con la Restricción 1 de Fase 5 ("cada paso deja el sistema funcionando... mergeable solo") → resuelta, se parte en dos lecturas (D9).**
Lectura A ("el artefacto sigue produciendo lo mismo"): eliminada, es lo que D2 dice que no se protege. Lectura B ("el repo queda verde, cada paso es revertible por separado"): se mantiene — es regla de tamaño de paso, no de preservación de comportamiento. No hay contradicción real una vez separadas.

Ninguna otra fase de Track A o Track F pierde sentido bajo D1/D2 — el resto (inventario, censo de fallos silenciosos, cumplimiento por capas, acoplamiento, doctrina) es diagnóstico neutral a la decisión de cuántos archivos se generan.

## Requisito transversal — D13, definición de terminado

Toda fase de Track A y de Track F, sin excepción, cierra solo con: (1) dos tests — uno de lo que la fase trabajó, uno del contrato que expone hacia la fase siguiente; (2) el registro de deltas de esa fase (D9), como warnings del pase, cubriendo tanto lo determinístico del backend como lo que produce el LLM; (3) `CLAUDE.md` + archivo de progreso actualizados. Ver D13 en `02-decisiones.md` para el detalle completo y el porqué.

---

## Paralelizable — actualizado 2026-07-22

- **Track A está pospuesto completo**, incluido A0 — no corre en paralelo con Track F por ahora (ver nota en la tabla de Track A).
- F1 (investigar) y C.2 (limpiar reglas de corte contra D6-bis) pueden arrancar ya, en paralelo entre sí.
- F4 (track de errores) y F5 (limpieza) son independientes de todo lo demás y pueden hacerse en cualquier momento.
- H16 verificado contra la base (sequence confirma) — lo que queda es confirmar contenido de `err1.ktr`/`err2.ktr`, cae dentro de F1/F4.
- F2 está bloqueado solo por F1+C.2. F3 está bloqueado por F2 y por H7 resuelto.
- Reescribir `docs/arquitectura-objetivo.md` (incorporando D6/D6-bis) puede hacerse ya, aunque A0 esté pospuesta — es trabajo de documentación, no de código.

## Backlog — fuera de alcance de este plan, con sesión propia

Ítems confirmados como reales pero explícitamente no planificados todavía (ver `02-decisiones.md`, sección "Abiertos"):

- **C.1** — plan de soporte multi-motor SQL (Postgres queda de default por D12, pero el resto no tiene plan).
- **C.4** — auditoría retroactiva de cambios no declarados en commits pasados de generación de KTR. Falta acotar hasta qué commit.

## Qué queda fuera de este plan

Todo lo listado en "Deliberadamente no decidido" de `02-decisiones.md`: si el borde va como parte de A7-PASO1 o antes, el cambio `string → object`, el comportamiento de `build-from-raw` ante raw incompleto, y el plan de soporte multi-motor SQL (C.1). Este plan no fuerza ninguna de esas decisiones.
