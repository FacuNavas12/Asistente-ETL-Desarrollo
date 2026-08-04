# Cómo leer esta documentación

**Mutable.** Lo escribe quien reorganiza objetivos. Es el punto de entrada: ningún documento de `docs/` se lee "desde el principio" sin pasar por acá primero.

**Escrito 2026-08-03**, en el corte hacia la entrega. Antes de esta fecha la entrada natural era `docs/refactor/ESTADO.md`; dejó de serlo por el motivo que explica la sección "Por qué existe este archivo".

---

## Los tres objetivos, y todo lo demás

El trabajo abierto está separado en tres objetivos y un congelador. **Una sesión trabaja sobre un objetivo, no sobre "el refactor".**

| # | Objetivo | Archivo | Estado |
|---|---|---|---|
| **O0** | Higiene de repo — que el estado real sea legible desde git | [`refactor/00-higiene-repo.md`](refactor/00-higiene-repo.md) | Precondición de todo |
| **O1** | Estabilizar la emisión — que siempre se entregue archivo **y que lo entregado no mienta** | [`refactor/10-estabilizar-emision.md`](refactor/10-estabilizar-emision.md) | **Prioridad 1** |
| **O2** | Arquitectura de capas — dónde vive cada cosa | [`refactor/20-arquitectura.md`](refactor/20-arquitectura.md) | **Prioridad 2** |
| **O3** | Dónde se decide — qué sintetiza Python y qué le pregunta al modelo | [`refactor/30-decision-python-llm.md`](refactor/30-decision-python-llm.md) | Después de O1 + `referencia/` |
| — | Registro de errores encadenados | [`refactor/errores.md`](refactor/errores.md) | Se actualiza siempre |
| — | Todo lo que queda fuera | [`refactor/90-congelado.md`](refactor/90-congelado.md) | Congelado hasta después de entregar |

**O2 y O3 son distintos objetivos, no dos partes del mismo.** O2 responde *dónde vive cada archivo* — capas, R1-R12, barato y verificable por test. O3 responde *qué decide el sistema solo y qué le pregunta al modelo* — es lo que corta la cascada de errores, y `arquitectura-objetivo.md` no lo cubre. Confundirlos hace que se mueva código sin que ningún error se cierre.

**Regla de asignación:** si un hallazgo nuevo no entra en un objetivo abierto, se registra en `errores.md` (si es un error) o en `90-congelado.md` (si es trabajo), con una línea. No se abre un objetivo nuevo antes de entregar. Descubrir es libre, actuar necesita objetivo.

---

## Nomenclatura de sesiones

**Una sesión = una conversación que trabaja un solo objetivo y cierra con la Regla 10.** Se nombra por su objetivo, nunca por número correlativo — "sesión 3" no significa nada dentro de un mes.

| Sesión | Qué | Estado |
|---|---|---|
| **O0** | Higiene de repo | cerrada 2026-08-03 |
| **O1-a** | Fixes baratos de T (E-04…E-08) | cerrada, D59 |
| **O1-b** | El crash + criterio de degradación (E-01, E-02, E-03) | cerrada 2026-08-03 — D60/D64 resolvieron 1-2; sesión de cierre verificó 3/4 contra corrida real (`/generate-async`→`/status`, corpus de E-01) y cerró Bloque 3 (capa job). Ver criterios de terminado en `10-estabilizar-emision.md`. E-20 cerrado; E-21 registrado (no arreglado, a propósito) con impacto confirmado como E-23; E-24 nuevo, registrado, no bloquea |
| **O1-c** | T estructural (E-09, E-10, E-11) | cerrada, 2026-08-03 |
| **O2-a** | Partir `common.py` | cerrada 2026-08-03, D61 |
| **O2-b** | `resolve_step_table()` en `domain/` | cerrada 2026-08-03, D62 |
| **O2-c** | Partir `lineage_builder.py` | cerrada 2026-08-03, D63 pendiente de redactar |
| **REF** | Escribir `referencia/` | cerrada 2026-08-03 — `contrato-ddl.md`, `scd.md`, `kettle-comportamiento.md` escritos y verificados contra código. `docs/SCD/` (3 archivos) queda intacto en disco, consolidado en `scd.md`, no borrado — decisión pendiente del usuario |
| **O3** | La línea Python/modelo | — |

**Dependencias, y son todas las que hay:**

- **O1 va en orden** (a → b → c). Cada una apoya a la siguiente.
- **O2 no tiene orden.** Las tres son independientes entre sí y de O1 — se intercalan donde convenga. Sirven para cortar con algo chico y verde cuando una sesión de O1 se puso larga.
- **O3 va al final.** Necesita O1 cerrado y REF escrito.

