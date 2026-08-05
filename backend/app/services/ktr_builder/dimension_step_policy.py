"""
Parte 4 (bloque A) de la serie dim_contracts: el tipo de step que carga una
dimension se decidia DOS veces — una implicitamente al escribir el DDL
(scd_type), otra al elegir el step en la fase de generacion. Dos decisiones
sobre lo mismo pueden discrepar, y el sintoma aparece en runtime, no al
guardar el .ktr.

La correccion: el tipo de SCD se declara UNA vez, en la inferencia
(dim_contracts[i].scd_type). El tipo de step se DERIVA de esa declaracion en
codigo — no es un juicio del modelo en cada corrida, porque la respuesta es
determinista. El juicio que SÍ sigue siendo del modelo es decidir scd_type en
la inferencia (Parte 1) — eso no cambia acá.

Overrides son legitimos (volumen muy alto cuya cache no entra en memoria,
matching por reglas complejas o difusas, dimension de recarga full refresh) y
existen. La propiedad que se preserva es "default determinista + override
explicito, nunca silencioso": ver OVERRIDE_STEP_PREFIX.

D37 (docs/refactor/02-decisiones.md): derive_dimension_step_type() se movio a
domain/scd.py — D11 (acá) fijo que el STEP se deriva de scd_type; D37 fijo de
donde sale scd_type, que D11 daba por dado. Se reexporta acá, mismo patron de
excepcion nombrada que schemas/canonical.py -> domain/canonical_types.py, para
no tocar los call sites existentes de este modulo.

D44/D51 (docs/refactor/02-decisiones.md): derive_dimension_step_type() se
elimina (no queda alias) y se reemplaza por derive_dimension_loader_step()/
derive_fact_lookup_step() — el step se deriva por ROL (loader vs. fact_lookup
de D16), no solo por scd_type. La única rama de auto-fix segura se invierte:
antes era DimensionLookup -> CombinationLookup (downgrade, config subconjunto);
ahora es CombinationLookup -> DimensionLookup, sintetizando fields/date_from/
date_to/version_field desde el DimContract — sigue siendo config de un step
existente, nunca topología (no cruza la línea que D16 fijó). Ver R-K7 en
docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md.

O3 (docs/refactor/30-decision-python-llm.md): lo que arriba era reparación
condicional (el modelo escribe el config completo, Python compara y corrige
si difiere) pasa a ser el camino principal, incondicional. El modelo ya no
escribe update/return_field/date_from/date_to/version_field/fields[].type —
apply_dimension_contracts() construye el config COMPLETO de todo step de
dimensión con contrato, siempre, desde DimContract. Lo único que el modelo
sigue aportando y Python no puede derivar: topología (de ahí sale el ROL vía
role_of_dimension_step) y el mapeo stream_field del lado de `keys`/`fields`
(build_dimension_lookup_config lo valida contra el stream real, nunca lo
inventa). enforce_dimension_step_policy se renombra: ya no "enforza" una
política contra lo que el modelo eligió, construye.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping

from app.domain.scd import (
    ATTRIBUTE_UPDATE_TYPE_CODES,
    derive_attribute_update_mode,
    derive_dimension_loader_step,
    derive_fact_lookup_step,
)
from app.domain.step_table import resolve_step_table
from app.services.ktr_builder.contracts import normalize_config, parse_cfg
from app.services.ktr_builder.fields_validate import upstream_fields_for_step

logger = logging.getLogger(__name__)

__all__ = [
    "OVERRIDE_STEP_PREFIX",
    "DIMENSION_STEP_TYPES",
    "derive_dimension_loader_step",
    "derive_fact_lookup_step",
    "derive_attribute_update_mode",
    "ATTRIBUTE_UPDATE_TYPE_CODES",
    "role_of_dimension_step",
    "build_dimension_lookup_config",
    "apply_dimension_contracts",
    "has_registered_override",
]

# Mismo patrón que FIELD_INTEGRITY_PREFIX en fields_validate.py: un prefijo de
# texto plano en validaciones[].mensaje que el código detecta por
# startswith() — el modelo lo usa para registrar un override intencional
# (campo = nombre exacto de la tabla) en vez de dejarlo como una discrepancia
# silenciosa entre el step elegido y el que deriva scd_type.
OVERRIDE_STEP_PREFIX = "[Override de step] "

# Tipos de step cuya función es cargar una dimensión (ver
# derive_dimension_loader_step/derive_fact_lookup_step). Si uno de estos
# apunta a una tabla ausente de dim_contracts, no es un step cualquiera fuera
# de alcance (fact, staging, etc.) — es evidencia de que la tabla debería
# estar en el contrato y no llegó (typo, mayúsculas distintas, o dimensión
# faltante en dim_contracts). Ese caso no puede quedar en silencio.
DIMENSION_STEP_TYPES = {"DimensionLookup", "CombinationLookup"}

# derive_dimension_loader_step()/derive_fact_lookup_step()/
# derive_attribute_update_mode() viven en domain/scd.py (D44/D51) — importadas
# arriba y reexportadas vía __all__.


# D16: tipos de step cuya escritura sobre tabla física es SIEMPRE inequívoca
# (nunca se usan como lookup de solo lectura en este generador) — el ancla
# del BFS de rol tiene que apoyarse en estos, NUNCA en DimensionLookup/
# CombinationLookup, cuyo status de escritura es exactamente lo que
# role_of_dimension_step() está tratando de resolver para la MISMA tabla
# (evita el chicken-and-egg, ver D16 en 02-decisiones.md).
_UNAMBIGUOUS_WRITER_TYPES = {"TableOutput", "InsertUpdate", "Update", "Delete"}


def _write_target_table(step: dict, step_type_aliases: dict[str, str]) -> str | None:
    canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
    if canonical not in _UNAMBIGUOUS_WRITER_TYPES:
        return None
    cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
    return (cfg.get("table") or "").strip() or None


def role_of_dimension_step(
    step_name: str,
    table: str,
    ktr_data: dict,
    step_type_aliases: dict[str, str],
) -> str:
    """"loader" | "fact_lookup" (D16). BFS hacia adelante desde step_name
    siguiendo hops habilitados: si alcanza algún step que escribe una tabla
    física DISTINTA de `table` (típicamente la carga del hecho), step_name es
    un lookup de FK del lado del hecho -> "fact_lookup" (debe quedar
    solo-lectura). Si nunca alcanza otro escritor — termina en la propia
    `table`, o solo en sinks sin tabla (WriteToLog, checkpoints, Dummy) —
    step_name es el loader de la dimensión -> "loader" (mantiene su
    escritura). Un loader que además loguea un checkpoint sigue clasificando
    bien: WriteToLog no es "escritor de tabla", no hace falta excluirlo del
    grado como hacía la heurística descartada (out_deg==0)."""
    steps_by_name = {s.get("name"): s for s in ktr_data.get("steps", [])}
    adjacency: dict[str, list[str]] = {}
    for hop in ktr_data.get("hops", []):
        if not hop.get("enabled", True):
            continue
        adjacency.setdefault(hop.get("from", ""), []).append(hop.get("to", ""))

    table_lower = table.strip().lower()
    visited: set[str] = {step_name}
    stack = list(adjacency.get(step_name, []))
    while stack:
        nxt = stack.pop()
        if nxt in visited:
            continue
        visited.add(nxt)
        nxt_step = steps_by_name.get(nxt)
        if nxt_step is not None:
            target = _write_target_table(nxt_step, step_type_aliases)
            if target and target.strip().lower() != table_lower:
                return "fact_lookup"
        stack.extend(adjacency.get(nxt, []))
    return "loader"


def has_registered_override(validaciones: list, table: str) -> bool:
    """Pública desde el diagnóstico de dim_contracts × ktr_data (docs/refactor/
    02-decisiones.md, D-pendiente "toda dimensión con FK tiene loader"):
    find_unloaded_dimensions (ddl_checks.py) necesita el mismo criterio que
    apply_dimension_contracts usa para NO tocar un step con override — una
    dimensión con override registrado no cuenta como "sin loader", es una
    decisión explícita del modelo, no un hueco."""
    table_lower = table.strip().lower()
    for v in validaciones or []:
        mensaje = str(v.get("mensaje", "") if isinstance(v, dict) else getattr(v, "mensaje", ""))
        campo = str(v.get("campo", "") if isinstance(v, dict) else getattr(v, "campo", "")).strip().lower()
        if mensaje.startswith(OVERRIDE_STEP_PREFIX) and campo == table_lower:
            return True
    return False


# O3: prefijo descriptivo que el modelo antepone a un atributo cuando el
# stream trae el valor "pelado" — ej. contrato pide 'nombre_categoria', el
# stream trae 'categoria' (corpus real: etl-llm-raw-test-01_sonnet_fase4.json,
# 'Cargar dim_producto'). Paso 3 de _resolve_stream_field, movido acá desde
# etl_generator._deterministic_field_mapping (E-21/E-23: antes vivía detrás
# de un `if llm is None: return` que lo hacía inalcanzable sin proveedor —
# acá no hay LLM en el camino, así que no hay guard que lo corte).
_DESCRIPTIVE_PREFIX = "nombre_"


def _resolve_stream_field(
    attr: str,
    upstream_exact: dict[str, str] | None,
    proposed_mapping: dict[str, str],
) -> tuple[str | None, bool]:
    """Escalera de resolución del lado stream de UN atributo de dimensión
    (O3, docs/refactor/30-decision-python-llm.md) — 3 pasos deterministas,
    ninguno depende de un LLM:

    1. El modelo propuso un mapeo para este atributo (model_config['fields'])
       y el campo propuesto existe de verdad en el stream — el modelo puede
       alucinar acá igual que en cualquier otro campo, se revalida contra
       upstream_exact, nunca se confía a ciegas.
    2. Identidad: el atributo tiene un campo homónimo en el stream.
    3. Prefijo descriptivo ('nombre_' + _DESCRIPTIVE_PREFIX): 'nombre_categoria'
       -> 'categoria'.
    4. Ninguno resuelve: (None, False) — el caller omite el atributo de
       'fields' y reporta, nunca asume por default (ver hallazgo en
       01-hallazgos.md: identidad sin verificar generó mapeos incorrectos
       reales antes de este chequeo).

    upstream_exact=None (grafo no resoluble desde este step, ver
    fields_validate.upstream_fields_for_step): preserva el comportamiento
    histórico — asume identidad sin verificar, nada contra qué validar.

    Devuelve (stream_field, inferido) — inferido=True si el nombre resuelto
    difiere del atributo, señal para que el caller emita un finding
    severity=info (un mapeo adivinado por una máquina tiene que quedar
    visible para quien abre el .ktr en Spoon, no solo funcionar en
    silencio)."""
    attr_lower = attr.strip().lower()

    if upstream_exact is None:
        return attr, False

    proposed = proposed_mapping.get(attr_lower)
    if proposed and proposed.strip().lower() in upstream_exact:
        resolved = proposed.strip()
        return resolved, resolved.lower() != attr_lower

    if attr_lower in upstream_exact:
        return attr, False

    if attr_lower.startswith(_DESCRIPTIVE_PREFIX):
        base = attr_lower[len(_DESCRIPTIVE_PREFIX):]
        if base in upstream_exact:
            return upstream_exact[base], True

    return None, False


def build_dimension_lookup_config(
    contract,
    *,
    update: str,
    model_config: Mapping,
    upstream_fields: set[str] | None,
    step_name: str,
    table: str,
) -> tuple[dict, list[dict]]:
    """O3 (docs/refactor/30-decision-python-llm.md): construye el config
    COMPLETO de un step DimensionLookup desde el DimContract — camino
    PRINCIPAL, no reparación condicional. Reemplaza
    _synthesize_dimension_lookup_config (que solo corría en 3 ramas de
    enforce_dimension_step_policy, al detectar una discrepancia): acá se
    llama SIEMPRE, para todo step de dimensión con contrato y sin override,
    sin importar lo que el modelo haya puesto en `config`.

    Nunca inventa: technical_key/version_field/date_from/date_to son
    obligatorios en TODA dimensión de dim_contracts (V1/V3,
    prompt_validacion_src.txt), y attributes_scd1/attributes_scd2 son el
    contrato completo de atributos no-clave (D37) — el modo de cada uno sale
    de derive_attribute_update_mode() (S-8), nunca de lo que haya emitido el
    modelo. `keys` se preserva de `model_config` tal cual (ya resuelto por el
    modelo contra la clave natural del lado del stream — Python no puede
    derivarlo, no trae el nombre del campo del stream).

    `update="N"` (rol fact_lookup, D16): sin `fields` — un lookup de solo
    lectura no necesita el modo de actualización de cada atributo, solo
    matchear por `keys` + rango de fechas y devolver `return_field`. Si el
    modelo había mandado `fields` de todos modos (asumiendo el rol loader
    que la topología que él mismo dibujó contradice), se descarta con un
    finding severity=info — vocabulario de modo Y en un step ahora en modo
    N es el vocabulario cruzado exacto que Kettle rechaza en runtime (D57).

    `update="Y"` (rol loader): arma `fields` con el mapeo del modelo
    (model_config['fields'], `table_field`/`stream_field`), resuelto atributo
    por atributo vía _resolve_stream_field. Un nombre que el modelo propuso
    en `fields` y no pertenece al contrato de esta dimensión ('sobra') se
    ignora con un finding severity=info — vocabulario cruzado con otra tabla
    (típicamente la de hechos), no error: el atributo del contrato igual se
    resuelve por su propio camino (identidad o prefijo)."""
    findings: list[dict] = []
    new_cfg: dict = {
        "schema": model_config.get("schema", ""),
        "table": model_config.get("table", ""),
        "connection": model_config.get("connection", ""),
        "return_field": contract.technical_key,
        "keys": model_config.get("keys", []),
        "update": update,
        "date_from": contract.date_from,
        "date_to": contract.date_to,
        "version_field": contract.version_field,
    }

    if update != "Y":
        if model_config.get("fields"):
            findings.append({
                "tipo": "info",
                "campo": table,
                "mensaje": (
                    f"Step '{step_name}' para '{table}': {len(model_config['fields'])} campo(s) de "
                    "'fields' descartado(s) — este step es un lookup de FK del lado del hecho (solo "
                    "lectura, D16), 'fields' no aplica en ese rol; su vocabulario asumía modo "
                    "loader (D57)."
                ),
            })
        return new_cfg, findings

    proposed_mapping: dict[str, str] = {}
    for f in (model_config.get("fields") or []):
        if not isinstance(f, dict):
            continue
        dest = str(f.get("table_field") or f.get("lookup") or "").strip().lower()
        src = str(f.get("stream_field") or f.get("stream") or "").strip()
        if dest and src:
            proposed_mapping[dest] = src

    contract_attrs_lower = {
        a.strip().lower() for a in (*contract.attributes_scd1, *contract.attributes_scd2) if a.strip()
    }
    sobra = sorted(set(proposed_mapping) - contract_attrs_lower)
    if sobra:
        findings.append({
            "tipo": "info",
            "campo": table,
            "mensaje": (
                f"Step '{step_name}' para '{table}': {', '.join(sobra)} en 'fields' del modelo no "
                "pertenece(n) al contrato de esta dimensión — ignorado(s) (vocabulario cruzado con "
                "otra tabla)."
            ),
        })

    upstream_exact = (
        {u.strip().lower(): u for u in upstream_fields} if upstream_fields is not None else None
    )
    fields: list[dict] = []
    for attr in (*contract.attributes_scd1, *contract.attributes_scd2):
        stream_field, inferred = _resolve_stream_field(attr, upstream_exact, proposed_mapping)
        if stream_field is None:
            candidatos = ", ".join(sorted(upstream_fields)) if upstream_fields else "(ninguno)"
            findings.append({
                "tipo": "error",
                "campo": table,
                "mensaje": (
                    f"Step '{step_name}' para '{table}': atributo '{attr}' del contrato no tiene "
                    f"campo homónimo en el stream de entrada — candidatos disponibles: {candidatos}. "
                    "Atributo omitido de 'fields', revisar el mapeo stream→columna a mano."
                ),
            })
            continue

        fields.append({
            "stream_field": stream_field,
            "table_field": attr,
            "type": derive_attribute_update_mode(attr, contract.attributes_scd1, contract.attributes_scd2),
        })
        if inferred:
            findings.append({
                "tipo": "info",
                "campo": table,
                "mensaje": (
                    f"Step '{step_name}' para '{table}': el mapeo '{stream_field}' → '{attr}' fue "
                    "inferido automáticamente — verificar antes de ejecutar en Spoon."
                ),
            })
    new_cfg["fields"] = fields
    return new_cfg, findings


def _dimension_step_table_counts(ktr_data: dict, step_type_aliases: dict[str, str]) -> dict[str, int]:
    """D58: cuántos steps DimensionLookup/CombinationLookup targetean cada
    tabla, en TODO ktr_data (no en el sub-árbol de un BFS) — precomputado una
    sola vez, reusado por cada step del loop principal.

    Por qué hace falta: role_of_dimension_step() (D16/H21) fue diseñado para
    DESAMBIGUAR entre 2+ steps candidatos sobre la misma tabla (el patrón
    "loader en rama muerta" + "lookup de FK que alimenta el hecho" de
    err1.ktr/err2.ktr). Aplicado a un ÚNICO step candidato, el BFS puede
    clasificar mal: un loader cuyo propio return_field alimenta, vía hops,
    la carga del hecho (patrón normal — no hace falta un segundo step
    dedicado a FK si el loader mismo devuelve la SK) llega a un escritor de
    OTRA tabla más adelante en el grafo, y el BFS lo declara "fact_lookup"
    aunque sea el único step que existe para esa tabla — no puede ser
    lectura de solo-FK si nadie más la carga. Confirmado contra corrida real
    (etl-llm-raw-test-01_sonnet_fase4.json): 'Cargar dim_producto', único
    DimensionLookup sobre dim_producto, alimenta 'Cargar fact_inventario'
    (InsertUpdate, tabla distinta) — BFS resuelve fact_lookup, aunque el
    step trae los 6 atributos de negocio de la dimensión en 'fields' y es,
    sin ambigüedad posible, el loader.

    Verificado ANTES de escribir esto (no asumido): ¿puede una tabla de
    dim_contracts cargarse en un .ktr FÍSICO distinto del que ve esta
    función, dejando acá solo un lookup de solo-lectura huérfano (que este
    conteo forzaría, mal, a loader)? No, con el pipeline actual:
    apply_dimension_contracts corre SIEMPRE sobre el dict completo de
    UNA sola etapa (KTR_2, STG→DWH) ANTES de que compute_cut()/
    split_ktr_by_cut() la fragmente en N archivos físicos (etl_generator.py:
    build_etl_from_raw líneas ~1150-1160 y el flujo síncrono ~1392 corren
    antes de _build_response_from_two_ktr_data/_build_ktr_stage, que es
    donde ocurre la fragmentación) — así que este conteo siempre ve TODOS
    los steps de dimensión de la etapa, nunca un subconjunto ya partido en
    archivos separados. Y KTR_1 (origen→STG) no tiene steps DWH — las
    dimensiones solo se cargan en KTR_2, nunca en otro archivo de la misma
    corrida. No existe hoy ningún mecanismo de dimensión compartida entre
    ETLs distintos (DimContract no lleva ese campo — ver DimContract en
    schemas/etl_schemas.py:145-162, puramente descriptivo del contrato SCD,
    sin flag de alcance/archivo).

    Riesgo DISTINTO, encontrado en la misma verificación: un único step
    candidato NO implica por sí solo que sea el loader — si el LLM omite el
    loader real de una tabla declarada en dim_contracts, el step remanente
    (un lookup huérfano) también cuenta 1. Este conteo solo resuelve la
    pregunta "¿hay ambigüedad ENTRE candidatos?" (no). O3 (docs/refactor/
    30-decision-python-llm.md) decidió no perseguir más la pregunta "¿ESTE
    candidato es realmente el loader?" con contenido de `fields` — con un
    solo candidato se fuerza a loader igual, y si está mal el síntoma queda
    visible en los findings de build_dimension_lookup_config (ver el caller,
    apply_dimension_contracts)."""
    counts: dict[str, int] = {}
    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        if canonical not in DIMENSION_STEP_TYPES:
            continue
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        table = (cfg.get("table") or "").strip().lower()
        if table:
            counts[table] = counts.get(table, 0) + 1
    return counts


def apply_dimension_contracts(
    ktr_data: dict,
    dim_contracts: list,
    step_type_aliases: dict[str, str],
    validaciones_modelo: list | None = None,
) -> list[dict]:
    """O3 (docs/refactor/30-decision-python-llm.md): reemplaza
    enforce_dimension_step_policy. Esa función comparaba lo que el modelo
    había escrito contra lo que el contrato deriva, y corregía si divergían
    — tenía sentido cuando el modelo escribía el config completo. Ahora no
    lo escribe: el prompt ya no le pide update/return_field/date_from/
    date_to/version_field/fields[].type (ver system_etl.txt, bloque "STEP DE
    DIMENSIONES"), así que no hay nada de eso para comparar. Esta función
    CONSTRUYE el config, siempre, para todo step de dimensión con contrato y
    sin override — no hay rama "ya venía bien" ni rama "corregir si difiere".

    Por step, en orden:
    1. Resuelve `table` (T1/D62: sin tabla no es defecto salvo que el step
       SEA de tipo dimensión) y el `contract` correspondiente. Sin match en
       dim_contracts: reporta (typo/mayúsculas, o dimensión sin contrato) —
       verificación legítima de lo que el modelo aportó, D60 "reporta, no
       repara".
    2. Tipo de step fuera de {DimensionLookup, CombinationLookup} sobre una
       tabla de dim_contracts: error, no se corrige — es topología (un
       TableOutput apuntando a una dimensión no es un problema de config).
    3. Override registrado (OVERRIDE_STEP_PREFIX): no se sintetiza nada, el
       step queda tal cual — único gate, antes se preguntaba en tres lugares
       distintos de esta misma función.
    4. Rol (loader vs. fact_lookup) vía role_of_dimension_step() — BFS sobre
       la TOPOLOGÍA que el modelo dibujó, D16. Con un único step candidato
       sobre la tabla (table_step_counts <= 1) no puede haber doble escritor
       sin importar el rol que resuelva el BFS, así que se fuerza a loader:
       si el modelo omitió el loader real, el síntoma queda visible como un
       loader con pocos atributos + findings de error (build_dimension_lookup_config
       los reporta), nunca como una escritura silenciosa perdida.
    5. build_dimension_lookup_config() construye el config completo desde el
       contrato — `update` sale del rol (Y=loader, N=fact_lookup), nunca de
       lo que el modelo haya puesto.

    Devuelve dicts {"tipo", "campo", "mensaje"} listos para Validacion(**v).
    Muta ktr_data in-place."""
    if not dim_contracts:
        return []

    contracts_by_table = {c.table.strip().lower(): c for c in dim_contracts}
    validaciones_modelo = validaciones_modelo or []
    results: list[dict] = []
    table_step_counts = _dimension_step_table_counts(ktr_data, step_type_aliases)

    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        # H4: alias de tabla resuelto vía contracts.STEP_CONTRACTS.key_aliases
        # (misma fuente que el builder XML), no un `or` inline propio.
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        table, message = resolve_step_table(step.get("name", ""), cfg.get("table"))
        if table is None:
            # T1/D62: la mayoría de los steps de una transformación no tocan
            # ninguna tabla de dim_contracts (Sort, FilterRows...) — para esos,
            # "sin tabla" es el caso normal, no un defecto. Un DimensionLookup/
            # CombinationLookup sin tabla configurada sí lo es: ese tipo de step
            # no tiene razón de ser sin una tabla que cargar/consultar.
            if canonical in DIMENSION_STEP_TYPES and message is not None:
                results.append({"tipo": "error", "campo": "", "mensaje": message})
            continue
        contract = contracts_by_table.get(table.lower())
        if contract is None:
            if canonical in DIMENSION_STEP_TYPES:
                results.append({
                    "tipo": "warning",
                    "campo": table,
                    "mensaje": (
                        f"Step '{step.get('name')}' es '{canonical}' (carga de dimensión) para la tabla "
                        f"'{table}', que no aparece en dim_contracts — no se pudo sintetizar el config "
                        "contra el contrato. Revisar si es un typo/mayúsculas distinto al nombre declarado "
                        "en dim_contracts, o si a esa dimensión le falta el contrato."
                    ),
                })
            continue

        if canonical not in DIMENSION_STEP_TYPES:
            # D60: reporta, no repara — un step que no es DimensionLookup ni
            # CombinationLookup sobre una tabla de dim_contracts es un error
            # de topología (el modelo eligió el step equivocado), no de
            # config; no hay contrato del cual sintetizar un tipo distinto.
            results.append({
                "tipo": "error",
                "campo": table,
                "mensaje": (
                    f"Step '{step.get('name')}' para '{table}' es '{canonical}', pero esa tabla está "
                    "en dim_contracts — un step de dimensión tiene que ser 'DimensionLookup' o, con "
                    "override registrado, 'CombinationLookup'. No se corrigió automáticamente."
                ),
            })
            continue

        if has_registered_override(validaciones_modelo, table):
            logger.info(
                "apply_dimension_contracts: override registrado para '%s' — step respetado tal cual.",
                table,
            )
            continue

        # D16 — el rol decide `update`. Un step que solo busca la FK de esta
        # dimensión del lado del hecho (no la carga) nunca debe quedar como
        # escritor, sin importar qué haya puesto el modelo — ver H21/H22/D16.
        role = role_of_dimension_step(step.get("name", ""), table, ktr_data, step_type_aliases)
        role_forced = False
        if role == "fact_lookup" and table_step_counts.get(table.lower(), 0) <= 1:
            # D58, simplificado por O3: con un único step candidato sobre la
            # tabla no puede haber doble escritor sin importar el rol que
            # resuelva el BFS — antes acá se discriminaba inspeccionando si
            # 'fields' del modelo traía el contrato completo (evidencia de
            # intención); ya no hace falta: 'fields' del modelo ya no es
            # prueba de intención, es apenas una pista de mapeo que
            # build_dimension_lookup_config valida contra el stream real. Si
            # el modelo omitió el loader real, el síntoma es normalmente un
            # loader con pocos atributos resueltos + findings de error —
            # visible, salvo la excepción de abajo (upstream no resoluble).
            role = "loader"
            role_forced = True
        update = "Y" if role == "loader" else "N"

        # Campos reales del stream que llega a este step — insumo de
        # build_dimension_lookup_config para no asumir stream_field==table_field
        # en silencio (hallazgo, 01-hallazgos.md).
        upstream = upstream_fields_for_step(ktr_data, step_type_aliases, step.get("name", ""))
        if role_forced and upstream is None:
            # Excepción a la nota de arriba: si el rol se forzó de fact_lookup a
            # loader (D58) Y el grafo desde este step no es resoluble (sin
            # predecesor — ver upstream_fields_for_step), build_dimension_lookup_config
            # no tiene contra qué verificar 'fields' y cae al fallback de
            # identidad SIN VERIFICAR (mismo comportamiento que un loader
            # legítimo con grafo no resoluble) — pero acá, a diferencia de un
            # loader legítimo, no hay ninguna otra señal de que este step sea
            # de verdad el loader. Sin este aviso la fabricación sería
            # silenciosa — D60 exige reportar, nunca callar.
            results.append({
                "tipo": "warning",
                "campo": table,
                "mensaje": (
                    f"Step '{step.get('name')}' es el único candidato para '{table}' y su topología "
                    "sugería lookup de FK (D58) — forzado a loader porque con un solo candidato no "
                    "puede haber doble escritor (D16), pero el stream que le llega no se pudo resolver "
                    "(sin predecesor): el mapeo de 'fields' se asume por identidad SIN VERIFICAR contra "
                    "columnas reales. Confirmar en Spoon que este step es de verdad el loader de la "
                    "dimensión antes de ejecutar."
                ),
            })
        new_cfg, notes = build_dimension_lookup_config(
            contract, update=update, model_config=cfg, upstream_fields=upstream,
            step_name=step.get("name", ""), table=table,
        )
        step["type"] = "DimensionLookup"  # D44: siempre, para todo scd_type
        step["config"] = new_cfg
        results.extend(notes)

    return results
