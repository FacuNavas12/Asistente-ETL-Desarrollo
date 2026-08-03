"""Builders de calidad/logging/control de flujo: WriteToLog, ExecSQL, SetVariable,
GetVariable, Abort, BlockingStep, Dummy, ScriptValueMod, GetSystemInfo, DataValidator."""
from __future__ import annotations

import logging
from xml.etree.ElementTree import Element, SubElement

from app.services.ktr_builder.common import _sub

logger = logging.getLogger(__name__)

# Únicos dos info_type verificados contra exports reales de Spoon 9.x. Un
# valor no reconocido por GetSystemInfoMeta rompe la carga del .ktr en Spoon
# (mismo tipo de falla que NumberRange/Abort documentados en transform.py), así
# que cualquier otro valor se fuerza a un fallback seguro en vez de pasarlo tal cual.
_SYSTEM_INFO_KNOWN_TYPES = frozenset({"system date (fixed)", "system date (variable)"})


def _step_Dummy(el: Element, cfg: dict) -> None:
    pass


def _step_WriteToLog(el: Element, cfg: dict) -> None:
    _sub(el, "loglevel",      cfg.get("level", "Basic"))
    _sub(el, "displayHeader", "Y")
    _sub(el, "logmessage",    cfg.get("message", ""))
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name", f if isinstance(f, str) else f.get("name", ""))


def _step_GetSystemInfo(el: Element, cfg: dict) -> None:
    """Get System Info — usar para capturar un timestamp de carga REAL cuando
    hace falta dentro del stream (nunca un Constant con texto de función SQL).
    'system date (fixed)': un único valor para toda la corrida (recomendado
    para 'fecha de carga'). 'system date (variable)': uno por fila."""
    fields = cfg.get("fields") or []
    if not fields:
        # GetSystemInfoMeta sin <fields> no produce ninguna columna: el step
        # queda "vacío" y Spoon lo marca inválido al validar la transformación.
        # Sin un field declarado no hay info_type que inferir del LLM, así que
        # se cae al propósito por defecto del step (fecha de carga).
        logger.warning("GetSystemInfo: config sin 'fields', se agrega field por defecto 'fecha_carga'")
        fields = [{"name": "fecha_carga", "info_type": "system date (fixed)"}]

    fe = SubElement(el, "fields")
    for f in fields:
        # El LLM puede declarar el info_type bajo la clave "type" (consistente
        # con el resto de los steps) o "info_type" — aceptar ambas evita que
        # se pierda silenciosamente y caiga al default.
        raw_type = f.get("info_type") or f.get("type") or "system date (fixed)"
        info_type = str(raw_type).strip().lower()
        if info_type not in _SYSTEM_INFO_KNOWN_TYPES:
            logger.warning(
                "GetSystemInfo: info_type '%s' no reconocido, forzado a 'system date (fixed)'",
                info_type,
            )
            info_type = "system date (fixed)"
        field = SubElement(fe, "field")
        _sub(field, "name", f.get("name", "fecha_carga"))
        _sub(field, "type", info_type)


def _step_DataValidator(el: Element, cfg: dict) -> None:
    _sub(el, "validate_all", "Y" if cfg.get("validate_all", True) else "N")
    _sub(el, "concat_errors", "Y")
    for v in cfg.get("validations", []):
        val = SubElement(el, "validator_field")
        # E-10 (investigacion-tags-validos-por-step.md § A.2) — ValidatorMeta/
        # Validation(Node) lee 'name' como el CAMPO REAL del stream a validar,
        # no la etiqueta de la regla; 'fieldname' no tiene lector. El emisor
        # anterior invertía esto (name=etiqueta, fieldname=campo real), rompiendo
        # la validación siempre que ambos difieren -- el caso esperado por diseño.
        _sub(val, "name",                  v.get("field", v.get("name", "")))
        _sub(val, "validation_name",       v.get("name", v.get("field", "")))
        _sub(val, "max_length",            str(v.get("max_length", -1)))
        _sub(val, "min_length",            str(v.get("min_length", -1)))
        _sub(val, "null_allowed",          "Y" if v.get("null_allowed", True) else "N")
        _sub(val, "only_null_allowed",     "N")
        _sub(val, "only_numeric_allowed",  "Y" if v.get("only_numeric", False) else "N")
        _sub(val, "data_type",             v.get("type", "String"))
        _sub(val, "data_type_verified",    "N")
        _sub(val, "conversion_mask",       v.get("mask", ""))
        _sub(val, "decimal_symbol",        ".")
        _sub(val, "grouping_symbol",       ",")
        _sub(val, "max_value",             str(v.get("max_value", "")))
        _sub(val, "min_value",             str(v.get("min_value", "")))
        _sub(val, "start_string",          "")
        _sub(val, "end_string",            "")
        _sub(val, "start_string_not_allowed", "")
        _sub(val, "end_string_not_allowed",   "")
        _sub(val, "regular_expression",        v.get("regex", ""))
        _sub(val, "regular_expression_not_allowed", "")
        _sub(val, "error_code",            v.get("error_code", ""))
        _sub(val, "error_description",     v.get("error_description", ""))
        _sub(val, "is_sourcing_values_from_another_step", "N")


