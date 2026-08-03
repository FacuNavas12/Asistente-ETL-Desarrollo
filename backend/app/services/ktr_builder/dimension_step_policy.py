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
"""
from __future__ import annotations

import logging

from app.domain.scd import (
    ATTRIBUTE_UPDATE_TYPE_CODES,
    VALUE_META_TYPE_NAMES,
    derive_attribute_update_mode,
    derive_dimension_loader_step,
    derive_fact_lookup_step,
)
from app.services.ktr_builder.contracts import normalize_config, parse_cfg
from app.services.ktr_builder.fields_validate import upstream_fields_for_step

logger = logging.getLogger(__name__)

_VALID_VALUE_META_NAMES = {c.lower() for c in VALUE_META_TYPE_NAMES}

__all__ = [
    "OVERRIDE_STEP_PREFIX",
    "DIMENSION_STEP_TYPES",
    "derive_dimension_loader_step",
    "derive_fact_lookup_step",
    "derive_attribute_update_mode",
    "ATTRIBUTE_UPDATE_TYPE_CODES",
    "role_of_dimension_step",
    "enforce_dimension_step_policy",
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


def _has_registered_override(validaciones: list, table: str) -> bool:
    table_lower = table.strip().lower()
    for v in validaciones or []:
        mensaje = str(v.get("mensaje", "") if isinstance(v, dict) else getattr(v, "mensaje", ""))
        campo = str(v.get("campo", "") if isinstance(v, dict) else getattr(v, "campo", "")).strip().lower()
        if mensaje.startswith(OVERRIDE_STEP_PREFIX) and campo == table_lower:
            return True
    return False


def _synthesize_dimension_lookup_config(
    cfg: dict,
    contract,
    *,
    update: str,
    upstream_fields: set[str] | None = None,
    repaired_mapping: dict[str, str] | None = None,
    findings: list[dict] | None = None,
    step_name: str = "",
    table: str = "",
) -> dict:
    """D44/D51: reconstruye el config de DimensionLookup a partir del
    DimContract al reparar CombinationLookup -> DimensionLookup (dirección
    invertida respecto de la versión anterior de esta política, que hacía el
    downgrade opuesto). Nunca inventa: technical_key/version_field/date_from/
    date_to son obligatorios en TODA dimensión de dim_contracts (V1/V3,
    prompt_validacion_src.txt), y attributes_scd1/attributes_scd2 son el
    contrato completo de atributos no-clave (D37) — el modo de cada uno sale
    de derive_attribute_update_mode() (S-8), nunca del default silencioso
    "Insert" del emisor. `keys` se preserva del config original (ya resuelto
    por el LLM contra la clave natural, y compatible sin mapeo: CombinationLookup
    ya emite {"stream"/"name", "lookup"}, que DimensionLookup también acepta)
    — no se reconstruye desde contract.natural_keys, que no trae el nombre
    del campo del lado del stream.

    `update="N"` (reparación de rol fact_lookup, D16): sin `fields` — un
    lookup de solo lectura no necesita el modo de actualización de cada
    atributo, solo matchear por keys + rango de fechas y devolver
    return_field.

    upstream_fields (hallazgo, docs/refactor/01-hallazgos.md): campos
    realmente disponibles en el stream que llega a este step (ver
    fields_validate.upstream_fields_for_step). None = no resoluble con
    certeza (sin predecesor claro en el grafo) — preserva el comportamiento
    histórico de acá abajo (asume stream_field == table_field, sin
    verificar). Cuando SÍ es resoluble, un atributo del contrato sin
    homónimo en el stream YA NO se mapea por identidad — se omite de
    `fields` y se reporta en `findings` (si el caller lo pasa) en vez de
    asumir en silencio que el nombre del stream coincide con el de la
    columna destino. Esa asunción, sin este chequeo, generó mapeos
    incorrectos reales: corpus etl-llm-raw-test-01_sonnet_fase4.json,
    'Cargar dim_producto' — el contrato pide 'nombre_categoria', el stream
    trae 'categoria' (nunca homónimos), y el código viejo hubiera declarado
    stream_field='nombre_categoria' igual, produciendo un .ktr que abre en
    Spoon y falla en runtime con 'Could not find field nombre_categoria in
    stream' — sin ningún aviso previo.

    repaired_mapping (table_field.lower() -> stream_field, opcional): salida
    de un repair dirigido (repair.py, un step aislado) — único lugar donde
    esta función construye 'fields', para no duplicar la lógica en el
    caller (mismo argumento que ya decidió que el checker de arriba viviera
    acá y no en validators/). Por atributo, en orden de prioridad: (1) si
    hay entrada en repaired_mapping Y esa entrada existe de verdad en
    upstream_fields (el repair también puede alucinar — se revalida igual
    que la identidad, nunca se confía a ciegas en la respuesta del modelo);
    (2) si no, identidad verificada contra upstream_fields (comportamiento
    de arriba); (3) si no, se omite + finding severity=error. Cuando (1)
    resuelve con un nombre DISTINTO al del atributo (inferencia real, no
    coincidencia), se agrega ADEMÁS un finding severity=info — un mapeo
    inferido por una máquina tiene que quedar visible para el experto que
    abre el .ktr en Spoon, no solo funcionar en silencio (mismo principio
    que motivó todo este chequeo, aplicado también al camino feliz)."""
    new_cfg: dict = {
        "schema": cfg.get("schema", ""),
        "table": cfg.get("table", ""),
        "connection": cfg.get("connection", ""),
        "return_field": cfg.get("return_field") or cfg.get("returnfield") or contract.technical_key,
        "keys": cfg.get("keys", []),
        "update": update,
        "date_from": contract.date_from,
        "date_to": contract.date_to,
        "version_field": contract.version_field,
    }
    if update == "Y":
        upstream_lower = (
            {u.strip().lower() for u in upstream_fields} if upstream_fields is not None else None
        )
        fields: list[dict] = []
        for attr in (*contract.attributes_scd1, *contract.attributes_scd2):
            attr_lower = attr.strip().lower()
            stream_field: str | None = None
            inferred = False

            repaired_candidate = (repaired_mapping or {}).get(attr_lower)
            if (
                repaired_candidate
                and upstream_lower is not None
                and repaired_candidate.strip().lower() in upstream_lower
            ):
                stream_field = repaired_candidate.strip()
                inferred = stream_field.lower() != attr_lower

            if stream_field is None and (upstream_lower is None or attr_lower in upstream_lower):
                stream_field = attr

            if stream_field is None:
                if findings is not None:
                    candidatos = ", ".join(sorted(upstream_fields)) if upstream_fields else "(ninguno)"
                    findings.append({
                        "tipo": "error",
                        "campo": table,
                        "mensaje": (
                            f"Step '{step_name}' para '{table}': atributo '{attr}' del contrato no tiene "
                            f"campo homónimo en el stream de entrada — candidatos disponibles: {candidatos}. "
                            "No se asume igualdad de nombre por default (identidad sin verificar generó "
                            "mapeos incorrectos en silencio antes de este chequeo, ver hallazgo en "
                            "01-hallazgos.md) — atributo omitido de 'fields', revisar el mapeo "
                            "stream→columna a mano."
                        ),
                    })
                continue

            fields.append({
                "stream_field": stream_field,
                "table_field": attr,
                "type": derive_attribute_update_mode(attr, contract.attributes_scd1, contract.attributes_scd2),
            })
            if inferred and findings is not None:
                findings.append({
                    "tipo": "info",
                    "campo": table,
                    "mensaje": (
                        f"Step '{step_name}' para '{table}': el mapeo '{stream_field}' → '{attr}' fue "
                        "inferido automáticamente (el contrato declara la columna, el stream no tiene "
                        "campo homónimo) — verificar antes de ejecutar en Spoon."
                    ),
                })
        new_cfg["fields"] = fields
    return new_cfg


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
    enforce_dimension_step_policy corre SIEMPRE sobre el dict completo de
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

    Riesgo DISTINTO, encontrado en la misma verificación y CERRADO en el
    caller (enforce_dimension_step_policy), no acá: un único step candidato
    NO implica por sí solo que sea el loader — si el LLM omite el loader
    real de una tabla declarada en dim_contracts, el step remanente (un
    lookup huérfano) también cuenta 1. Este conteo solo resuelve la
    pregunta "¿hay ambigüedad ENTRE candidatos?" (no) — la pregunta "¿ESTE
    candidato es realmente el loader?" la responde el caller comparando
    `fields` contra los atributos que el contrato declara (ver ahí)."""
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


