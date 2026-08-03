"""
KTR serializer: convierte el ktr JSON dict devuelto por el LLM en XML .ktr válido
para Pentaho PDI. Orquestador delgado — la lógica de cada step vive en steps/*.py
(vía registry.py), la de conexiones en connection.py, el auto-layout en layout.py
y la validación de estructura pre-XML en validate.py.

No AI calls — pure Python data transformation.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

from app.core.config import settings
from app.services.ktr_builder.xml_helpers import _sub
from app.services.ktr_builder.connection import (
    _build_connection,
    _resolve_connection,
    _STEPS_NEEDING_CONNECTION,
    build_kettle_properties_template,
)
from app.services.ktr_builder.contracts import ConfigParseError, missing_required_keys, normalize_config, parse_cfg
from app.services.ktr_builder.error_catalog_checks import (
    ERROR_CATALOG_PREFIX,
    parse_ktr,
    v4_select_values_sin_entradas,
    v5_dimension_lookup_columnas_tecnicas,
    v6_insert_update_mapeos,
    v7_fact_table_output_sin_clave,
    v8_truncate_sin_transaccional,
    v11_monetario_sin_bignumber,
    v13_lookup_key_incompleta,
)
from app.services.ktr_builder.fields_validate import (
    FIELD_INTEGRITY_PREFIX,
    repair_select_values_narrowing,
    validate_dimension_lookup_races,
    validate_field_resolution,
    validate_row_sources,
)
from app.services.ktr_builder.layout import _auto_layout
from app.services.ktr_builder.step_emitters import STEP_BUILDERS, unmapped_config_keys
from app.services.ktr_builder.step_types import _CRITICAL_FIELDS, STEP_TYPE_ALIASES
from app.services.ktr_builder.validate import _validate_ktr
from app.services.ktr_builder.validators import (
    PRE_EMIT_ERROR_PREFIX,
    ValidationContext,
    run_passes,
    split_findings_by_severity,
)
from app.services.ktr_default_validator import (
    check_missing_required_fields,
    scrub_function_default_constants,
)
from app.services.ktr_xml_validator import validate_ktr_xml

logger = logging.getLogger(__name__)

# Canónico interno → nombre de plugin real que espera Kettle en el XML.
# Necesario cuando el ID de plugin difiere del nombre "humano" usado como canónico.
_XML_TYPE_OVERRIDES: dict[str, str] = {
    "GetSystemInfo": "SystemInfo",  # UI: "Get System Info", plugin ID real: SystemInfo
    # E-11 (investigacion-tags-validos-por-step.md § A.4) — kettle-steps.xml solo
    # registra id="SplitFieldToRows3"; "SplitFieldToRows" (sin el 3) no es un
    # plugin id real y Spoon marca el step "missing". El alias "Split fields" de
    # step_types.py resuelve al canónico sin el 3 -- este override es lo que
    # evita que ese <type> llegue mal formado al XML.
    "SplitFieldToRows": "SplitFieldToRows3",
}


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
    known_tables: frozenset[str] | None = None,
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

    strict_connections: si True, revisa si alguna conexión GENERIC sigue con
    host/database placeholder tras aplicar real_connections. Ya NO aborta el
    build (D15, docs/refactor/02-decisiones.md) — la conexión sin resolver
    se entrega igual, como warning en el tercer elemento de la tupla, para
    completar a mano en Spoon. Usar SOLO cuando el caller ya intentó resolver
    conexiones reales (ver _try_build en etl_generator.py) — en los demás
    flujos (preview sin conexiones aún elegidas) el placeholder es esperado
    y ni se revisa.

    known_tables: nombres de tabla física reales del ETL (staging + DWH,
    lowercase, sin schema) — insumo de validators.recover_table_key (H29).
    Red de seguridad: etl_generator.py ya corre ese pass ANTES de acá (tiene
    que correr antes de enforce_dimension_step_policy/split_ktr_by_cut, que
    ejecutan antes de build_ktr — ver validators/README.md), así que acá es
    best-effort para callers que invocan build_ktr() directo (tests,
    build_etl_from_raw). None sin required_columns_by_table -> set vacío
    (el pass no encuentra nada que recuperar, solo reporta). None CON
    required_columns_by_table -> usa sus claves como aproximación (cobertura
    parcial: solo tablas con alguna columna NOT NULL sin default).

    Returns (ktr_xml_string, filename, warnings). Returns ("", "", []) if ktr_data is empty.
    """
    if not ktr_data:
        return "", "", []

    # Pass único de normalización: alias de clave -> canónica (StepContract,
    # ver contracts.py) ANTES de cualquier validación o emisión, así el
    # emisor XML y el validador de grafo de campos ven siempre las mismas
    # claves (mata el drift tipo inputField/input_field en origen) y el
    # config queda como dict (no string JSON) para el resto de esta función.
    # H6/D15: si el caller no pasó por normalize_step_configs() (ver
    # etl_generator.py, punto de entrada del pipeline), un config todavía
    # string y no-JSON llega hasta acá — capturarlo acá también en vez de
    # dejar que build_ktr() aborte sin generar nada por una sola config rota.
    #
    # D60 (docs/refactor/02-decisiones.md, Sitio 1): una clave requerida
    # ausente no tiene "valor real" contra qué contrastar (no hay inventario
    # que verificar para una clave, a diferencia de un stream_field o una
    # columna de DWH) — nunca se aborta TODO el build por esto. El step sale
    # con esa clave vacía/ausente tal cual (el builder de cada step ya tolera
    # claves faltantes con su propio default) + Finding(error) nombrando el
    # step y la clave, para que Spoon no falle en runtime sin que nadie lo
    # haya dicho antes.
    cfg_parse_warnings: list[str] = []
    for step in ktr_data.get("steps", []):
        canonical = STEP_TYPE_ALIASES.get(step.get("type", ""), step.get("type", ""))
        try:
            cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        except ConfigParseError as e:
            cfg = {}
            cfg_parse_warnings.append(
                f"Step '{step.get('name')}' ({canonical}): config no es JSON válido, tratado "
                f"como vacío — {e}. Revisar este step antes de ejecutar en Spoon."
            )
        step["config"] = cfg
        for key, reason in missing_required_keys(canonical, cfg):
            cfg_parse_warnings.append(
                f"{PRE_EMIT_ERROR_PREFIX}Config incompleto en '{step.get('name')}' ({canonical}): "
                f"{reason} — clave '{key}' ausente/vacía, emitida tal cual llegó."
            )

    # Red de seguridad (H29): ya corrió antes en etl_generator.py para los
    # steps que enforce_dimension_step_policy/build_rw_matrix necesitan ver
    # a tiempo — acá es best-effort para callers que no pasaron por ese
    # pipeline. Idempotente: si ya se resolvió, no encuentra nada que hacer.
    table_ctx = ValidationContext(
        ktr_data=ktr_data,
        step_type_aliases=STEP_TYPE_ALIASES,
        known_tables=known_tables if known_tables is not None
        else frozenset(k.lower() for k in (required_columns_by_table or {})),
    )
    table_findings = run_passes(table_ctx)
    cfg_parse_warnings.extend(split_findings_by_severity(table_findings))

    warnings = cfg_parse_warnings + _validate_ktr(ktr_data)
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

    # D60 (docs/refactor/02-decisiones.md, Sitio 2): un campo crítico vacío o
    # en placeholder (ver fix_gemini_config_generico.md) ya no aborta TODO el
    # build — mismo tratamiento que Sitio 1: se emite el valor literal (el
    # placeholder incluido — es lo que llegó, no se inventa nada mejor) +
    # Finding(error) explícito de que ese step no va a producir filas reales.
    for step in ktr_data.get("steps", []):
        canonical = STEP_TYPE_ALIASES.get(step.get("type", ""), step.get("type", ""))
        required = _CRITICAL_FIELDS.get(canonical, [])
        # config ya es dict acá: el pass de normalización de más arriba
        # (línea ~118) ya reemplazó step["config"] en ktr_data — mismos
        # objetos, mismo dict de steps, así que nunca llega un string.
        cfg = step.get("config") or {}
        missing = [f for f in required if not (cfg.get(f) or cfg.get(f + "_name") or cfg.get("target_" + f))]
        # TableInput.sql tiene un fallback literal "SELECT 1" en el builder
        # (ver steps/input.py _step_TableInput) — presencia de la clave no
        # alcanza, un placeholder ahí es equivalente a ausente.
        if canonical == "TableInput" and str(cfg.get("sql", "")).strip().upper() == "SELECT 1":
            missing.append("sql (placeholder 'SELECT 1', no es una query real)")
        if missing:
            logger.warning(
                "BUILD_KTR step='%s' type='%s' campos_faltantes=%s config_completo=%s",
                step.get("name"), canonical, missing, cfg,
            )
            warnings.append(
                f"{PRE_EMIT_ERROR_PREFIX}Config crítico incompleto en '{step.get('name')}' "
                f"({canonical}): faltan {missing} — este step no va a producir filas reales, "
                "emitido tal cual llegó."
            )

    # Pre-pass: garantizar que cada step con conexión la tenga resuelta en su config
    connection_names = [c.get("name", "") for c in connections if c.get("name")]
    for step in steps:
        canonical = STEP_TYPE_ALIASES.get(step.get("type", ""), step.get("type", ""))
        if canonical in _STEPS_NEEDING_CONNECTION:
            # config ya es dict (ver pass de normalización más arriba).
            cfg = step.get("config") or {}
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

    # Variables ${...} de las conexiones: SIEMPRE incluye al menos el/los
    # password (ver decisión de diseño de no-custodia de credenciales — el
    # password nunca se embebe, ni en conexiones resueltas), y además
    # host/port/database/username de toda conexión que no se pudo resolver.
    # Se declaran como <parameters> de la transformación (default = el mismo
    # placeholder, o vacío para password) y se documentan en una plantilla
    # kettle.properties.
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
        # Estos dos avisos van siempre (no solo en preview): el password es
        # variable de Kettle en todo .ktr generado, no un caso de error.
        warnings.append(
            "Antes de ejecutar en Spoon/Kitchen/Pan: completar el/los password de "
            "conexión en kettle.properties (plantilla abajo) o directamente en el "
            "conector de Spoon. El .ktr nunca incluye ningún password.\n"
            + build_kettle_properties_template(undeclared_params)
        )
        warnings.append(
            "Este .ktr contiene metadata de conexión (host, puerto, base de datos, "
            "usuario) de uso interno del equipo — no lo subas a repositorios públicos "
            "ni lo compartas fuera del equipo."
        )

    # Hops
    _build_order(trans, hops)

    # Steps
    for step in steps:
        step_el   = SubElement(trans, "step")
        step_type = step.get("type", "Dummy")

        # Normalizar tipo: el modelo puede devolver nombres con espacios ("Table Input")
        # o internos ("TableInput"). El alias map traduce ambos al canónico.
        canonical_type = STEP_TYPE_ALIASES.get(step_type, step_type)
        xml_type = _XML_TYPE_OVERRIDES.get(canonical_type, canonical_type)

        _sub(step_el, "name",                step.get("name", "Step"))
        _sub(step_el, "type",                xml_type)
        _sub(step_el, "description")
        outgoing_hops = sum(1 for h in hops if h.get("from") == step.get("name"))
        distribute_value = "N" if outgoing_hops > 1 else "Y"
        _sub(step_el, "distribute",          distribute_value)
        _sub(step_el, "custom_distribution")
        _sub(step_el, "copies",              "1")

        part = SubElement(step_el, "partitioning")
        _sub(part, "method",      "none")
        _sub(part, "schema_name")

        # config puede llegar como dict (ya normalizado por el Loop A arriba)
        # o como string JSON (ruta legacy). El else es CRÍTICO — sin él, cfg
        # no se reasigna cuando raw_cfg ya es dict y queda "pegado" al valor
        # de la iteración anterior (bug de scoping — ver fix_definitivo_scoping_config.md).
        raw_cfg = step.get("config", {})
        if isinstance(raw_cfg, str):
            try:
                cfg = parse_cfg(raw_cfg)
            except ConfigParseError as e:
                logger.warning("KTR: config JSON inválido en step '%s': %r", step.get("name"), raw_cfg[:200])
                warnings.append(
                    f"Step '{step.get('name')}' ({canonical_type}): config no es JSON válido, "
                    f"tratado como vacío — {e}. Revisar este step antes de ejecutar en Spoon."
                )
                cfg = {}
        else:
            cfg = raw_cfg if isinstance(raw_cfg, dict) else {}

        # D60 (docs/refactor/02-decisiones.md, Sitio 3): un type sin emisor
        # registrado (ni siquiera detrás de un alias) no es un plugin PDI real
        # o no está soportado por este builder. Único de los 4 sitios de
        # naturaleza distinta — no hay "valor tal cual llegó" que preservar,
        # porque no existe código que lo codifique. Nunca se aborta todo el
        # build: se sustituye por un step `Dummy` real de Kettle (no-op
        # documentado — DummyTransMeta no sobreescribe getXML(), hereda el
        # default de BaseStepMeta que emite XML vacío, igual que
        # steps/control.py::_step_Dummy), conservando nombre y hops, +
        # Finding(error) con el tipo original no soportado.
        builder = STEP_BUILDERS.get(canonical_type)
        if builder is None:
            warnings.append(
                f"{PRE_EMIT_ERROR_PREFIX}Tipo de step no soportado: '{step_type}' en paso "
                f"'{step.get('name')}' — no hay builder registrado (ni directo ni vía alias). "
                "Emitido como 'Dummy' (no-op) en su lugar, conservando nombre y hops, para no "
                "abortar el resto del build. Reemplazar a mano en Spoon por el step real."
            )
            canonical_type = "Dummy"
            xml_type = "Dummy"
            builder = STEP_BUILDERS["Dummy"]

        if canonical_type != step_type or xml_type != step_type:
            logger.info("KTR: step type '%s' normalizado a '%s' (XML: '%s')", step_type, canonical_type, xml_type)
            type_el = step_el.find("type")
            if type_el is not None:
                type_el.text = xml_type

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
    # Aviso siempre presente en el .ktr generado (no solo en la respuesta de
    # la API) — el archivo puede circular por fuera de esta app (adjunto,
    # subido a un repo por error, etc.) sin el contexto de esos warnings.
    _SECURITY_NOTE = (
        "<!--\n"
        "  Este archivo contiene metadata de conexion (host, puerto, base de\n"
        "  datos, usuario) de uso interno del equipo. No lo subas a repositorios\n"
        "  publicos ni lo compartas fuera del equipo.\n"
        "  Antes de ejecutar en Spoon/Kitchen/Pan: completar el/los password de\n"
        "  conexion en kettle.properties o en el conector de Spoon. Este archivo\n"
        "  nunca incluye ningun password.\n"
        "-->"
    )
    lines.insert(1, _SECURITY_NOTE)
    ktr_xml = "\n".join(lines)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{_sanitize(name)}_{timestamp}.ktr"

    # Última barrera: si algo se escapó de las correcciones anteriores (conexión
    # GENERIC sin driver, step con configuración obligatoria vacía, hop
    # huérfano), rechazar acá con un mensaje claro en vez de entregar un .ktr
    # que Spoon abre roto sin explicación. Una conexión sin resolver (bajo
    # strict_connections) ya NO está en esa lista de fatales (D15) — vuelve acá
    # como warning y se anota junto con el resto en vez de abortar la emisión.
    warnings.extend(validate_ktr_xml(ktr_xml, strict_connections=strict_connections))

    # Fase 0 (docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md,
    # D50 en 02-decisiones.md): catálogo E1-E14 sobre el XML YA serializado --
    # "anota, no aborta", nunca level de KtrBuilderError. ddl_columns es
    # best-effort: reusa required_columns_by_table (columnas NOT NULL sin
    # default, la única fuente de columnas reales que build_ktr ya recibe) --
    # no es el DDL completo, así que V5/V6 solo pueden CONFIRMAR una columna
    # ahí presente, nunca objetar una columna real ausente de esa lista
    # parcial. v8 entra cableado (a diferencia de lo que anticipaba el plan
    # antes de cerrar Fase 1): R-K5 confirmó que <unique_connections> es el
    # flag real, no un proxy -- ver docstring de v8_truncate_sin_transaccional.
    ddl_columns = {t: set(cols) for t, cols in (required_columns_by_table or {}).items()}
    catalog_root = parse_ktr(ktr_xml)
    catalog_findings = [
        *v4_select_values_sin_entradas(catalog_root),
        *v5_dimension_lookup_columnas_tecnicas(catalog_root, ddl_columns),
        *v6_insert_update_mapeos(catalog_root, ddl_columns),
        *v7_fact_table_output_sin_clave(catalog_root),
        *v8_truncate_sin_transaccional(catalog_root),
        *v11_monetario_sin_bignumber(catalog_root),
        *v13_lookup_key_incompleta(catalog_root),
    ]
    warnings.extend(
        f"{ERROR_CATALOG_PREFIX}[{f.rule}/{f.error}] {f.step}: {f.message}"
        for f in catalog_findings
    )

    return ktr_xml, filename, warnings
