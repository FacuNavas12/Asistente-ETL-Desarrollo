"""
KTR serializer: convierte el ktr JSON dict devuelto por el LLM en XML .ktr válido
para Pentaho PDI. Orquestador delgado — la lógica de cada step vive en steps/*.py
(vía registry.py), la de conexiones en connection.py, el auto-layout en layout.py
y la validación de estructura pre-XML en validate.py.

No AI calls — pure Python data transformation.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

from app.core.config import settings
from app.services.ktr_builder.common import _sub, KtrBuilderError
from app.services.ktr_builder.connection import (
    _build_connection,
    _resolve_connection,
    _STEPS_NEEDING_CONNECTION,
    build_kettle_properties_template,
)
from app.services.ktr_builder.contracts import missing_required_keys, normalize_config, parse_cfg
from app.services.ktr_builder.fields_validate import (
    FIELD_INTEGRITY_PREFIX,
    repair_select_values_narrowing,
    validate_dimension_lookup_races,
    validate_field_resolution,
    validate_row_sources,
)
from app.services.ktr_builder.layout import _auto_layout
from app.services.ktr_builder.registry import (
    _CRITICAL_FIELDS,
    STEP_BUILDERS,
    STEP_TYPE_ALIASES,
    unmapped_config_keys,
)
from app.services.ktr_builder.validate import _validate_ktr
from app.services.ktr_default_validator import (
    check_missing_required_fields,
    scrub_function_default_constants,
)
from app.services.ktr_xml_validator import validate_ktr_xml

logger = logging.getLogger(__name__)


def _sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name).strip("_") or "Transformacion_ETL"


def _build_order(trans: Element, hops: list) -> None:
    order = SubElement(trans, "order")
    for hop in hops:
        h = SubElement(order, "hop")
        _sub(h, "from",    hop.get("from", ""))
        _sub(h, "to",      hop.get("to", ""))
        _sub(h, "enabled", "Y" if hop.get("enabled", True) else "N")


def build_ktr(
    ktr_data: dict,
    process_name: str = "",
    real_connections: dict[str, dict] | None = None,
    required_columns_by_table: dict[str, list[str]] | None = None,
    pass_source_connection: str | None = None,
    pass_dest_connection: str | None = None,
    strict_connections: bool = False,
) -> tuple[str, str, list[str]]:
    """
    Convert KTR JSON dict from Gemini response to .ktr XML string.

    real_connections: {nombre_lógico: {host, port, database, username, password, type, access}},
    ya resuelto por resolve_real_connections() — reemplaza los placeholders del
    modelo para esa conexión puntual. Conexiones sin entrada en el dict quedan
    con el placeholder que emitió el modelo (comportamiento actual).

    required_columns_by_table: {tabla: [columnas NOT NULL sin default]}, derivado
    por el caller a partir del DDL de staging/DWH (ver etl_generator). Opcional —
    None desactiva ese chequeo puntual sin afectar el resto del build.

    pass_source_connection / pass_dest_connection: nombres de conexión lógicos a
    usar como fallback por rol de step (TableInput → source, resto → dest) cuando
    el modelo omite 'connection' en el config. Pensado para el flujo de 2 KTR
    (origen→STG y STG→DWH) — ver _resolve_connection(). None/None preserva el
    fallback de inferencia por prefijo de tabla ya existente.

    strict_connections: si True, una conexión GENERIC que siga con
    host/database placeholder tras aplicar real_connections aborta el build
    (KtrXmlValidationError vía validate_ktr_xml) en vez de entregar un .ktr
    con credenciales sin resolver. Usar SOLO cuando el caller ya intentó
    resolver conexiones reales (ver _try_build en etl_generator.py) — en los
    demás flujos (preview sin conexiones aún elegidas) el placeholder es
    esperado y se documenta como advertencia + plantilla kettle.properties.

    Returns (ktr_xml_string, filename, warnings). Returns ("", "", []) if ktr_data is empty.
    """
    if not ktr_data:
        return "", "", []

    # Pass único de normalización: alias de clave -> canónica (StepContract,
    # ver contracts.py) ANTES de cualquier validación o emisión, así el
    # emisor XML y el validador de grafo de campos ven siempre las mismas
    # claves (mata el drift tipo inputField/input_field en origen) y el
    # config queda como dict (no string JSON) para el resto de esta función.
    # required_keys ausentes abortan acá mismo, apuntando al step culpable,
    # en vez de dejar que Spoon falle en runtime con un step "vacío".
    incomplete: list[str] = []
    for step in ktr_data.get("steps", []):
        canonical = STEP_TYPE_ALIASES.get(step.get("type", ""), step.get("type", ""))
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        step["config"] = cfg
        for key, reason in missing_required_keys(canonical, cfg):
            incomplete.append(f"Config incompleto en '{step.get('name')}' ({canonical}): {reason}")
    if incomplete:
        raise KtrBuilderError(" | ".join(incomplete))

    warnings = _validate_ktr(ktr_data)
    for w in warnings:
        logger.warning("KTR validation: %s", w)

    # Red de seguridad general (Fase 2): ningún .ktr sale con el texto de una
    # función SQL como valor constante de un campo Date/Timestamp, sin importar
    # si el modelo respetó o no la indicación del prompt.
    default_warnings = scrub_function_default_constants(ktr_data, STEP_TYPE_ALIASES)
    for w in default_warnings:
        logger.warning("KTR default validation: %s", w)
    warnings.extend(default_warnings)

    warnings.extend(
        check_missing_required_fields(ktr_data, STEP_TYPE_ALIASES, required_columns_by_table)
    )

    # Pre-pass mecánico: reinyecta en un SelectValues previo cualquier campo
    # que un consumidor aguas abajo necesite y que el modelo haya dejado
    # afuera de la lista explícita de select/fields (solo agrega, nunca quita
    # ni reinterpreta). Corre ANTES de las validaciones de integridad para que
    # el grafo que ellas ven ya tenga el field resuelto cuando es recuperable.
    warnings.extend(repair_select_values_narrowing(ktr_data, STEP_TYPE_ALIASES))

    # Validación de integridad ("integridad_campos"): grafo de campos +
    # fuente de filas + condición de carrera dimensión/lookup. Los tres son
    # el mismo síntoma en distintas formas — un .ktr que Spoon abre pero falla
    # (o vacía el pipeline) en runtime. NO abortan el build: el .ktr se genera
    # igual y cada error se agrega a `warnings` con FIELD_INTEGRITY_PREFIX —
    # etl_generator.py los promueve a Validacion tipo="error" (máxima
    # severidad que el frontend renderiza) para que el usuario decida si
    # corregirlos en Spoon o regenerar. Preferible entregar el archivo con
    # el problema documentado que no entregar nada.
    #   - validate_field_resolution: campo referenciado que ningún step aguas
    #     arriba produce ("Could not find field X in stream").
    #   - validate_row_sources: rama sin fuente de filas real (Constant/Add
    #     constants colgado de un WriteToLog sin entrada) o JoinRows
    #     cruzando contra una rama de 0 filas garantizadas (vacía TODO el
    #     resultado del cartesiano).
    #   - validate_dimension_lookup_races: DimensionLookup/CombinationLookup
    #     y un DBLookup separado apuntando a la MISMA tabla en una misma
    #     transformación — PDI corre los steps en paralelo, así que el
    #     DBLookup puede leer antes de que el DimensionLookup commitee.
    field_errors = validate_field_resolution(ktr_data, STEP_TYPE_ALIASES)
    row_source_errors = validate_row_sources(ktr_data, STEP_TYPE_ALIASES)
    dimension_race_errors = validate_dimension_lookup_races(ktr_data, STEP_TYPE_ALIASES)
    integrity_errors = [*field_errors, *row_source_errors, *dimension_race_errors]
    for e in integrity_errors:
        logger.error("KTR field integrity: %s", e)
    warnings.extend(f"{FIELD_INTEGRITY_PREFIX}{e}" for e in integrity_errors)

    name        = ktr_data.get("name") or process_name or "Transformacion_ETL"
    description = ktr_data.get("description", "")
    connections = ktr_data.get("connections", [])
    steps       = _auto_layout(ktr_data.get("steps", []), ktr_data.get("hops", []))
    hops        = ktr_data.get("hops", [])

    # Diagnóstico: loggear config completo de steps con campos críticos vacíos
    for step in ktr_data.get("steps", []):
        canonical = STEP_TYPE_ALIASES.get(step.get("type", ""), step.get("type", ""))
        required = _CRITICAL_FIELDS.get(canonical, [])
        raw = step.get("config", {})
        if isinstance(raw, str):
            try:
                cfg = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                cfg = {}
        else:
            cfg = raw or {}
        missing = [f for f in required if not (cfg.get(f) or cfg.get(f + "_name") or cfg.get("target_" + f))]
        if missing:
            logger.warning(
                "BUILD_KTR step='%s' type='%s' campos_faltantes=%s config_completo=%s",
                step.get("name"), canonical, missing, cfg,
            )

    # Pre-pass: garantizar que cada step con conexión la tenga resuelta en su config
    connection_names = [c.get("name", "") for c in connections if c.get("name")]
    for step in steps:
        canonical = STEP_TYPE_ALIASES.get(step.get("type", ""), step.get("type", ""))
        if canonical in _STEPS_NEEDING_CONNECTION:
            raw = step.get("config", {})
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw) if raw.strip() else {}
                except json.JSONDecodeError:
                    parsed = {}
                step["config"] = parsed  # normalizar a dict para el pre-pass
                raw = parsed
            cfg = raw if isinstance(raw, dict) else {}
            step.setdefault("config", cfg)
            explicit = (cfg.get("connection") or cfg.get("connection_name") or "").strip()
            resolved = _resolve_connection(
                cfg, canonical, connection_names,
                pass_source_connection=pass_source_connection,
                pass_dest_connection=pass_dest_connection,
            )
            if explicit and explicit not in connection_names:
                warnings.append(
                    f"Step '{step.get('name')}' referencia conexión '{explicit}' no declarada en 'connections' — se usó '{resolved}' como fallback."
                )
            cfg["connection"] = resolved

    trans = Element("transformation")

    # Info
    info = SubElement(trans, "info")
    _sub(info, "name",                 name)
    _sub(info, "description",          description)
    _sub(info, "extended_description")
    _sub(info, "trans_version")
    _sub(info, "trans_status",         "0")
    # "Make the transformation database transactional" en Spoon: comparte UNA
    # conexión física por nombre de conexión entre todos los steps que la usan
    # (commit al final), en vez de abrir una conexión por step. Propiedad
    # general del .ktr — evita agotar el pool de la BD destino sin importar
    # cuántos steps de BD tenga la transformación.
    _sub(info, "unique_connections", "Y" if settings.shared_connections else "N")
    dir_el = SubElement(info, "directory")
    dir_el.text = "/"

    # Connections
    undeclared_params: list[tuple[str, str]] = []
    for conn in connections:
        undeclared_params.extend(
            _build_connection(trans, conn, real=(real_connections or {}).get(conn.get("name", ""))) or []
        )

    # Variables ${...} que alguna conexión dejó sin resolver: se declaran como
    # <parameters> de la transformación (default = el mismo placeholder, así
    # Spoon lo muestra explícitamente en vez de resolver en blanco) y se
    # documentan en una plantilla kettle.properties — ver docstring de
    # build_ktr (strict_connections) para el caso en que esto aborta el build.
    if undeclared_params:
        params_el = SubElement(info, "parameters")
        seen_params: set[str] = set()
        for var_name, default in undeclared_params:
            if var_name in seen_params:
                continue
            seen_params.add(var_name)
            p = SubElement(params_el, "parameter")
            _sub(p, "name", var_name)
            _sub(p, "default_value", default)
            _sub(p, "description", "Completar antes de ejecutar en Spoon — ver plantilla kettle.properties.")
        if not strict_connections:
            warnings.append(
                "Conexión(es) sin credenciales reales — quedaron como variables Kettle sin valor "
                "(declaradas en <parameters> con el placeholder como default). Completar antes de "
                "ejecutar en Spoon. Plantilla kettle.properties:\n"
                + build_kettle_properties_template(undeclared_params)
            )

    # Hops
    _build_order(trans, hops)

    # Steps
    for step in steps:
        step_el   = SubElement(trans, "step")
        step_type = step.get("type", "Dummy")

        _sub(step_el, "name",                step.get("name", "Step"))
        _sub(step_el, "type",                step_type)
        _sub(step_el, "description")
        _sub(step_el, "distribute",          "Y")
        _sub(step_el, "custom_distribution")
        _sub(step_el, "copies",              "1")

        part = SubElement(step_el, "partitioning")
        _sub(part, "method",      "none")
        _sub(part, "schema_name")

        # config puede llegar como dict (schema object) o string JSON (schema string)
        raw_cfg = step.get("config", {})
        if isinstance(raw_cfg, str):
            try:
                cfg = json.loads(raw_cfg) if raw_cfg.strip() else {}
            except json.JSONDecodeError:
                logger.warning("KTR: config JSON inválido en step '%s': %r", step.get("name"), raw_cfg[:200])
                cfg = {}
        else:
            cfg = raw_cfg or {}

        # Normalizar tipo: el modelo puede devolver nombres con espacios ("Table Input")
        # o internos ("TableInput"). El alias map traduce ambos al canónico.
        canonical_type = STEP_TYPE_ALIASES.get(step_type, step_type)

        # Un type sin emisor registrado (ni siquiera detrás de un alias) no es
        # un plugin PDI real o no está soportado por este builder — Spoon
        # rompería con "plugin missing"/step vacío. Se aborta el build con un
        # mensaje claro en vez de degradar en silencio a Dummy: un .ktr que
        # "abre" pero le falta un step entero es peor que uno que no se genera.
        builder = STEP_BUILDERS.get(canonical_type)
        if builder is None:
            raise KtrBuilderError(
                f"Tipo de step no soportado: '{step_type}' en paso '{step.get('name')}'"
            )

        if canonical_type != step_type:
            logger.info("KTR: step type '%s' normalizado a '%s'", step_type, canonical_type)
            # Reescribir el <type> en el XML para que Spoon lo reconozca
            type_el = step_el.find("type")
            if type_el is not None:
                type_el.text = canonical_type

        for key in unmapped_config_keys(canonical_type, cfg):
            msg = f"clave de config no mapeada '{key}' en '{step.get('name')}'"
            logger.warning("KTR fidelidad: %s", msg)
            warnings.append(msg)

        builder(step_el, cfg)

        gui = SubElement(step_el, "GUI")
        _sub(gui, "xloc", str(step.get("x", 100)))
        _sub(gui, "yloc", str(step.get("y", 100)))
        _sub(gui, "draw", "Y")

    SubElement(trans, "step_error_handling")
    SubElement(trans, "slave-step-copy-partition-distribution")
    _sub(trans, "slave_transformation", "N")

    # Serialize to pretty XML
    raw    = tostring(trans, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    # Replace minidom's default declaration with UTF-8
    lines  = pretty.split("\n")
    if lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    ktr_xml = "\n".join(lines)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{_sanitize(name)}_{timestamp}.ktr"

    # Última barrera: si algo se escapó de las correcciones anteriores (conexión
    # GENERIC sin driver, step con configuración obligatoria vacía, hop
    # huérfano), rechazar acá con un mensaje claro en vez de entregar un .ktr
    # que Spoon abre roto sin explicación.
    validate_ktr_xml(ktr_xml, strict_connections=strict_connections)

    return ktr_xml, filename, warnings