El estado vigente de cada sesión vive en esta tabla y en `errores.md`. Si las dos discrepan, gana `errores.md` — está más cerca del trabajo.

---

## Cómo abrir una sesión

**Con Claude Code (ejecuta):** se le da el objetivo y los dos archivos. Nunca "seguí con el refactor".

> Leé `docs/README.md` y `docs/refactor/<archivo del objetivo>`. Esto es **<O1-b>**. <qué hacer>. Cerrá según la Regla 10.

**Con Claude en Cowork (analiza, planifica, contrasta):** se conecta la carpeta del repo y se dice en una línea dónde estás. **No hace falta pedirle que lea todo `docs/`** — eso viola el presupuesto de lectura y es lo que hace que una sesión empiece a inferir en vez de verificar.

> Repo conectado. Estoy en **<O1-b>**. Cerré <O1-a> con <D59>. <Qué necesito>.

Con eso alcanza: lee este archivo, el del objetivo, `errores.md`, y verifica el resto contra el código.

**La diferencia entre las dos** no es de detalle sino de trabajo: Code implementa dentro del repo con el contexto de su propia sesión. Cowork sirve para lo que Code no hace bien desde adentro — contrastar documentación contra código, encontrar contradicciones, decidir dónde va algo nuevo, planificar el objetivo siguiente. Arranca en frío siempre, así que lo que necesita es **qué es cierto hoy**, no cómo se implementa.

**Lo que nunca se pide, a ninguno de los dos:** "leé toda la documentación". `01-hallazgos.md` son 135 KB y `02-decisiones.md` 267 KB. Una sesión que intenta leerlos completos se queda sin contexto antes de empezar a trabajar — ver Regla B.

---

## Por qué existe este archivo

El 2026-08-02 una sesión de reconciliación (D0) clasificó los ítems de `03-plan.md` contra el estado del código. Se equivocó en su parte más importante: reportó los ítems 4-8 de D55 como "planificados, no ejecutados" cuando **los cinco estaban implementados**. Leyó `ESTADO.md`, que se había escrito a las 19:09; el código de esos ítems es de las 22:04, 22:23 y 22:30 del mismo día.

El prompt de esa sesión exigía explícitamente lo contrario — *"EVIDENCIA: archivo y línea del código actual. Sin cita, el estado es 'no verificado'. No infieras del texto del plan."* La regla estaba escrita y no alcanzó.

De ahí salen las dos reglas de abajo, que son el contenido real de este archivo.

### Regla A — el estado se verifica contra el código

Ningún documento de estado es autoridad sobre si algo está hecho. `ESTADO.md` dice qué fase está abierta; **no** dice si una función existe. Para eso: `grep`, `git log -- <archivo>`, y la línea.

Corolario operativo: cuando un documento y el código discrepan, **el documento está mal** y se corrige en el mismo turno en que se detecta la discrepancia. No se abre un hallazgo para eso.

### Regla A-bis — se cita símbolo, no línea

Verificado 2026-08-03: las líneas que `05-transversales.md` § T1 da para los tres `if not table: continue` ya no apuntan a ese código. `error_catalog_checks.py:305-317` en `03-plan.md` hoy es `:330`. Los hallazgos siguen siendo válidos; lo que se corrió es la cita.

**Una cita es `fragmentation.build_rw_matrix`, no `fragmentation.py:79`.** El símbolo sobrevive a un `git pull`; el número no. Cuando el número es imprescindible (una línea dentro de una función larga), se escribe junto al símbolo y con la fecha en que se verificó.

### Regla B — presupuesto de lectura por sesión

Amplía la regla 5 de `CLAUDE.md`, que quedó corta cuando `01-hallazgos.md` llegó a 135 KB y `02-decisiones.md` a 267 KB. Una sesión lee, como máximo:

1. `CLAUDE.md`
2. Este archivo
3. **El archivo de su objetivo** (O0, O1 u O2)
4. Como mucho **dos** archivos de evidencia, los que ese objetivo cite por nombre

Nada más. En particular: `02-decisiones.md` **no se lee entero nunca** — se entra por el índice de cabecera y se lee la entrada D-N que el objetivo cite. Lo mismo para `01-hallazgos.md`.

Si una sesión necesita más que eso, el objetivo está mal cortado, y eso mismo es un hallazgo.

---

## Qué es cada archivo

### Entrada y doctrina

