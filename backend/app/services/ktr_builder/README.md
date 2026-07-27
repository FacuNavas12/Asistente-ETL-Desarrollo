# services/ktr_builder

**Capa:** mezclada — la parte con más dominio puro del repo, junto con la infraestructura de serialización XML más grande. No hay separación física todavía, ver tabla.
**Propósito:** tomar el dict `{steps: [...]}` que devolvió el LLM (ya normalizado y reparado) y convertirlo en un `.ktr` que Spoon pueda abrir, decidiendo antes cuántos archivos físicos hacen falta.

## Qué entra
Un `dict` KTR sin tipar (`{name, type, config, x, y}` por step — vehículo real y dominante del sistema hoy, sin definición formal en código; ver `docs/auditoria/00-inventario.md` sección 5 para las 6 representaciones de `config` en circulación).

## Qué sale
XML `.ktr` (uno o más, según `fragmentation.py`) + `.kjb` si hubo corte (`job_analyzer.build_kjb_xml`) + `warnings`/`notifications` acumuladas durante normalización/reparación/build.

## Archivos

| Archivo | Capa objetivo | Qué hace |
|---|---|---|
| `contracts.py` | `domain/` | `parse_cfg`, `normalize_config`, `STEP_CONTRACTS` — la forma canónica de un step y sus alias de clave. Punto de entrada de todo lo demás del paquete. |
| `fragmentation.py` | `domain/` | Motor de corte F3: matriz step×tabla×{R,W} + algoritmo de componentes conexos que decide en cuántos `.ktr` se parte una fase. |
| `dimension_step_policy.py` | `domain/` | Deriva/fuerza el tipo de step de dimensión (`DimensionLookup`/`CombinationLookup`) según `scd_type`. |
| `fields_validate.py` | `domain/` | Validación de resolución de campos en orden topológico + detección de races de lookup de dimensión. |
| `validate.py` | `domain/` | Validación estructural pre-XML (columnas SELECT duplicadas, `Calculator`/`Formula` encadenado). Importa `step_types.STEP_TYPE_ALIASES` — domain→domain, cero excepción de capa (antes cruzaba a `registry.py`, ver split abajo). |
| `common.py` | **partido** | `_yn`/`KtrBuilderError` (`:14-36`) puros → `domain/`. `_sub` (`:7-11`) arma XML → `infrastructure/pentaho/`. |
| `step_types.py` | `domain/` | Split de `registry.py` (sesión de arquitectura): `STEP_TYPE_ALIASES` (identidad de tipo) + `_CRITICAL_FIELDS` (completitud mínima). Cero imports de proyecto. |
| `step_emitters.py` | `infrastructure/pentaho/` | Mitad infra del mismo split: `STEP_BUILDERS` (tipo canónico → función XML, con los imports de `steps/*`) + `STEP_CONFIG_KEYS`/`unmapped_config_keys` (auditoría de fidelidad de esa serialización — es capacidad presente del builder, no invariante de dominio). |
| `repair.py` | `services/` | Reparación de steps con config incompleto, LLM acotado a un step por vez. Recibe `llm: BaseLLM` por parámetro — decisión justificada en `docs/arquitectura-objetivo.md` mapa E1. |
| `build.py` | `infrastructure/pentaho/` | Orquestador de serialización: normaliza, valida, resuelve conexiones, emite XML final vía `STEP_BUILDERS`. Punto único de entrada del paquete (`build_ktr`). |
| `connection.py` | `infrastructure/pentaho/` | Resolución/serialización de conexiones Kettle. `resolve_real_connections` arma host/port/db/user reales — el password SIEMPRE queda como `${VAR}` de Kettle, nunca se resuelve (ver "Credenciales de conexión" en `CLAUDE.md`). |
| `layout.py` | `infrastructure/pentaho/` | Auto-layout x/y de steps sin posición. |
| `error_catalog_checks.py` | `infrastructure/pentaho/` | Auditoría del catálogo E1-E14 sobre el XML ya serializado. |
| `steps/` | `infrastructure/pentaho/` | Subpaquete — ver su propio README. |

## Reglas que aplican
R6 — `STEP_CONTRACTS` (`contracts.py`) es la única fuente de verdad de qué campos produce/consume cada tipo de step.
R7 — el conocimiento de "qué tabla toca este step" vive en `contracts.py`/`fragmentation.py`, no se reimplementa por módulo. **Violación real y no resuelta:** hoy SÍ se reimplementa el reverso de esa pregunta (reacción cuando la tabla sale vacía) en tres lugares — `fragmentation.py:79`, `dimension_step_policy.py:158`, `fields_validate.py:111` — ver R12 y `docs/auditoria/00b-fallos-silenciosos.md` sección 3.1.
R10 — el pipeline completo del paquete (`normalize_step_configs → repair_ktr_steps → repair_integrity_gaps → enforce_dimension_step_policy → split_ktr_by_cut → build_ktr`) hoy se comunica mutando el dict KTR in-place entre etapas — es la violación que motiva R10 forma positiva y `EtlDraft` (no implementado, ver `docs/arquitectura-objetivo.md`).

**Nota sobre `KNOWN_PDI_STEP_TYPES` (borrada):** existía en `registry.py` como whitelist derivada de `STEP_BUILDERS.keys()`, pero nunca se consultaba en runtime — `build.py` rechaza un `type` no soportado por `STEP_BUILDERS.get() is None`, no por whitelist. La coherencia entre lo que `system_etl.txt` le promete al LLM y lo que este paquete efectivamente construye la cubre `backend/tests/test_pdi_step_coherence.py` (tres direcciones: prompt→builder, alias→builder, builder→prompt), sin agregar un símbolo muerto de vuelta.

## Qué NO va acá
- Un nuevo campo de negocio en `STEP_CONTRACTS` que solo aplica a un builder XML — si es sobre cómo se serializa (no sobre qué significa), va en `steps/<familia>.py`, no acá.
- Una llamada nueva al LLM fuera de `repair.py` — el resto del paquete es determinístico a propósito (D6-bis: la fragmentación corta solo por señal estructural, sin heurística de LLM).
- Un `if not table: continue` nuevo sin notificar — es exactamente el patrón que R12 va a cerrar; cualquier código nuevo que responda "¿qué tabla toca este step?" debe poder devolver una notificación, no tragarse el caso vacío.