def _step_ExecSQL(el: Element, cfg: dict) -> None:
    sql = cfg.get("sql", "")
    if not sql:
        logger.warning("ExecSQL: 'sql' vacío — el step no ejecutará nada útil")
    _sub(el, "connection",        cfg.get("connection", ""))
    _sub(el, "execute_each_row",  "Y" if cfg.get("execute_each_row", False) else "N")
    _sub(el, "single_statement",  "Y" if cfg.get("single_statement", True) else "N")
    _sub(el, "replace_variables", "Y" if cfg.get("replace_variables", True) else "N")
    _sub(el, "quoteString",       "N")
    _sub(el, "set_params",        "N")
    _sub(el, "sql",               sql or "SELECT 1")
    _sub(el, "insert_field")
    _sub(el, "update_field")
    _sub(el, "delete_field")
    _sub(el, "read_field")
    SubElement(el, "arguments")


def _step_ScriptValueMod(el: Element, cfg: dict) -> None:
    """Modified Java Script Value. ScriptValuesMetaMod soporta dos formatos XML: uno
    legacy con un único tag <script> (el que se usa acá) y otro con <jsScripts>/
    <jsScript><jsScript_type> donde jsScript_type se parsea con Integer.parseInt SIN
    Const.toInt de por medio — un tag vacío ahí rompe la carga del step con
    NumberFormatException. Usar siempre el <script> legacy evita ese camino por completo."""
    script = cfg.get("script") or "// sin transformacion definida"
    _sub(el, "script",            script)
    _sub(el, "compatible",        "Y")
    _sub(el, "optimizationLevel", str(cfg.get("optimization_level", 9)))
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "rename",    f.get("rename") or f.get("name", ""))
        _sub(field, "type",      f.get("type", "String"))
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))
        _sub(field, "replace",   "Y" if f.get("replace", False) else "N")


def _step_SetVariable(el: Element, cfg: dict) -> None:
    _sub(el, "use_formatting", "Y" if cfg.get("use_formatting", False) else "N")
    fe = SubElement(el, "fields")
    for f in cfg.get("variables", cfg.get("fields", [])):
        field = SubElement(fe, "field")
        _sub(field, "field_name",    f.get("field_name") or f.get("name", ""))
        _sub(field, "variable_name", f.get("variable_name", ""))
        # Códigos válidos: JVM | PARENT_JOB | GP_JOB | ROOT_JOB (ver SetVariableMeta)
        _sub(field, "variable_type", f.get("scope") or f.get("variable_type", "JVM"))
        _sub(field, "default_value", str(f.get("default_value", "")))


def _step_GetVariable(el: Element, cfg: dict) -> None:
    fe = SubElement(el, "fields")
    for f in cfg.get("variables", cfg.get("fields", [])):
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "variable",  f.get("variable") or f.get("variable_name", ""))
        _sub(field, "type",      f.get("type", "String"))
        _sub(field, "format",    f.get("format", ""))
        _sub(field, "currency")
        _sub(field, "decimal")
        _sub(field, "group")
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))
        _sub(field, "trim_type", f.get("trim_type", "none"))


def _step_Abort(el: Element, cfg: dict) -> None:
    """AbortMeta.readData hace AbortOption.valueOf(str) — enum Java, case-sensitive —
    cuando 'abort_option' viene no vacío. Un valor fuera de {ABORT, ABORT_WITH_ERROR}
    o con distinto casing tira IllegalArgumentException al abrir el .ktr en Spoon."""
    option = "ABORT_WITH_ERROR" if cfg.get("abort_with_error", True) else "ABORT"
    _sub(el, "row_threshold",   str(cfg.get("row_threshold", 0)))
    _sub(el, "message",         cfg.get("message", "Proceso abortado"))
    _sub(el, "always_log_rows", "N")
    _sub(el, "abort_option",    option)


def _step_BlockingStep(el: Element, cfg: dict) -> None:
    _sub(el, "pass_all_rows", "Y" if cfg.get("pass_all_rows", True) else "N")
    _sub(el, "directory",     cfg.get("directory", "%%java.io.tmpdir%%"))
    _sub(el, "prefix",        cfg.get("prefix", "block"))
    _sub(el, "cache_size",    str(cfg.get("cache_size", 2000)))
    _sub(el, "compress",      "N")