def enforce_dimension_step_policy(
    ktr_data: dict,
    dim_contracts: list,
    step_type_aliases: dict[str, str],
    validaciones_modelo: list | None = None,
    repaired_mappings: dict[str, dict[str, str]] | None = None,
) -> list[dict]:
    """repaired_mappings (por nombre de step, opcional — hallazgo en
    01-hallazgos.md): mapeo table_field->stream_field que un repair dirigido
    (repair.py) ya validó para ESE step, pasado tal cual a
    _synthesize_dimension_lookup_config en los dos call sites que arman
    'fields' de un loader (rol loader con update!=Y, y upgrade
    CombinationLookup->DimensionLookup). El caller (etl_generator.py) es
    quien decide si vale la pena una segunda pasada con esto — acá solo se
    enhebra, no se decide nada nuevo.

    Compara, para cada step que carga/consulta una tabla listada en
    dim_contracts, el tipo realmente usado contra el step que corresponde
    según su ROL (D16: loader vs. fact_lookup) — derive_dimension_loader_step/
    derive_fact_lookup_step, D44/D51: ambos son 'DimensionLookup' para TODO
    scd_type, ver docstring de esas funciones en domain/scd.py.

    Desenlaces:
    - Coinciden, o hay un override registrado (OVERRIDE_STEP_PREFIX en
      validaciones con campo == tabla): no se toca nada.
    - Rol fact_lookup sin solo-lectura: se fuerza update="N" — si el step ya
      es DimensionLookup, in-place; si es CombinationLookup (sin modo de
      solo-lectura), se convierte sintetizando el config desde el contrato
      (_synthesize_dimension_lookup_config). R-K2 (rango [date_from, date_to)
      resuelve bien incluso en dimensiones sin historial real) cierra el
      residual que D16 dejaba abierto acá.
    - Rol loader con CombinationLookup donde el contrato pide DimensionLookup
      (D44/D51: TODO scd_type, 0/1/2): reparación SEGURA — se sintetiza
      fields/date_from/date_to/version_field desde el contrato, que ya los
      declara completos. Se corrige in-place y se reporta tipo="warning".
      (Antes de D44 era la dirección opuesta — downgrade DimensionLookup ->
      CombinationLookup — invertida por completo.)
    - Cualquier otro desajuste (tipo de step fuera de
      {DimensionLookup, CombinationLookup} sobre una tabla de dim_contracts):
      NO se corrige — mismo principio que check_missing_required_fields en
      ktr_default_validator.py ("reporta, no repara"). tipo="error".

    Devuelve dicts {"tipo", "campo", "mensaje"} listos para Validacion(**v).
    Muta ktr_data in-place solo en los casos de reparación segura."""
    if not dim_contracts:
        return []

    contracts_by_table = {c.table.strip().lower(): c for c in dim_contracts}
    validaciones_modelo = validaciones_modelo or []
    repaired_mappings = repaired_mappings or {}
    results: list[dict] = []
    table_step_counts = _dimension_step_table_counts(ktr_data, step_type_aliases)

    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        mapping_for_step = repaired_mappings.get(step.get("name", ""))
        # H4: alias de tabla resuelto vía contracts.STEP_CONTRACTS.key_aliases
        # (misma fuente que el builder XML), no un `or` inline propio.
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        table = (cfg.get("table") or "").strip()
        if not table:
            continue
        contract = contracts_by_table.get(table.lower())
        if contract is None:
            if canonical in DIMENSION_STEP_TYPES:
                results.append({
                    "tipo": "warning",
                    "campo": table,
                    "mensaje": (
                        f"Step '{step.get('name')}' es '{canonical}' (carga de dimensión) para la tabla "
                        f"'{table}', que no aparece en dim_contracts — no se pudo verificar el tipo de step "
                        "contra el contrato. Revisar si es un typo/mayúsculas distinto al nombre declarado "
                        "en dim_contracts, o si a esa dimensión le falta el contrato."
                    ),
                })
            continue

        expected = derive_dimension_loader_step(contract.scd_type)  # "DimensionLookup", siempre (D44/R-K7)
        # Hallazgo (01-hallazgos.md): campos reales del stream que llega a
        # este step — insumo de _synthesize_dimension_lookup_config para no
        # asumir stream_field==table_field en silencio (ver su docstring).
        # Se calcula una sola vez por step, se pasa a los 3 call sites de
        # más abajo que puedan sintetizar 'fields'.
        upstream = upstream_fields_for_step(ktr_data, step_type_aliases, step.get("name", ""))

        # D16 (Paso 4) — el rol decide qué regla aplica primero. Un step que
        # solo busca la FK de esta dimensión del lado del hecho (no la carga)
        # nunca debe quedar como escritor, sin importar qué deriva el
        # contrato — ver H21/H22/D16 en 01-hallazgos.md/02-decisiones.md.
        if canonical in DIMENSION_STEP_TYPES:
            role = role_of_dimension_step(step.get("name", ""), table, ktr_data, step_type_aliases)
            # D58: el BFS declara "fact_lookup" apenas alcanza, aguas abajo,
            # un escritor de OTRA tabla — señal que se rompe exactamente
            # cuando ESTE step es el loader y su propio return_field
            # alimenta esa escritura (patrón normal: no hace falta un
            # segundo step de FK si el loader mismo devuelve la SK).
            # role_of_dimension_step() (D16/H21) fue diseñado para
            # desambiguar entre 2+ candidatos sobre la misma tabla — con 1
            # solo candidato no hay nadie más que pueda estar cargándola,
            # así que "fact_lookup" es sospechoso, no concluyente. Pero "es
            # el único candidato" tampoco alcanza para forzarlo a loader:
            # un lookup huérfano (LLM omitió el loader real) también sería
            # el único candidato, y forzar update=Y ahí sería una escritura
            # silenciosa sobre una dimensión que este step nunca demostró
            # cargar — la clase de falla que este ciclo existe para
            # eliminar. Se discrimina por contenido: un loader trae, en
            # 'fields', los atributos de negocio que el contrato declara
            # (D37: attributes_scd1/attributes_scd2 son "el contrato
            # completo de atributos no-clave" — domain/scd.py; ver también
            # el docstring de _synthesize_dimension_lookup_config más
            # arriba, que construye 'fields' con EXACTAMENTE ese conjunto
            # completo al sintetizar un loader real). Un lookup de FK no
            # tiene razón de negocio para declarar el conjunto COMPLETO de
            # atributos — como mucho trae columnas de retorno puntuales
            # (P3-1). Se exige el conjunto COMPLETO, no "alguno"/"la
            # mayoría": un match parcial es indistinguible de esas columnas
            # de retorno legítimas, y ante esa ambigüedad se reporta, no se
            # fuerza (D5). Contrato sin atributos declarados (dimensión
            # solo con claves) es vacuamente verdadero — no hay nada que un
            # loader real deba traer en 'fields' en ese caso, así que no
            # hay señal para discriminar; límite conocido, documentado, no
            # resuelto acá.
            #
            # Cuando el BFS YA dice "loader" (rama muerta, o simplemente no
            # hay hop que llegue a otra tabla) esto ni se evalúa — el
            # conteo de candidatos solo interviene para CORREGIR un
            # "fact_lookup" sospechoso, nunca para pisar un "loader" que el
            # BFS ya resolvió sin ambigüedad (evita romper los casos donde
            # el step llega incompleto a propósito, ej. H51/CombinationLookup,
            # y 'fields' todavía no existe porque esta misma función lo va
            # a sintetizar).
            if role == "fact_lookup" and table_step_counts.get(table.lower(), 0) <= 1:
                contract_attrs = {
                    a.strip().lower() for a in (*contract.attributes_scd1, *contract.attributes_scd2)
                    if a.strip()
                }
                if contract_attrs:
                    # Misma prioridad de clave que el emisor real (lookups.py:88:
                    # f.get("lookup") or f.get("table_field") or f.get("name", "")).
                    field_dest = {
                        str(f.get("lookup") or f.get("table_field") or f.get("name") or "").strip().lower()
                        for f in (cfg.get("fields") or [])
                    }
                    if contract_attrs <= field_dest:
                        role = "loader"
                    else:
                        missing = sorted(contract_attrs - field_dest)
                        # Hallazgo (01-hallazgos.md): el discriminador de D58
                        # solo miraba qué falta. 'sobra' (nombres en 'fields'
                        # que NO pertenecen al contrato de esta dimensión) es
                        # la otra mitad de la señal — vocabulario cruzado con
                        # otra tabla (típicamente la de hechos), confirmado
                        # contra corpus real (etl-llm-raw-test-01_sonnet_
                        # fase4.json, 'Cargar dim_producto': fk_categoria/
                        # precio_lista/stock son columnas de fact_inventario,
                        # no de dim_producto). 'repairable' es el marcador que
                        # el caller (etl_generator.py) usa para saber a qué
                        # findings les puede seguir un intento de repair
                        # dirigido — no se re-deriva la condición del
                        # discriminador en otro lado (drift garantizado).
                        sobra = sorted(field_dest - contract_attrs)
                        results.append({
                            "tipo": "error",
                            "campo": table,
                            "mensaje": (
                                f"Step '{step.get('name')}' es la única candidata para '{table}' "
                                "(dimensión declarada en dim_contracts), pero no trae en 'fields' los "
                                f"atributos que el contrato declara — falta(n): {', '.join(missing)}."
                                + (f" Sobra(n) (no pertenecen a esta dimensión): {', '.join(sobra)}." if sobra else "")
                                + " Probable loader faltante (este step parece un lookup huérfano, no el "
                                "loader) — no se fuerza update=Y sobre una tabla que este step no "
                                "demuestra cargar."
                            ),
                            "repairable": True,
                            "step_name": step.get("name", ""),
                            "missing": missing,
                            "sobra": sobra,
                        })
                        continue
                else:
                    role = "loader"
            if role == "fact_lookup":
                if _has_registered_override(validaciones_modelo, table):
                    logger.info(
                        "enforce_dimension_step_policy: override registrado para '%s' — "
                        "rol fact_lookup no forzado a solo-lectura.", table,
                    )
                    continue
                already_readonly = (
                    canonical == "DimensionLookup"
                    and str(cfg.get("update", "Y")).strip().upper() == "N"
                )
                if already_readonly:
                    # D58: mismo defecto de clase que H51 (continue mudo de
                    # la línea ~329 antes de su fix) y que D57 ya cerró para
                    # el branch de reclasificación de abajo — acá el step ya
                    # llegó en modo N, pero eso no garantiza que 'fields'
                    # tenga vocabulario de modo N (D-1). No se repara (no hay
                    # contrato para inventar qué hacer con columnas de
                    # retorno legítimas en modo N, D5/D45 pt.1 "reporta, no
                    # repara") — se valida y se reporta si está cruzado, en
                    # vez de dar el step por bueno en silencio.
                    crossed = [
                        f.get("stream_field") or f.get("stream") or f.get("name") or "?"
                        for f in (cfg.get("fields") or [])
                        if str(f.get("type") or "").strip().lower() not in _VALID_VALUE_META_NAMES
                    ]
                    if crossed:
                        results.append({
                            "tipo": "error",
                            "campo": table,
                            "mensaje": (
                                f"Step '{step.get('name')}' para '{table}': ya en modo N (solo lectura), "
                                f"pero {len(crossed)} campo(s) en 'fields' ({', '.join(crossed)}) usa(n) "
                                "vocabulario fuera de modo N (String/Number/Integer/BigNumber/Date/"
                                "Boolean/Binary/Timestamp) — vocabulario cruzado (D-1), no corregido "
                                "automáticamente."
                            ),
                        })
                    continue
                if canonical == "CombinationLookup":
                    # D44/D51: CombinationLookup no tiene modo solo-lectura —
                    # antes se reportaba sin reparar (D16 residual); R-K2
                    # (rango [date_from, date_to) resuelve bien incluso sin
                    # historial real) cierra ese residual, se sintetiza el
                    # DimensionLookup(update=N) equivalente desde el contrato.
                    new_cfg = _synthesize_dimension_lookup_config(
                        cfg, contract, update="N", upstream_fields=upstream, findings=results,
                        step_name=step.get("name", ""), table=table,
                    )
                else:
                    # D57: el step ya era DimensionLookup, con `fields` armado
                    # bajo la premisa (declarada falsa acá, por esta misma
                    # reclasificación) de que era el loader — vocabulario
                    # modo Y (Insert/Update/...). Forzar update=N sin tocar
                    # `fields` deja ese vocabulario viejo en un step ahora en
                    # modo N, donde el vocabulario válido es otro (D-1) — el
                    # vocabulario cruzado exacto que build_ktr()/lookups.py
                    # rechaza con KtrBuilderError. DimensionLookupMeta.
                    # getFields() (pentaho-kettle, 776-803) trata `fields`
                    # vacío en modo N como la rama contemplada (columnas de
                    # retorno opcionales), no como un degradado — se limpia,
                    # no se sintetiza (ver D57 en 02-decisiones.md: la fuente
                    # de columnas de retorno legítimas en modo N queda fuera
                    # de esta reparación, no está definida todavía).
                    discarded_fields = cfg.get("fields") or []
                    new_cfg = dict(cfg)
                    new_cfg["update"] = "N"
                    new_cfg["fields"] = []
                    if discarded_fields:
                        results.append({
                            "tipo": "warning",
                            "campo": table,
                            "mensaje": (
                                f"Step '{step.get('name')}' para '{table}': "
                                f"{len(discarded_fields)} campo(s) descartado(s) al forzar "
                                "solo lectura (D57) — su vocabulario de <field><update> "
                                "asumía que el step era loader (modo Y); reclasificado a "
                                "fact_lookup en modo N, ese vocabulario ya no pertenece al "
                                "modo del step (D-1) y se limpia en vez de emitirse cruzado."
                            ),
                            "repaired": True,
                        })
                step["type"] = "DimensionLookup"
                step["config"] = new_cfg
                results.append({
                    "tipo": "warning",
                    "campo": table,
                    "mensaje": (
                        f"Step '{step.get('name')}' para '{table}' es un lookup de FK del lado del "
                        "hecho, no el loader de la dimensión — forzado a DimensionLookup con "
                        "update=N (solo lectura) para evitar doble escritor sobre la misma tabla "
                        "(D16). El rango [date_from, date_to) resuelve bien incluso sin historial "
                        "real (R-K2)."
                    ),
                })
                continue
            # role == "loader": cae al chequeo general de abajo.
            if canonical == "DimensionLookup" and str(cfg.get("update", "Y")).strip().upper() != "Y":
                if _has_registered_override(validaciones_modelo, table):
                    results.append({"tipo": "info", "campo": table, "mensaje": (
                        f"Step '{step.get('name')}' para '{table}': loader con update=N, override "
                        f"'{OVERRIDE_STEP_PREFIX}' registrado — no se corrige, respetado tal cual."
                    )})
                    continue
                new_cfg = _synthesize_dimension_lookup_config(
                    cfg, contract, update="Y", upstream_fields=upstream, repaired_mapping=mapping_for_step,
                    findings=results, step_name=step.get("name", ""), table=table,
                )
                step["config"] = new_cfg
                results.append({"tipo": "warning", "campo": table, "mensaje": (
                    f"Step '{step.get('name')}' para '{table}' es el loader (rol) pero tenía "
                    "update=N — corregido a update=Y y vocabulario de campos regenerado desde "
                    "dim_contracts (H51)."
                )})
                continue

        if canonical == expected:
            continue
        if _has_registered_override(validaciones_modelo, table):
            logger.info(
                "enforce_dimension_step_policy: override registrado para '%s' (%s en vez de %s) — respetado.",
                table, canonical, expected,
            )
            continue

        if canonical == "CombinationLookup":
            # D44/D51: única reparación segura, dirección invertida respecto
            # de antes — CombinationLookup -> DimensionLookup, sintetizando
            # fields/date_from/date_to/version_field desde el contrato
            # (disponibles siempre: V1/V3 de prompt_validacion_src.txt los
            # exige en TODA dimensión, sea scd_type 0, 1 o 2).
            new_cfg = _synthesize_dimension_lookup_config(
                cfg, contract, update="Y", upstream_fields=upstream, repaired_mapping=mapping_for_step,
                findings=results, step_name=step.get("name", ""), table=table,
            )
            step["type"] = "DimensionLookup"
            step["config"] = new_cfg
            results.append({
                "tipo": "warning",
                "campo": table,
                "mensaje": (
                    f"Step '{step.get('name')}' para '{table}' corregido de CombinationLookup a "
                    "DimensionLookup — D44/D51: vocabulario uniforme por rol, el loader es "
                    "'Dimension lookup/update' para todo scd_type (incluido 0/1, R-K7). Config "
                    "sintetizado desde dim_contracts (fields con modo por atributo, date_from, "
                    "date_to, version_field). Si el step correcto es otro (junk/technical "
                    f"dimension), registrá el override con el prefijo '{OVERRIDE_STEP_PREFIX}' y motivo."
                ),
            })
        else:
            results.append({
                "tipo": "error",
                "campo": table,
                "mensaje": (
                    f"Step '{step.get('name')}' para '{table}' es '{canonical}' pero el contrato "
                    f"(dim_contracts) deriva '{expected}' — sin override registrado. No se "
                    "corrigió automáticamente."
                ),
            })

    return results