| Archivo | Qué pregunta responde | Naturaleza |
|---|---|---|
| `../CLAUDE.md` | ¿Cómo trabaja este repo? Comandos, estructura, principios no negociables, criterio de capas | Mutable |
| `arquitectura-objetivo.md` | ¿Cuál es la arquitectura a la que se converge? Capas, R1-R12, mapa capa↔directorio, regla de migración | Mutable — **fuente de verdad de O2** |
| `README.md` (este) | ¿Por dónde entro y qué leo? | Mutable |

### Objetivos

| Archivo | Qué pregunta responde | Naturaleza |
|---|---|---|
| `refactor/00-higiene-repo.md` | ¿Por qué no puedo leer el estado desde git, y qué lo arregla? | Mutable |
| `refactor/10-estabilizar-emision.md` | ¿Qué aborta hoy, qué se entrega mintiendo, y con qué criterio se arregla cada cosa? | Mutable |
| `refactor/20-arquitectura.md` | ¿Qué deuda de capas se paga ahora, con qué prompt se abre cada sesión? | Mutable |
| `refactor/30-decision-python-llm.md` | ¿Qué deriva Python solo y qué le pregunta al modelo? | Mutable |
| `refactor/errores.md` | ¿Qué errores hay abiertos y de cuál salió cada uno? | Mutable en `Estado`/`Objetivo`, append-only el resto |
| `refactor/90-congelado.md` | ¿Qué quedó afuera y qué lo destraba? | Mutable |

### Fuentes de verdad (append-only — no se reescriben)

| Archivo | Qué pregunta responde | Cómo se consulta |
|---|---|---|
| `refactor/02-decisiones.md` | ¿Qué se decidió y por qué? **Manda sobre cualquier plan que lo contradiga** | Por índice, entrada D-N puntual. Nunca entero |
| `refactor/01-hallazgos.md` | ¿Qué se encontró y dónde exactamente? | Por índice, entrada H-N puntual. Nunca entero |
| `refactor/05-transversales.md` | ¿Qué falla en más de un módulo a la vez? | Entero — son 3 KB |
| `refactor/06-contrato-ddl.md` | ¿Qué le falta al contrato de DDL? | Por índice DDL-N |
| `refactor/04-verificacion.md` | ¿Qué cambió sin que ninguna corrida real lo ejercite? | Entero — son 5 KB |

**Append-only significa:** una entrada H o D se escribe una vez y su cuerpo no se edita nunca más. Si una decisión cambia, se escribe una D nueva que supersede a la anterior. Solo la línea `**Estado:**` y el índice son mutables.

### Estado e historia

| Archivo | Qué pregunta responde | Advertencia |
|---|---|---|
| `refactor/ESTADO.md` | ¿Qué fase está abierta? | **Ya no es el punto de entrada.** Su celda de F4 acumuló ~8000 caracteres de historia en una sola fila y se desfasó del código al menos una vez (ver "Por qué existe este archivo"). Se consulta para fases, no para verificar si algo está implementado |
| `refactor/03-plan.md` | ¿Cuáles eran las fases del refactor de fragmentación? | Histórico a partir de 2026-08-03 — los objetivos vigentes son O0/O1/O2. Se conserva porque Track F documenta cómo se llegó al motor de corte actual |
| `refactor/00-objetivo.md` | ¿Por qué se arrancó el refactor de fragmentación? | Histórico, sigue siendo válido |
| `refactor/03b-reportes.md` | ¿Cómo se llegó hasta acá? Narrativa de sesión | Histórico |

### Investigación (consulta puntual, nunca lectura completa)

| Archivo | Cuándo se abre |
|---|---|
| `refactor/plan-reparacion-etl.md` | Detalle de implementación de los 8 ítems de D55, con 7 revisiones. Se abre por sección de ítem, y por su § MATERIAL PARA SESIÓN D (inventario de puntos de dialecto) |
| `refactor/diagnostico-fk-categoria-loader-faltante.md` | **Insumo directo de O1** — es el diagnóstico del crash. Temporal: se borra cuando O1 cierre |
| `refactor/03c-investigacion-vocabulario-dimension-kettle.md` | Vocabulario de dimensión contra fuente Kettle. 48 KB |
| `refactor/investigacion-kettle-RK1-RK6.md` | Lecturas de `pentaho-kettle` para R-K1 a R-K6. 41 KB |
| `refactor/investigacion-pentaho-C10-C11-C12.md` | Lecturas de doc oficial Pentaho para C.10-C.12. 33 KB |
| `refactor/fase4_manual/` | Corpus de corridas reales (Sonnet completa, Haiku fallida). Evidencia, no documento |
| `auditoria/00-inventario.md` | Inventario de módulos del backend, sección 3.6 = pipeline de generación |
| `auditoria/00b-fallos-silenciosos.md` | Censo de `except`/`continue` que no notifican |
| `costo/beneficio de JSON Schemas.md` | Encargo redactado para una sesión propia. Congelado |

