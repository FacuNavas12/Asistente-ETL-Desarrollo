# Cómo leer esta documentación

**Mutable.** Lo escribe quien reorganiza objetivos. Es el punto de entrada: ningún documento de `docs/` se lee "desde el principio" sin pasar por acá primero.

**Escrito 2026-08-03**, en el corte hacia la entrega. Antes de esta fecha la entrada natural era `docs/refactor/ESTADO.md`; dejó de serlo por el motivo que explica la sección "Por qué existe este archivo".

---

## Los tres objetivos, y todo lo demás

El trabajo abierto está separado en tres objetivos y un congelador. **Una sesión trabaja sobre un objetivo, no sobre "el refactor".**

| # | Objetivo | Archivo | Estado |
|---|---|---|---|
| **O0** | Higiene de repo — que el estado real sea legible desde git | [`refactor/00-higiene-repo.md`](refactor/00-higiene-repo.md) | Precondición de O1 y O2 |
| **O1** | Estabilizar la emisión — que `build_ktr()` siempre entregue archivo, con el problema documentado | [`refactor/10-estabilizar-emision.md`](refactor/10-estabilizar-emision.md) | **Prioridad 1** |
| **O2** | Aplicar la arquitectura objetivo | [`refactor/20-arquitectura.md`](refactor/20-arquitectura.md) | **Prioridad 2** |
| — | Todo lo que queda fuera de O0/O1/O2 | [`refactor/90-congelado.md`](refactor/90-congelado.md) | Congelado hasta después de entregar |

**Regla de asignación:** si un hallazgo nuevo no entra en O0, O1 ni O2, va a `90-congelado.md` con una línea. No se abre un objetivo nuevo antes de entregar. No se arregla algo porque se lo vio — eso ya es la regla 4 de `CLAUDE.md`, acá se vuelve más estricta: descubrir es libre, actuar necesita objetivo.

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
| `refactor/10-estabilizar-emision.md` | ¿Qué aborta hoy la generación, y con qué criterio deja de abortar? | Mutable |
| `refactor/20-arquitectura.md` | ¿Qué deuda de arquitectura hay registrada y cuál se paga ahora? | Mutable |
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