---

## Autoridad: qué manda sobre qué

Cuando dos fuentes se contradicen, este es el orden. Sirve para no reabrir discusiones ya cerradas.

1. **El código.** Para "¿esto está implementado?" no hay segunda opinión.
2. **`02-decisiones.md`.** Para "¿qué se decidió?". Manda sobre cualquier plan o análisis que lo contradiga — regla ya vigente en `CLAUDE.md`.
3. **`arquitectura-objetivo.md`.** Para "¿dónde va este código?".
4. **El archivo del objetivo en curso.** Para "¿qué hago ahora?".
5. Todo lo demás es evidencia o historia.

### Autoridad sobre comportamiento de Pentaho

Regla aparte, porque es la que más veces se resolvió mal. Cuando hay ambigüedad sobre qué hace Kettle:

1. **`readData()` / `loadXML()` / `getXML()` del `Meta` correspondiente en `pentaho/pentaho-kettle`**, citando clase y línea. Única autoridad normativa.
2. **Fixtures de artefactos reales** del repo — contraste, no autoridad. Si difieren de (1), se registra la diferencia; no se elige una.
3. Wiki, Apache Hop, blogs — **no son fuente**. Hop tiene el formato divergido en varios steps.

Sin cita de clase y línea, una afirmación sobre Kettle queda marcada NO VERIFICADA. No se completa por analogía con otro step.

**Dos límites de esta regla, que no son obvios:**

- **Kettle es mudo donde no valida.** Acepta cualquier string como nombre de columna; el error aparece recién en runtime contra la base. Para legitimidad de nombres la autoridad es el DDL real, no el `Meta`. Son dos autoridades distintas — el crash que motiva O1 nace justo de confundirlas.
- **Kettle resuelve ambigüedades con silencio.** Un valor no reconocido cae a `TYPE_UPDATE_DIM_INSERT` sin aviso; `getValueMetaName()` devuelve `"-"`, que además es el nombre legítimo del id 0 — un centinela de "no encontrado" que colisiona con un valor válido. Copiar eso contradice R11. La regla operativa es: **leer como Kettle, fallar distinto que Kettle.** Se replica su semántica de lectura para predecir qué va a hacer; el emisor reporta fuerte donde Kettle degradaría callado.

---

## Reglas de escritura

Vigentes, heredadas de `CLAUDE.md` y sin cambios:

1. El estado de una fase vive en un solo lugar. Ningún otro documento lo repite.
2. Evidencia y decisiones son append-only.
3. Cada archivo declara arriba si es mutable o append-only, y quién lo escribe.
4. Descubrir es libre; actuar necesita objetivo.
5. Presupuesto de lectura — ver Regla B arriba.
6. Archivado frío solo al cerrar un objetivo, nunca continuo.

Nuevas, de esta reorganización:

7. **Toda sesión que tome una decisión cierra escribiéndola en `02-decisiones.md` en el mismo turno.** Ya estaba en `CLAUDE.md`; se repite porque es la que más se incumplió.
8. **Un documento que discrepa del código se corrige en el momento en que se detecta**, sin abrir hallazgo. Ver Regla A.
9. **Ningún archivo de objetivo supera las ~200 líneas.** Si crece, es señal de que acumuló historia — la historia va a `03b-reportes.md`, el objetivo queda con lo accionable.

### Regla 10 — cómo cierra una sesión

**Una sesión que tocó código no termina hasta que estas tres cosas están hechas, en el mismo turno:**

1. **El código commiteado.**
2. **`errores.md` al día** — los errores que cerró pasan a `cerrado`; los que encontró se agregan con su `Origen`. Esto no es opcional: es lo único que evita que la cascada vuelva a vivir en la memoria de quien estaba trabajando.
3. **El archivo del objetivo actualizado** — qué quedó hecho, qué no, y el resultado de la suite si la corrió.

Y si tomó una decisión, la D-N (regla 7).

Una sesión que termina sin esto deja a la siguiente arrancando a ciegas. Ya pasó una vez: el código de tres ítems de D55 se escribió a las 22:00 y `ESTADO.md` quedó con la frase de las 19:09 — una sesión posterior clasificó mal cinco ítems por leerla.

**Corolario:** si una sesión encuentra algo fuera de su objetivo, lo registra en `errores.md` y **no lo arregla**. Registrar es parte del cierre; arreglar necesita otro objetivo.
