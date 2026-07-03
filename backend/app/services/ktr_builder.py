"""
KTR serializer: converts the ktr JSON structure returned by Gemini into valid .ktr XML.
No AI calls — pure Python data transformation.
"""
import re
import json
import logging
import uuid
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from app.core.config import settings
from app.core.kettle_crypto import encode as kettle_encode
from app.services.ktr_default_validator import (
    check_missing_required_fields,
    scrub_function_default_constants,
)

logger = logging.getLogger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sub(parent: Element, tag: str, text: str = "") -> Element:
    el = SubElement(parent, tag)
    if text:
        el.text = str(text)
    return el


# Step types que requieren un tag <connection> en el XML
_STEPS_NEEDING_CONNECTION = {
    "TableInput", "TableOutput", "InsertUpdate", "Update", "Delete",
    "DimensionLookup", "CombinationLookup", "DBLookup", "ExecSQL",
    "DynamicSQLRow", "CallDBProc",
}

_STAGING_PREFIXES = ("stg_", "staging_", "tmp_", "temp_", "ods_", "raw_", "wrk_", "work_")
_DWH_PREFIXES     = ("dim_", "fact_", "fct_", "hecho_", "ft_", "dwh_", "bridge_", "br_", "rel_")


def _resolve_connection(cfg: dict, canonical_type: str, connection_names: list) -> str:
    """
    Devuelve el nombre de conexión a usar en el step.
    Prioridad: campo 'connection' del config → campo 'connection_name' → inferencia por tabla.
    """
    conn = (cfg.get("connection") or cfg.get("connection_name") or "").strip()
    if conn:
        return conn

    table = (cfg.get("table") or cfg.get("schema_table") or "").lower().strip()

    if any(table.startswith(p) for p in _DWH_PREFIXES):
        inferred = "conn_dwh"
    elif any(table.startswith(p) for p in _STAGING_PREFIXES):
        inferred = "conn_staging"
    elif canonical_type == "TableInput":
        inferred = "conn_origen"
    else:
        inferred = connection_names[0] if connection_names else "conn_origen"

    # Preferir el nombre inferido si existe en las conexiones declaradas
    if inferred in connection_names:
        return inferred
    return connection_names[0] if connection_names else inferred


# ─── Motor -> tipo de conexión Kettle ──────────────────────────────────────────
# MSSQLNATIVE = driver JDBC oficial de Microsoft (confirmado contra export real
# de Spoon 9.x, ver tests/fixtures/connections_sample.ktr). Si el Spoon del
# equipo usa jTDS en vez del driver Microsoft, cambiar a "MSSQL" acá.
_DB_TYPE_TO_KETTLE: dict[str, dict] = {
    "postgresql": {"type": "POSTGRESQL",  "access": "Native"},
    "sqlserver":  {"type": "MSSQLNATIVE", "access": "Native"},
}


def resolve_real_connections(connections_map: dict, db) -> tuple[dict[str, dict], list[str]]:
    """
    Resuelve un mapa {nombre_lógico: connection_id} a datos de conexión reales
    (host/port/database/username/password-ofuscado/type) consultando la tabla
    Connection y desofuscando el password SOLO en memoria, para inyectarlo en el
    XML final. Nunca devuelve el password en claro ni lo loguea.

    Devuelve (real_connections, warnings). Toda conexión que no se pueda resolver
    genera un warning en vez de fallar — el .ktr sigue el build con placeholder.
    """
    from app.core.crypto import decrypt_password
    from app.models.connection import Connection

    real: dict[str, dict] = {}
    warnings: list[str] = []

    for logical_name, conn_id in (connections_map or {}).items():
        if not conn_id:
            continue
        try:
            conn_uuid = uuid.UUID(str(conn_id))
        except (ValueError, TypeError, AttributeError):
            warnings.append(f"Conexión '{logical_name}': id inválido — se usará placeholder, configurar manualmente en Spoon.")
            continue

        conn = db.get(Connection, conn_uuid)
        if conn is None:
            warnings.append(f"Conexión '{logical_name}': no encontrada — se usará placeholder, configurar manualmente en Spoon.")
            continue

        db_type_key = conn.db_type.value if hasattr(conn.db_type, "value") else str(conn.db_type)
        kettle_meta = _DB_TYPE_TO_KETTLE.get(db_type_key)
        if kettle_meta is None:
            warnings.append(f"Conexión '{logical_name}': motor '{db_type_key}' sin mapeo Kettle — se usará placeholder.")
            continue

        password_plain = decrypt_password(conn.encrypted_password)
        real[logical_name] = {
            "host":     conn.host,
            "port":     conn.port,
            "database": conn.database,
            "username": conn.username,
            "password": kettle_encode(password_plain),
            "type":     kettle_meta["type"],
            "access":   kettle_meta["access"],
        }
        password_plain = None  # nunca queda referenciado más allá de este punto

    return real, warnings


# ─── Connection block ─────────────────────────────────────────────────────────

def _build_connection(trans: Element, conn: dict, real: dict | None = None) -> None:
    c = SubElement(trans, "connection")
    _sub(c, "name", conn.get("name", "conn_default"))
    if real:
        _sub(c, "server",   real["host"])
        _sub(c, "type",     real["type"])
        _sub(c, "access",   real.get("access", "Native"))
        _sub(c, "database", real["database"])
        _sub(c, "port",     str(real["port"]))
        _sub(c, "username", real["username"])
        _sub(c, "password", real["password"])
    else:
        _sub(c, "server",   conn.get("host", "PLACEHOLDER_HOST"))
        _sub(c, "type",     conn.get("type", "GENERIC"))
        _sub(c, "access",   "Native")
        _sub(c, "database", conn.get("database", "PLACEHOLDER_DATABASE"))
        _sub(c, "port",     str(conn.get("port", 0)))
        _sub(c, "username", conn.get("username", "PLACEHOLDER_USER"))
        # Sin conexión real resuelta: no hay password que ofuscar. Vacío es
        # honesto (Spoon lo muestra en blanco); "Encrypted " a secas simulaba
        # un password ofuscado inexistente.
        _sub(c, "password", "")
    _sub(c, "servername")
    _sub(c, "data_tablespace")
    _sub(c, "index_tablespace")
    SubElement(c, "attributes")


# ─── Order / hops block ───────────────────────────────────────────────────────

def _build_order(trans: Element, hops: list) -> None:
    order = SubElement(trans, "order")
    for hop in hops:
        h = SubElement(order, "hop")
        _sub(h, "from",    hop.get("from", ""))
        _sub(h, "to",      hop.get("to", ""))
        _sub(h, "enabled", "Y" if hop.get("enabled", True) else "N")


# ─── Step-type config builders ────────────────────────────────────────────────

def _step_TableInput(el: Element, cfg: dict) -> None:
    _sub(el, "connection",             cfg.get("connection", ""))
    _sub(el, "sql",                    cfg.get("sql", "SELECT 1"))
    _sub(el, "limit",                  "0")
    _sub(el, "lookup")
    _sub(el, "execute_each_row",       "N")
    _sub(el, "variables_active",       "N")
    _sub(el, "lazy_conversion_active", "N")


def _step_TableOutput(el: Element, cfg: dict) -> None:
    table = cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or ""
    _sub(el, "connection",     cfg.get("connection", ""))
    _sub(el, "schema",         cfg.get("schema", ""))
    _sub(el, "table",          table)
    _sub(el, "commit",         "1000")
    _sub(el, "truncate",       "Y" if cfg.get("truncate") else "N")
    _sub(el, "ignore_errors",  "N")
    _sub(el, "use_batch",      "Y")
    fields = cfg.get("fields", [])
    _sub(el, "specify_fields", "Y" if fields else "N")
    fe = SubElement(el, "fields")
    for f in fields:
        field = SubElement(fe, "field")
        _sub(field, "column_name", f.get("column_name", f.get("dest", "")))
        _sub(field, "stream_name", f.get("stream_name", f.get("source", "")))


def _step_InsertUpdate(el: Element, cfg: dict) -> None:
    table = cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or ""
    _sub(el, "connection", cfg.get("connection", ""))
    _sub(el, "schema",     cfg.get("schema", ""))
    _sub(el, "table",      table)
    _sub(el, "commit",     "100")
    lookup = SubElement(el, "lookup")
    for k in cfg.get("keys", []):
        ke = SubElement(lookup, "key")
        _sub(ke, "name",      k.get("stream_field", k.get("name", "")))
        _sub(ke, "field",     k.get("table_field",  k.get("field", "")))
        _sub(ke, "condition", "=")
        _sub(ke, "name2")
    for f in cfg.get("fields", []):
        ve = SubElement(lookup, "value")
        _sub(ve, "name",   f.get("stream_field", f.get("name", "")))
        _sub(ve, "rename", f.get("table_field",  f.get("rename", "")))
        _sub(ve, "update", "Y" if f.get("update", True) else "N")


def _step_Update(el: Element, cfg: dict) -> None:
    table = cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or ""
    _sub(el, "connection",             cfg.get("connection", ""))
    _sub(el, "schema",                 cfg.get("schema", ""))
    _sub(el, "table",                  table)
    _sub(el, "commit",                 "100")
    _sub(el, "use_batch",              "Y")
    _sub(el, "ignore_lookup_failure",  "N")
    lookup = SubElement(el, "lookup")
    for k in cfg.get("keys", []):
        ke = SubElement(lookup, "key")
        _sub(ke, "name",      k.get("stream_field", k.get("name", "")))
        _sub(ke, "field",     k.get("table_field",  k.get("field", "")))
        _sub(ke, "condition", "=")
        _sub(ke, "name2")
    for f in cfg.get("fields", []):
        ve = SubElement(lookup, "value")
        _sub(ve, "name",   f.get("stream_field", f.get("name", "")))
        _sub(ve, "rename", f.get("table_field",  f.get("rename", "")))


def _step_SelectValues(el: Element, cfg: dict) -> None:
    # LLM puede usar "select", "fields" o "columns" para la lista de campos a seleccionar
    select_fields = cfg.get("select") or cfg.get("fields") or cfg.get("columns") or []
    remove_fields = cfg.get("remove", [])
    cast_fields   = cfg.get("cast", [])

    if not select_fields and not cast_fields and not remove_fields:
        logger.warning("SelectValues: config sin campos en select/fields/cast/remove. cfg=%s", cfg)

    fe = SubElement(el, "fields")
    for f in select_fields:
        if isinstance(f, str):
            f = {"name": f, "rename": f}
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "rename",    f.get("rename") or f.get("name", ""))
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))
    # PDI requiere este tag al final de <fields>
    _sub(fe, "select_unspecified", "N")

    re_el = SubElement(el, "remove")
    for r in remove_fields:
        _sub(re_el, "field", r if isinstance(r, str) else r.get("name", ""))

    meta = SubElement(el, "meta")
    for f in cast_fields:
        # El LLM puede usar "name" o "field" como clave del nombre de columna
        col_name = f.get("name") or f.get("field", "")
        field = SubElement(meta, "field")
        _sub(field, "name",                col_name)
        _sub(field, "rename")
        _sub(field, "type",                f.get("type", "String"))
        _sub(field, "length",              "-1")
        _sub(field, "precision",           "-1")
        _sub(field, "conversion_mask")
        _sub(field, "date_format_lenient", "false")
        _sub(field, "encoding")
        _sub(field, "dec_symbol")
        _sub(field, "group_symbol")


def _step_FilterRows(el: Element, cfg: dict) -> None:
    compare = SubElement(el, "compare")
    cond = SubElement(compare, "condition")
    _sub(cond, "negated",    "N")
    _sub(cond, "operator",   "-")
    _sub(cond, "leftvalue",  cfg.get("field", ""))
    op_map = {
        "IS NOT NULL": "IS NOT NULL", "IS NULL": "IS NULL",
        "=": "=", "!=": "<>", "<>": "<>",
        ">": ">", "<": "<", ">=": ">=", "<=": "<=", "CONTAINS": "CONTAINS",
    }
    _sub(cond, "function", op_map.get(str(cfg.get("operator", "IS NOT NULL")).upper(), "IS NOT NULL"))
    _sub(cond, "rightvalue", cfg.get("right_field", ""))
    val = SubElement(cond, "value")
    _sub(val, "name",      "constant")
    _sub(val, "type",      cfg.get("value_type", "String"))
    _sub(val, "text",      str(cfg["value"]) if cfg.get("value") is not None else "")
    _sub(val, "length",    "-1")
    _sub(val, "precision", "-1")
    _sub(val, "isnull",    "Y" if cfg.get("value") is None else "N")
    _sub(val, "mask")
    SubElement(cond, "conditions")
    if cfg.get("true_target"):
        _sub(el, "send_true_to",  cfg["true_target"])
    if cfg.get("false_target"):
        _sub(el, "send_false_to", cfg["false_target"])


def _step_SortRows(el: Element, cfg: dict) -> None:
    _sub(el, "sort_size",              "1000000")
    _sub(el, "free_memory_treshold",   "25")
    _sub(el, "compress",               "N")
    _sub(el, "add_groupby_fields",     "N")
    _sub(el, "prefix",                 "sort")
    _sub(el, "sort_path")
    _sub(el, "unique_rows",            "N")
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", cfg.get("sort_fields", [])):
        field = SubElement(fe, "field")
        if isinstance(f, dict):
            name = f.get("name") or f.get("field") or f.get("column") or ""
            asc  = f.get("ascending", True)
        else:
            name = str(f)
            asc  = True
        _sub(field, "name",           name)
        _sub(field, "ascending",      "Y" if asc else "N")
        _sub(field, "case_sensitive", "N")


def _step_GroupBy(el: Element, cfg: dict) -> None:
    _sub(el, "all_rows",         "N")
    _sub(el, "sort_direction",   "None")
    _sub(el, "prefix",           "grp")
    _sub(el, "add_linenr",       "N")
    _sub(el, "linenr_fieldname")
    _sub(el, "include_all_rows", "N")
    _sub(el, "give_back_row",    "N")
    grp = SubElement(el, "group")
    for gf in cfg.get("group_fields", []):
        ge = SubElement(grp, "field")
        _sub(ge, "name", gf if isinstance(gf, str) else gf.get("name", ""))
    fe = SubElement(el, "fields")
    for agg in cfg.get("aggregates", []):
        field = SubElement(fe, "field")
        # LLM puede usar name/result_field/aggregate para el campo resultado
        _sub(field, "aggregate", (agg.get("name") or agg.get("result_field") or
                                  agg.get("aggregate") or agg.get("output_field") or ""))
        # LLM puede usar subject/subject_field/field para el campo fuente
        _sub(field, "subject",   (agg.get("subject") or agg.get("subject_field") or
                                  agg.get("field") or agg.get("input_field") or ""))
        _sub(field, "type",      agg.get("type", "SUM"))
        _sub(field, "valuefield")


def _step_MergeJoin(el: Element, cfg: dict) -> None:
    jt_map = {
        "INNER": "INNER JOIN", "LEFT": "LEFT OUTER JOIN",
        "RIGHT": "RIGHT OUTER JOIN", "FULL": "FULL OUTER JOIN",
        "INNER JOIN": "INNER JOIN", "LEFT OUTER JOIN": "LEFT OUTER JOIN",
        "RIGHT OUTER JOIN": "RIGHT OUTER JOIN", "FULL OUTER JOIN": "FULL OUTER JOIN",
    }
    _sub(el, "join_type", jt_map.get(str(cfg.get("join_type", "INNER JOIN")).upper(), "INNER JOIN"))
    _sub(el, "step1",     cfg.get("step1", ""))
    _sub(el, "step2",     cfg.get("step2", ""))
    k1 = SubElement(el, "keys_1")
    for k in cfg.get("keys1", []):
        _sub(k1, "key", k if isinstance(k, str) else k.get("name", ""))
    k2 = SubElement(el, "keys_2")
    for k in cfg.get("keys2", []):
        _sub(k2, "key", k if isinstance(k, str) else k.get("name", ""))


def _step_DimensionLookup(el: Element, cfg: dict) -> None:
    table        = cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or ""
    return_field = (cfg.get("return_field") or cfg.get("returnfield") or
                    cfg.get("sk_field") or cfg.get("surrogate_key") or "id_sk")
    if not table:
        logger.warning("DimensionLookup: 'table' vacío — PDI fallará con SELECT FROM null")
    if not return_field or return_field == "id_sk":
        logger.warning("DimensionLookup: 'returnfield' no configurado, usando fallback '%s'", return_field)
    _sub(el, "schema",                    cfg.get("schema", ""))
    _sub(el, "table",                     table)
    _sub(el, "connection",                cfg.get("connection", ""))
    _sub(el, "commit",                    "100")
    _sub(el, "update",                    "Y")
    _sub(el, "returnfield",               return_field)
    _sub(el, "preload_cache",             "N")
    _sub(el, "cache_size",                "5000")
    _sub(el, "use_start_date_alternative","N")
    _sub(el, "start_date_alternative")
    _sub(el, "use_alternative_start_date","N")
    _sub(el, "batch_size",                "0")
    fe = SubElement(el, "fields")
    for k in cfg.get("keys", []):
        ke = SubElement(fe, "key")
        # LLM puede usar stream/stream_field/name para el campo del stream
        _sub(ke, "name",   k.get("stream") or k.get("stream_field") or k.get("name", ""))
        _sub(ke, "lookup", k.get("lookup") or k.get("table_field") or k.get("name", ""))
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",   f.get("stream") or f.get("stream_field") or f.get("name", ""))
        _sub(field, "lookup", f.get("lookup") or f.get("table_field") or f.get("name", ""))
        _sub(field, "update", "Y" if f.get("update", True) else "N")
        _sub(field, "type",   f.get("type", "Insert"))
    date_el = SubElement(fe, "date")
    _sub(date_el, "name",       cfg.get("date_from", "fecha_desde"))
    _sub(date_el, "datename",   cfg.get("date_to",   "fecha_hasta"))
    _sub(date_el, "dateformat", "yyyy-MM-dd")
    # Bloque <return> obligatorio para PDI — identifica el surrogate key generado
    ret_el = SubElement(fe, "return")
    _sub(ret_el, "name",            return_field)
    _sub(ret_el, "rename",          return_field)
    _sub(ret_el, "creation_method", "autoinc")
    _sub(ret_el, "use_autoinc",     "Y")
    _sub(ret_el, "version",         "1")


def _step_DBLookup(el: Element, cfg: dict) -> None:
    table = cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or ""
    if not table:
        logger.warning("DBLookup: 'table' vacío — PDI fallará buscando campo en tabla null")
    _sub(el, "connection", cfg.get("connection", ""))
    _sub(el, "schema",     cfg.get("schema", ""))
    _sub(el, "table",      table)
    _sub(el, "orderby")
    _sub(el, "fail_on_multiple", "N")
    _sub(el, "eat_row_on_lookup_failure", "N")
    _sub(el, "cache", "N")
    _sub(el, "cache_load_all", "N")
    _sub(el, "cache_size", "9999")
    for k in cfg.get("keys", []):
        ke = SubElement(el, "key")
        _sub(ke, "name",      k.get("stream_field") or k.get("name", ""))
        _sub(ke, "field",     k.get("lookup_field") or k.get("table_field") or k.get("field", ""))
        _sub(ke, "condition", k.get("condition", "="))
    for r in cfg.get("return_fields", cfg.get("returns", [])):
        ret = SubElement(el, "value")
        _sub(ret, "name",    r.get("name", ""))
        _sub(ret, "rename",  r.get("rename") or r.get("name", ""))
        _sub(ret, "default", str(r.get("default", "")))
        _sub(ret, "type",    r.get("type", "String"))


def _step_CombinationLookup(el: Element, cfg: dict) -> None:
    _sub(el, "schema",       cfg.get("schema", ""))
    _sub(el, "table",        cfg.get("table", ""))
    _sub(el, "connection",   cfg.get("connection", ""))
    _sub(el, "useautoinc",   "N")
    _sub(el, "returnfield",  cfg.get("return_field", "id_sk"))
    _sub(el, "lastUpdateField")
    fe = SubElement(el, "fields")
    for k in cfg.get("keys", []):
        ke = SubElement(fe, "key")
        _sub(ke, "name",   k.get("stream", k.get("name", "")))
        _sub(ke, "lookup", k.get("lookup", k.get("name", "")))
    _sub(el, "cache_size",   "5000")
    _sub(el, "preload_cache","N")
    _sub(el, "commit_size",  "100")


def _step_WriteToLog(el: Element, cfg: dict) -> None:
    _sub(el, "loglevel",      cfg.get("level", "Basic"))
    _sub(el, "displayHeader", "Y")
    _sub(el, "logmessage",    cfg.get("message", ""))
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name", f if isinstance(f, str) else f.get("name", ""))


def _step_StringOperations(el: Element, cfg: dict) -> None:
    fe = SubElement(el, "fields")
    trim_map = {"both": "3", "left": "1", "right": "2", "none": "0"}
    case_map = {"upper": "1", "lower": "2", "none": "0", "title": "3"}
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "in_stream_name",          f.get("name", ""))
        _sub(field, "out_stream_name",         f.get("rename", ""))
        _sub(field, "trim_type",               trim_map.get(str(f.get("trim_type", "both")).lower(), "3"))
        _sub(field, "lower_upper",             case_map.get(str(f.get("case", "none")).lower(), "0"))
        _sub(field, "padding_type",            "0")
        _sub(field, "pad_char")
        _sub(field, "pad_len")
        _sub(field, "init_cap",                "N")
        _sub(field, "mask_XML",                "N")
        _sub(field, "digits_only",             "N")
        _sub(field, "remove_special_characters","N")
        _sub(field, "remove_CR",               "N")
        _sub(field, "remove_LF",               "N")
        _sub(field, "return_type",             "0")
        _sub(field, "replace_value")
        _sub(field, "replace_mask")


def _step_IfNull(el: Element, cfg: dict) -> None:
    fields = cfg.get("fields", [])
    _sub(el, "selectFields",     "Y" if fields else "N")
    _sub(el, "selectValuesType")
    fe = SubElement(el, "fields")
    for f in fields:
        field = SubElement(fe, "fields")
        _sub(field, "name",  f.get("name", ""))
        _sub(field, "type",  f.get("type", ""))
        _sub(field, "value", str(f.get("replace_value", "")))
        _sub(field, "mask",  f.get("mask", ""))


def _step_Unique(el: Element, cfg: dict) -> None:
    _sub(el, "error_description")
    _sub(el, "redirect_rows", "N")
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",           f if isinstance(f, str) else f.get("name", ""))
        _sub(field, "case_sensitive", "N")


def _step_Dummy(el: Element, cfg: dict) -> None:
    pass


# ─── Builders agregados (cobertura de los tipos listados en system_etl.txt) ──

def _step_CsvInput(el: Element, cfg: dict) -> None:
    _sub(el, "filename",         cfg.get("filename", "PLACEHOLDER.csv"))
    _sub(el, "filename_field")
    _sub(el, "rownum_field")
    _sub(el, "include_filename", "N")
    _sub(el, "separator",        cfg.get("separator", ","))
    _sub(el, "enclosure",        cfg.get("enclosure", '"'))
    _sub(el, "header",           "Y" if cfg.get("header", True) else "N")
    _sub(el, "buffer_size",      "50000")
    _sub(el, "lazy_conversion",  "Y")
    _sub(el, "add_filename_result", "N")
    _sub(el, "parallel",         "N")
    _sub(el, "newline_possible", "N")
    _sub(el, "format",           "mixed")
    _sub(el, "encoding")
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "type",      f.get("type", "String"))
        _sub(field, "format",    f.get("format", ""))
        _sub(field, "currency",  "€")
        _sub(field, "decimal",   ",")
        _sub(field, "group",     ".")
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))
        _sub(field, "trim_type", "none")


def _step_Calculator(el: Element, cfg: dict) -> None:
    """Cálculos numéricos / de fecha. config = {calculations: [{field_name, calc_type, field_a, field_b, value_type}]}"""
    for c in cfg.get("calculations", []):
        calc = SubElement(el, "calculation")
        _sub(calc, "field_name",      c.get("field_name", ""))
        _sub(calc, "calc_type",       c.get("calc_type", "NONE"))
        _sub(calc, "field_a",         c.get("field_a", ""))
        _sub(calc, "field_b",         c.get("field_b", ""))
        _sub(calc, "field_c",         c.get("field_c", ""))
        _sub(calc, "value_type",      c.get("value_type", "None"))
        _sub(calc, "value_length",    str(c.get("value_length", -1)))
        _sub(calc, "value_precision", str(c.get("value_precision", -1)))
        _sub(calc, "remove",          "N")


def _step_Constant(el: Element, cfg: dict) -> None:
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "type",      f.get("type", "String"))
        _sub(field, "format",    f.get("format", ""))
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))
        _sub(field, "nullif",    str(f.get("value", "")))
        _sub(field, "set_empty_string", "N")


# Únicos dos info_type verificados contra exports reales de Spoon 9.x. Un
# valor no reconocido por GetSystemInfoMeta rompe la carga del .ktr en Spoon
# (mismo tipo de falla que NumberRange/Abort documentados arriba), así que
# cualquier otro valor se fuerza a un fallback seguro en vez de pasarlo tal cual.
_SYSTEM_INFO_KNOWN_TYPES = frozenset({"system date (fixed)", "system date (variable)"})


def _step_GetSystemInfo(el: Element, cfg: dict) -> None:
    """Get System Info — usar para capturar un timestamp de carga REAL cuando
    hace falta dentro del stream (nunca un Constant con texto de función SQL).
    'system date (fixed)': un único valor para toda la corrida (recomendado
    para 'fecha de carga'). 'system date (variable)': uno por fila."""
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        info_type = str(f.get("info_type", "system date (fixed)")).strip().lower()
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
        _sub(val, "name",                  v.get("name", ""))
        _sub(val, "fieldname",             v.get("field", v.get("name", "")))
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


def _step_StreamLookup(el: Element, cfg: dict) -> None:
    _sub(el, "from",          cfg.get("step", cfg.get("from", "")))
    _sub(el, "input_sorted",  "N")
    _sub(el, "preserve_memory", "Y")
    _sub(el, "sorted_list",   "N")
    _sub(el, "integer_pair",  "N")
    lookup = SubElement(el, "lookup")
    for k in cfg.get("keys", []):
        ke = SubElement(lookup, "key")
        _sub(ke, "name",  k.get("stream", k.get("name", "")))
        _sub(ke, "field", k.get("lookup", k.get("field", "")))
    for v in cfg.get("values", cfg.get("fields", [])):
        ve = SubElement(lookup, "value")
        _sub(ve, "name",    v.get("name", ""))
        _sub(ve, "rename",  v.get("rename", v.get("name", "")))
        _sub(ve, "default", str(v.get("default", "")))
        _sub(ve, "type",    v.get("type", "String"))


def _step_MergeRows(el: Element, cfg: dict) -> None:
    """Merge rows (diff) — compara dos streams ordenados y marca cambios."""
    # El LLM puede usar "step1"/"step2" o "reference"/"compare_step"
    reference = cfg.get("reference") or cfg.get("step1") or cfg.get("reference_step") or ""
    compare   = cfg.get("compare") or cfg.get("compare_step") or cfg.get("step2") or cfg.get("compare_step_name") or ""
    if not reference or not compare:
        logger.warning(
            "MergeRows: faltan step1/step2. reference=%r compare=%r config completo=%r",
            reference, compare, cfg
        )
    keys_el = SubElement(el, "keys")
    for k in cfg.get("keys", []):
        _sub(keys_el, "key", k if isinstance(k, str) else k.get("name", ""))
    values_el = SubElement(el, "values")
    for v in cfg.get("values", []):
        _sub(values_el, "value", v if isinstance(v, str) else v.get("name", ""))
    _sub(el, "flag_field", cfg.get("flag_field", "flagfield"))
    _sub(el, "reference",  reference)
    _sub(el, "compare",    compare)


def _step_ConcatFields(el: Element, cfg: dict) -> None:
    _sub(el, "extra_field",         cfg.get("target_field", "concat_result"))
    _sub(el, "separator",           cfg.get("separator", ""))
    _sub(el, "enclosure",           cfg.get("enclosure", ""))
    _sub(el, "remove_selected_fields", "N")
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",      f if isinstance(f, str) else f.get("name", ""))
        _sub(field, "type",      "String" if isinstance(f, str) else f.get("type", "String"))
        _sub(field, "length",    "-1")
        _sub(field, "precision", "-1")


def _step_NumberRange(el: Element, cfg: dict) -> None:
    """NumberRangeMeta.loadXML hace Double.parseDouble(...) SIN guard de null sobre
    lower_bound/upper_bound/fallBackValue. Un tag vacío (<lower_bound/>) se serializa
    self-closing y XMLHandler.getTagValue lo devuelve como null (no ""), por eso un
    default "" ahí revienta Spoon con NPE al abrir el .ktr. Nunca dejar esos 3 tags
    sin texto: fallback numérico explícito, y se descarta la regla si falta bound."""
    _sub(el, "inputField",  cfg.get("input_field", ""))
    _sub(el, "outputField", cfg.get("output_field", "range"))
    _sub(el, "fallBackValue", str(cfg.get("fallback", 0)) or "0")
    rules = SubElement(el, "rules")
    for r in cfg.get("ranges", []):
        lower = r.get("lower")
        upper = r.get("upper")
        if lower is None or upper is None:
            logger.warning("NumberRange: rule sin lower/upper, se descarta. rule=%s", r)
            continue
        rule = SubElement(rules, "rule")
        _sub(rule, "lower_bound", str(lower))
        _sub(rule, "upper_bound", str(upper))
        _sub(rule, "value",       str(r.get("value", "")) or " ")


def _step_SplitFieldToRows(el: Element, cfg: dict) -> None:
    _sub(el, "splitfield",         cfg.get("split_field", cfg.get("field", "")))
    _sub(el, "delimiter",          cfg.get("delimiter", ","))
    _sub(el, "newfield",           cfg.get("new_field", "value"))
    _sub(el, "rownum",             "N")
    _sub(el, "rownum_field")
    _sub(el, "resetrownumber",     "Y")
    _sub(el, "delimiter_is_regex", "Y" if cfg.get("regex", False) else "N")


def _step_FieldSplitter(el: Element, cfg: dict) -> None:
    """Split Fields — un campo delimitado -> N columnas en la MISMA fila.
    No confundir con SplitFieldToRows (Split field to rows: un campo -> N filas)."""
    _sub(el, "splitfield", cfg.get("split_field", cfg.get("field", "")))
    _sub(el, "delimiter",  cfg.get("delimiter", ","))
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "id")
        _sub(field, "type",      f.get("type", "String"))
        _sub(field, "format",    f.get("format", ""))
        _sub(field, "group")
        _sub(field, "decimal")
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))
        _sub(field, "trimtype",  f.get("trim_type", "none"))
        _sub(field, "nullif")


def _step_Denormaliser(el: Element, cfg: dict) -> None:
    """Pivot filas->columnas. config = {key_field, group_fields:[...], pivots:[{field_name, key_value, target_name, target_type}]}"""
    _sub(el, "key_field", cfg.get("key_field", ""))
    group_el = SubElement(el, "group")
    for g in cfg.get("group_fields", []):
        ge = SubElement(group_el, "field")
        _sub(ge, "name", g if isinstance(g, str) else g.get("name", ""))
    fe = SubElement(el, "fields")
    for p in cfg.get("pivots", []):
        field = SubElement(fe, "field")
        _sub(field, "field_name",   p.get("field_name", ""))
        _sub(field, "key_value",    p.get("key_value", ""))
        _sub(field, "target_name",  p.get("target_name", ""))
        _sub(field, "target_type",  p.get("target_type", "String"))
        _sub(field, "target_format", p.get("target_format", ""))
        _sub(field, "target_length", str(p.get("target_length", -1)))
        _sub(field, "target_precision", str(p.get("target_precision", -1)))
        _sub(field, "target_aggregation_type", p.get("aggregation", "-"))


def _step_ValueMapper(el: Element, cfg: dict) -> None:
    field_to_use = (cfg.get("field_to_use") or cfg.get("source_field") or
                    cfg.get("field") or cfg.get("input_field") or "")
    if not field_to_use:
        logger.warning("ValueMapper: 'field_to_use' vacío — PDI fallará buscando campo [null]")
    _sub(el, "field_to_use",   field_to_use)
    _sub(el, "target_field",   cfg.get("target_field") or cfg.get("output_field") or field_to_use)
    _sub(el, "non_match_default", cfg.get("default", ""))
    fe = SubElement(el, "fields")
    for m in cfg.get("mappings", []):
        field = SubElement(fe, "field")
        _sub(field, "source_value", str(m.get("source", "")))
        _sub(field, "target_value", str(m.get("target", "")))


def _step_ReplaceString(el: Element, cfg: dict) -> None:
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "in_stream_name",  f.get("name", ""))
        _sub(field, "out_stream_name", f.get("rename", ""))
        _sub(field, "use_regex",       "Y" if f.get("regex", False) else "N")
        _sub(field, "replace_string",  f.get("search", ""))
        _sub(field, "replace_by_string", f.get("replace", ""))
        _sub(field, "set_empty_string", "N")
        _sub(field, "whole_word",       "N")
        _sub(field, "case_sensitive",   "Y" if f.get("case_sensitive", False) else "N")


# ─── Builders agregados (Fase 2: cobertura de los 18 tipos sin builder) ───────
# Cada uno verificado contra el código fuente real de pentaho-kettle (loadXML/
# readData de la Meta class correspondiente). Se documenta inline solo lo que
# no es obvio (tags con riesgo de NPE/NumberFormatException al cargar en Spoon).

def _step_Delete(el: Element, cfg: dict) -> None:
    """Mismo layout XML que Update/InsertUpdate (DeleteMeta.readData: <lookup><schema>/
    <table>/<key>(name/field/condition/name2)</lookup>), pero sin bloque de <value> —
    Delete no proyecta columnas de salida, solo condiciones de borrado."""
    table = cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or ""
    if not table:
        logger.warning("Delete: 'table' vacío — PDI fallará borrando de tabla null")
    _sub(el, "connection", cfg.get("connection", ""))
    _sub(el, "commit",     str(cfg.get("commit", 100)))
    lookup = SubElement(el, "lookup")
    _sub(lookup, "schema", cfg.get("schema", ""))
    _sub(lookup, "table",  table)
    for k in cfg.get("keys", []):
        ke = SubElement(lookup, "key")
        _sub(ke, "name",      k.get("stream_field", k.get("name", "")))
        _sub(ke, "field",     k.get("table_field",  k.get("field", "")))
        _sub(ke, "condition", k.get("condition", "="))
        _sub(ke, "name2")


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


def _step_AddSequence(el: Element, cfg: dict) -> None:
    use_db = bool(cfg.get("use_database", False))
    _sub(el, "valuename",    cfg.get("output_field") or cfg.get("valuename", "sequence"))
    _sub(el, "use_database", "Y" if use_db else "N")
    _sub(el, "connection",   cfg.get("connection", "") if use_db else "")
    _sub(el, "schema",       cfg.get("schema", ""))
    _sub(el, "seqname",      cfg.get("sequence_name") or cfg.get("seqname", ""))
    _sub(el, "use_counter",  "N" if use_db else "Y")
    _sub(el, "counter_name", cfg.get("counter_name", ""))
    _sub(el, "start_at",     str(cfg.get("start_at", 1)))
    _sub(el, "increment_by", str(cfg.get("increment_by", 1)))
    _sub(el, "max_value",    str(cfg.get("max_value", 999999999)))


def _step_Formula(el: Element, cfg: dict) -> None:
    """FormulaMeta.loadXML NO envuelve las fórmulas en un <fields> — cada <formula> es
    hijo directo del step (a diferencia de Calculator). value_length/value_precision
    usan Const.toInt (con default), sin riesgo de NPE."""
    for f in cfg.get("formulas", cfg.get("fields", [])):
        formula = SubElement(el, "formula")
        _sub(formula, "field_name",      f.get("field_name") or f.get("name", ""))
        _sub(formula, "formula_string",  f.get("formula", ""))
        _sub(formula, "value_type",      f.get("type", "String"))
        _sub(formula, "value_length",    str(f.get("length", -1)))
        _sub(formula, "value_precision", str(f.get("precision", -1)))
        _sub(formula, "replace_field",   f.get("replace_field", ""))


def _step_RegexEval(el: Element, cfg: dict) -> None:
    _sub(el, "script",             cfg.get("regex") or cfg.get("script", ""))
    _sub(el, "matcher",            cfg.get("field") or cfg.get("matcher", ""))
    _sub(el, "resultfieldname",    cfg.get("result_field") or cfg.get("resultfieldname", ""))
    _sub(el, "usevar",             "N")
    _sub(el, "allowcapturegroups", "Y" if cfg.get("capture_groups") else "N")
    _sub(el, "replacefields",      "N")
    _sub(el, "canoneq",            "N")
    _sub(el, "caseinsensitive",    "Y" if cfg.get("case_insensitive") else "N")
    _sub(el, "comment",            "N")
    _sub(el, "dotall",             "N")
    _sub(el, "multiline",          "N")
    _sub(el, "unicode",            "N")
    _sub(el, "unix",               "N")
    fe = SubElement(el, "fields")
    for g in cfg.get("capture_fields", cfg.get("fields", [])):
        field = SubElement(fe, "field")
        _sub(field, "name",      g.get("name", ""))
        _sub(field, "type",      g.get("type", "String"))
        _sub(field, "format",    g.get("format", ""))
        _sub(field, "group")
        _sub(field, "decimal")
        _sub(field, "currency")
        _sub(field, "length",    str(g.get("length", -1)))
        _sub(field, "precision", str(g.get("precision", -1)))
        _sub(field, "nullif")
        _sub(field, "ifnull")
        _sub(field, "trimtype",  g.get("trim_type", "none"))


def _step_JoinRows(el: Element, cfg: dict) -> None:
    """JoinRowsMeta usa el tag 'main' (no 'main_step') para identificar el step
    principal, y reutiliza el mismo <compare><condition> que FilterRows (clase
    Condition compartida en core). cache_size ya viene protegido con Const.toInt."""
    main_step = cfg.get("main_step") or cfg.get("step1") or ""
    if not main_step:
        logger.warning("JoinRows: 'main_step' vacío — PDI no sabrá qué stream usar como principal")
    _sub(el, "directory",  cfg.get("directory", "%%java.io.tmpdir%%"))
    _sub(el, "prefix",     cfg.get("prefix", "out"))
    _sub(el, "cache_size", str(cfg.get("cache_size", 500)))
    _sub(el, "main",       main_step)
    compare = SubElement(el, "compare")
    cond = SubElement(compare, "condition")
    _sub(cond, "negated",    "N")
    _sub(cond, "operator",   "-")
    _sub(cond, "leftvalue",  cfg.get("left_field", ""))
    _sub(cond, "function",   cfg.get("operator", "="))
    _sub(cond, "rightvalue", cfg.get("right_field", ""))
    val = SubElement(cond, "value")
    _sub(val, "name",      "constant")
    _sub(val, "type",      "String")
    _sub(val, "text")
    _sub(val, "length",    "-1")
    _sub(val, "precision", "-1")
    _sub(val, "isnull",    "Y")
    _sub(val, "mask")
    SubElement(cond, "conditions")


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


def _step_TextFileInput(el: Element, cfg: dict) -> None:
    filename = cfg.get("filename", "")
    if not filename:
        logger.warning("TextFileInput: 'filename' vacío — Spoon no tendrá archivo que leer")
    _sub(el, "accept_filenames",       "N")
    _sub(el, "passing_through_fields", "N")
    _sub(el, "accept_field")
    _sub(el, "accept_stepname")
    _sub(el, "separator",              cfg.get("separator", ";"))
    _sub(el, "enclosure",              cfg.get("enclosure", '"'))
    _sub(el, "enclosure_breaks",       "N")
    _sub(el, "escapechar")
    _sub(el, "header",                 "Y" if cfg.get("header", True) else "N")
    _sub(el, "nr_headerlines",         str(cfg.get("header_lines", 1)))
    _sub(el, "footer",                 "N")
    _sub(el, "nr_footerlines",         "0")
    _sub(el, "line_wrapped",           "N")
    _sub(el, "nr_wraps",               "0")
    _sub(el, "layout_paged",           "N")
    _sub(el, "nr_lines_per_page",      "0")
    _sub(el, "nr_lines_doc_header",    "0")
    _sub(el, "add_to_result_filenames", "Y")
    _sub(el, "noempty",                "Y" if cfg.get("no_empty_lines", True) else "N")
    _sub(el, "include",                "N")
    _sub(el, "include_field")
    _sub(el, "rownum",                 "N")
    _sub(el, "rownumByFile",           "N")
    _sub(el, "rownum_field")
    _sub(el, "format",                 cfg.get("format", "mixed"))
    _sub(el, "encoding",               cfg.get("encoding", ""))

    file_el = SubElement(el, "file")
    _sub(file_el, "name",               filename)
    _sub(file_el, "filemask")
    _sub(file_el, "exclude_filemask")
    _sub(file_el, "file_required",      "N")
    _sub(file_el, "include_subfolders", "N")
    _sub(file_el, "type",               "CSV")
    _sub(file_el, "compression",        "None")

    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "type",      f.get("type", "String"))
        _sub(field, "format",    f.get("format", ""))
        _sub(field, "currency")
        _sub(field, "decimal")
        _sub(field, "group")
        _sub(field, "nullif")
        _sub(field, "ifnull")
        _sub(field, "position",  "-1")
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))
        _sub(field, "trim_type", f.get("trim_type", "none"))
        _sub(field, "repeat",    "N")

    _sub(el, "limit",              "0")
    _sub(el, "error_ignored",      "N")
    _sub(el, "skip_bad_files",     "N")
    _sub(el, "file_error_field")
    _sub(el, "file_error_message_field")
    _sub(el, "error_line_skipped", "N")
    _sub(el, "error_count_field")
    _sub(el, "error_fields_field")
    _sub(el, "error_text_field")
    _sub(el, "bad_line_files_destination_directory")
    _sub(el, "bad_line_files_extension")
    _sub(el, "error_line_files_destination_directory")
    _sub(el, "error_line_files_extension")
    _sub(el, "line_number_files_destination_directory")
    _sub(el, "line_number_files_extension")
    _sub(el, "date_format_lenient", "Y")


def _step_TextFileOutput(el: Element, cfg: dict) -> None:
    filename = cfg.get("filename", "")
    if not filename:
        logger.warning("TextFileOutput: 'filename' vacío — Spoon no tendrá archivo destino")
    _sub(el, "separator",              cfg.get("separator", ";"))
    _sub(el, "enclosure",              cfg.get("enclosure", '"'))
    _sub(el, "enclosure_forced",       "N")
    _sub(el, "enclosure_fix_disabled", "N")
    _sub(el, "header",                 "Y" if cfg.get("header", True) else "N")
    _sub(el, "footer",                 "N")
    _sub(el, "format",                 cfg.get("format", "DOS"))
    _sub(el, "compression",            "None")
    _sub(el, "encoding",               cfg.get("encoding", ""))
    _sub(el, "endedLine")
    _sub(el, "fileNameInField",        "N")
    _sub(el, "fileNameField")

    file_el = SubElement(el, "file")
    _sub(file_el, "name",                     filename)
    _sub(file_el, "extention",                cfg.get("extension", "txt"))
    _sub(file_el, "append",                   "Y" if cfg.get("append", False) else "N")
    _sub(file_el, "split",                    "N")
    _sub(file_el, "haspartno",                "N")
    _sub(file_el, "add_date",                 "N")
    _sub(file_el, "add_time",                 "N")
    _sub(file_el, "SpecifyFormat",            "N")
    _sub(file_el, "date_time_format")
    _sub(file_el, "add_to_result_filenames",  "Y")
    _sub(file_el, "create_parent_folder",     "Y")
    _sub(file_el, "servlet_output",           "N")
    _sub(file_el, "do_not_open_new_file_init", "N")
    _sub(file_el, "pad",                      "N")
    _sub(file_el, "fast_dump",                "N")
    _sub(file_el, "splitevery",               "0")

    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "type",      f.get("type", "String"))
        _sub(field, "format",    f.get("format", ""))
        _sub(field, "currency")
        _sub(field, "decimal")
        _sub(field, "group")
        _sub(field, "trim_type", f.get("trim_type", "none"))
        _sub(field, "nullif")
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))


def _step_ExcelInput(el: Element, cfg: dict) -> None:
    filename = cfg.get("filename", "")
    if not filename:
        logger.warning("ExcelInput: 'filename' vacío — Spoon no tendrá archivo que leer")
    _sub(el, "header",       "Y" if cfg.get("header", True) else "N")
    _sub(el, "noempty",      "Y")
    _sub(el, "stoponempty",  "N")
    _sub(el, "sheetrownumfield")
    _sub(el, "rownumfield")
    _sub(el, "sheetfield")
    _sub(el, "filefield")
    _sub(el, "limit",        "0")
    _sub(el, "encoding",     cfg.get("encoding", ""))
    _sub(el, "add_to_result_filenames", "Y")
    _sub(el, "accept_filenames", "N")
    _sub(el, "accept_field")
    _sub(el, "accept_stepname")

    file_el = SubElement(el, "file")
    _sub(file_el, "name",               filename)
    _sub(file_el, "filemask")
    _sub(file_el, "exclude_filemask")
    _sub(file_el, "file_required",      "N")
    _sub(file_el, "include_subfolders", "N")

    sheets_el = SubElement(el, "sheets")
    for s in cfg.get("sheets", [{"name": cfg.get("sheet_name", "Sheet1")}]):
        sheet = SubElement(sheets_el, "sheet")
        _sub(sheet, "name",     s.get("name", "Sheet1"))
        _sub(sheet, "startrow", str(s.get("start_row", 0)))
        _sub(sheet, "startcol", str(s.get("start_col", 0)))

    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "type",      f.get("type", "String"))
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))
        _sub(field, "trim_type", f.get("trim_type", "none"))
        _sub(field, "repeat",    "N")
        _sub(field, "format",    f.get("format", ""))
        _sub(field, "currency")
        _sub(field, "decimal")
        _sub(field, "group")

    _sub(el, "strict_types",      "N")
    _sub(el, "error_ignored",     "N")
    _sub(el, "error_line_skipped", "N")
    _sub(el, "bad_line_files_destination_directory")
    _sub(el, "bad_line_files_extension")
    _sub(el, "error_line_files_destination_directory")
    _sub(el, "error_line_files_extension")


def _step_ExcelOutput(el: Element, cfg: dict) -> None:
    filename = cfg.get("filename", "")
    if not filename:
        logger.warning("ExcelOutput: 'filename' vacío — Spoon no tendrá archivo destino")
    _sub(el, "header", "Y" if cfg.get("header", True) else "N")
    _sub(el, "footer", "N")
    _sub(el, "encoding", cfg.get("encoding", ""))
    _sub(el, "append",  "N")
    _sub(el, "add_to_result_filenames", "Y")

    file_el = SubElement(el, "file")
    _sub(file_el, "name",                      filename)
    _sub(file_el, "extention",                 cfg.get("extension", "xls"))
    _sub(file_el, "do_not_open_newfile_init",  "N")
    _sub(file_el, "create_parent_folder",      "Y")
    _sub(file_el, "split",                     "N")
    _sub(file_el, "add_date",                  "N")
    _sub(file_el, "add_time",                  "N")
    _sub(file_el, "SpecifyFormat",             "N")
    _sub(file_el, "date_time_format")
    _sub(file_el, "usetempfiles",              "N")
    _sub(file_el, "tempdirectory")
    _sub(file_el, "autosizecolums",            "Y")
    _sub(file_el, "nullisblank",               "N")
    _sub(file_el, "protect_sheet",             "N")
    _sub(file_el, "password")
    _sub(file_el, "splitevery",                "0")
    _sub(file_el, "sheetname",                 cfg.get("sheet_name", "Sheet1"))

    tmpl = SubElement(el, "template")
    _sub(tmpl, "enabled", "N")
    _sub(tmpl, "append",  "N")
    _sub(tmpl, "filename")

    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",   f.get("name", ""))
        _sub(field, "type",   f.get("type", "String"))
        _sub(field, "format", f.get("format", ""))

    # Bloque <custom> (apariencia): getFontXByCode()/getFontColorByCode() en
    # ExcelOutputMeta devuelven 0 ante código vacío o no reconocido (sin excepción),
    # así que estos valores son solo estéticos, nunca críticos para la carga.
    custom = SubElement(el, "custom")
    _sub(custom, "header_font_name",        "Arial")
    _sub(custom, "header_font_size",        "10")
    _sub(custom, "header_font_bold",        "Y")
    _sub(custom, "header_font_italic",      "N")
    _sub(custom, "header_font_underline",   "none")
    _sub(custom, "header_font_orientation", "horizontal")
    _sub(custom, "header_font_color",       "0")
    _sub(custom, "header_background_color", "-1")
    _sub(custom, "header_row_height",       "-1")
    _sub(custom, "header_alignment",        "left")
    _sub(custom, "header_image")
    _sub(custom, "row_font_name",           "Arial")
    _sub(custom, "row_font_size",           "10")
    _sub(custom, "row_font_color",          "0")
    _sub(custom, "row_background_color",   "-1")


def _step_JsonInput(el: Element, cfg: dict) -> None:
    filename = cfg.get("filename", "")
    in_fields = bool(cfg.get("source_field"))
    if not filename and not in_fields:
        logger.warning("JsonInput: ni 'filename' ni 'source_field' configurados — sin origen de datos")
    _sub(el, "include",              "N")
    _sub(el, "include_field")
    _sub(el, "rownum",               "N")
    _sub(el, "addresultfile",        "Y")
    _sub(el, "readurl",              "N")
    _sub(el, "removeSourceField",    "N")
    _sub(el, "IsIgnoreEmptyFile",    "N")
    _sub(el, "doNotFailIfNoFile",    "N")
    _sub(el, "ignoreMissingPath",    "N")
    _sub(el, "defaultPathLeafToNull", "Y")
    _sub(el, "IsInFields",           "Y" if in_fields else "N")
    _sub(el, "rownum_field")

    file_el = SubElement(el, "file")
    _sub(file_el, "name",               filename)
    _sub(file_el, "filemask")
    _sub(file_el, "exclude_filemask")
    _sub(file_el, "file_required",      "N")
    _sub(file_el, "include_subfolders", "N")

    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "path",      f.get("path", ""))
        _sub(field, "type",      f.get("type", "String"))
        _sub(field, "format",    f.get("format", ""))
        _sub(field, "currency")
        _sub(field, "decimal")
        _sub(field, "group")
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))
        _sub(field, "trim_type", f.get("trim_type", "none"))
        _sub(field, "repeat",    "N")

    _sub(el, "limit",      "0")
    _sub(el, "IsAFile",    "N")
    _sub(el, "valueField", cfg.get("source_field", ""))
    _sub(el, "shortFileFieldName")
    _sub(el, "pathFieldName")
    _sub(el, "hiddenFieldName")
    _sub(el, "lastModificationTimeFieldName")
    _sub(el, "uriNameFieldName")
    _sub(el, "rootUriNameFieldName")
    _sub(el, "extensionFieldName")
    _sub(el, "sizeFieldName")


def _step_JsonOutput(el: Element, cfg: dict) -> None:
    fields = cfg.get("fields", [])
    if not fields:
        logger.warning("JsonOutput: sin 'fields' — el JSON generado estará vacío")
    _sub(el, "outputValue",        cfg.get("output_field", "json_output"))
    _sub(el, "jsonBloc",           cfg.get("json_block", "data"))
    _sub(el, "nrRowsInBloc",       str(cfg.get("rows_per_block", 1)))
    _sub(el, "operation_type",     cfg.get("operation_type", "writetofile"))
    _sub(el, "compatibility_mode", "N")
    _sub(el, "encoding",           cfg.get("encoding", ""))
    _sub(el, "AddToResult",        "Y")

    file_el = SubElement(el, "file")
    _sub(file_el, "name",                 cfg.get("filename", ""))
    _sub(file_el, "create_parent_folder", "Y")
    _sub(file_el, "extention",            cfg.get("extension", "json"))
    _sub(file_el, "append",               "N")
    _sub(file_el, "split",                "N")
    _sub(file_el, "haspartno",            "N")
    _sub(file_el, "add_date",             "N")
    _sub(file_el, "add_time",             "N")
    _sub(file_el, "DoNotOpenNewFileInit", "N")
    _sub(file_el, "servlet_output",       "N")

    fe = SubElement(el, "fields")
    for f in fields:
        field = SubElement(fe, "field")
        _sub(field, "name",    f.get("name", ""))
        _sub(field, "element", f.get("element") or f.get("name", ""))


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


def _step_AnalyticQuery(el: Element, cfg: dict) -> None:
    """AnalyticQueryMeta.readData hace Integer.parseInt(getTagValue(fnode,'valuefield'))
    SIN Const.toInt de por medio — un 'valuefield' vacío tira NumberFormatException al
    abrir el .ktr en Spoon, el mismo bug que ya vimos en NumberRange. Nunca dejarlo sin
    un entero real."""
    group_el = SubElement(el, "group")
    for g in cfg.get("group_fields", []):
        ge = SubElement(group_el, "field")
        _sub(ge, "name", g if isinstance(g, str) else g.get("name", ""))
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "aggregate",  f.get("result_field") or f.get("aggregate", ""))
        _sub(field, "subject",    f.get("subject_field") or f.get("subject", ""))
        _sub(field, "type",       str(f.get("type", "LEAD")).upper())
        _sub(field, "valuefield", str(f.get("offset", f.get("valuefield", 1))) or "1")


# ─── Alias map ────────────────────────────────────────────────────────────────
# El modelo a veces devuelve los nombres "display" de Spoon (con espacios) y otras
# veces los nombres "internos" (camelCase). Este mapa normaliza ambos a la forma
# canónica usada por STEP_BUILDERS antes de buscar el builder.

STEP_TYPE_ALIASES = {
    # Entrada
    "Table Input":               "TableInput",
    "CSV file input":            "CsvInput",
    "CSVInput":                  "CsvInput",
    "Text File Input":           "TextFileInput",
    "Microsoft Excel Input":     "ExcelInput",
    "Excel Input":               "ExcelInput",
    "JSON Input":                "JsonInput",
    "XML input stream (SAX)":    "GetXMLData",
    "REST Client":               "Rest",
    # Transformación
    "Select values":             "SelectValues",
    "Filter rows":               "FilterRows",
    "Sort rows":                 "SortRows",
    "Group by":                  "GroupBy",
    "Memory Group by":           "MemoryGroupBy",
    "Unique rows":               "Unique",
    "Unique rows (HashSet)":     "UniqueRowsByHashSet",
    "Calculator":                "Calculator",
    "String operations":         "StringOperations",
    "Replace in string":         "ReplaceString",
    "Concat fields":             "ConcatFields",
    "Split fields":              "SplitFieldToRows",
    "Value mapper":              "ValueMapper",
    "Null if...":                "IfNull",
    "If field value is null":    "IfNull",
    "Add constants":             "Constant",
    "AddConstants":              "Constant",
    "Number range":              "NumberRange",
    "Regex evaluation":          "RegexEval",
    "Row Normaliser":            "Normaliser",
    "Row denormaliser":          "Denormaliser",
    # Joins / lookups
    "Database lookup":           "DBLookup",
    "Database Lookup":           "DBLookup",
    "DatabaseLookup":            "DBLookup",
    "Stream lookup":             "StreamLookup",
    "Merge rows (diff)":         "MergeRows",
    "Merge join":                "MergeJoin",
    "Merge Join":                "MergeJoin",
    # Salida
    "Table Output":              "TableOutput",
    "Insert / Update":           "InsertUpdate",
    "Update":                    "Update",
    "Delete":                    "Delete",
    "Microsoft Excel Writer":    "MicrosoftExcelWriter",
    "Text file output":          "TextFileOutput",
    "JSON output":               "JsonOutput",
    # Dimensiones / DWH
    "Dimension lookup/update":   "DimensionLookup",
    "Combination lookup/update": "CombinationLookup",
    # Calidad / logging
    "Field meta data validation": "FieldMetaDataValidation",
    "Data validator":            "DataValidator",
    "Write to log":              "WriteToLog",
    # Control de flujo
    "Mapping (sub-transformation)": "Mapping",
    "Transformation executor":   "TransExecutor",
    "Get System Info":           "GetSystemInfo",
}


def _step_generic(el: Element, cfg: dict) -> None:
    for key, val in cfg.items():
        if isinstance(val, (str, int, float)):
            _sub(el, key, str(val))
        elif isinstance(val, bool):
            _sub(el, key, "Y" if val else "N")


STEP_BUILDERS = {
    # Entrada
    "TableInput":          _step_TableInput,
    "CsvInput":            _step_CsvInput,
    "TextFileInput":       _step_TextFileInput,
    "ExcelInput":          _step_ExcelInput,
    "JsonInput":           _step_JsonInput,
    # Salida
    "TableOutput":         _step_TableOutput,
    "InsertUpdate":        _step_InsertUpdate,
    "Update":              _step_Update,
    "Delete":              _step_Delete,
    "TextFileOutput":      _step_TextFileOutput,
    "ExcelOutput":         _step_ExcelOutput,
    "JsonOutput":          _step_JsonOutput,
    # Selección / orden / filtros / unique
    "SelectValues":        _step_SelectValues,
    "FilterRows":          _step_FilterRows,
    "SortRows":            _step_SortRows,
    "GroupBy":             _step_GroupBy,
    "MemoryGroupBy":       _step_GroupBy,
    "Unique":              _step_Unique,
    "UniqueRowsByHashSet": _step_Unique,
    "RegexEval":           _step_RegexEval,
    "AnalyticQuery":       _step_AnalyticQuery,
    # Joins / lookups
    "MergeJoin":           _step_MergeJoin,
    "JoinRows":            _step_JoinRows,
    "StreamLookup":        _step_StreamLookup,
    "MergeRows":           _step_MergeRows,
    "DBLookup":            _step_DBLookup,
    # DWH
    "DimensionLookup":     _step_DimensionLookup,
    "CombinationLookup":   _step_CombinationLookup,
    # Cálculo / texto / constantes
    "Calculator":          _step_Calculator,
    "Formula":             _step_Formula,
    "Constant":            _step_Constant,
    "AddSequence":         _step_AddSequence,
    "StringOperations":    _step_StringOperations,
    "ReplaceString":       _step_ReplaceString,
    "ConcatFields":        _step_ConcatFields,
    "ValueMapper":         _step_ValueMapper,
    "IfNull":              _step_IfNull,
    "NumberRange":         _step_NumberRange,
    "SplitFieldToRows":    _step_SplitFieldToRows,
    "SplitFieldToRows3":   _step_SplitFieldToRows,
    "FieldSplitter":       _step_FieldSplitter,
    "Denormaliser":        _step_Denormaliser,
    "ScriptValueMod":      _step_ScriptValueMod,
    # Calidad / control
    "DataValidator":       _step_DataValidator,
    "WriteToLog":          _step_WriteToLog,
    "ExecSQL":             _step_ExecSQL,
    "SetVariable":         _step_SetVariable,
    "GetVariable":         _step_GetVariable,
    "Abort":               _step_Abort,
    "BlockingStep":        _step_BlockingStep,
    "Dummy":               _step_Dummy,
    "GetSystemInfo":       _step_GetSystemInfo,
}


# ─── Master whitelist: IDs válidos de plugin PDI 9.x ──────────────────────────
# Debe reflejar la lista "NOMBRES DE PLUGIN PDI" de system_etl.txt 1:1. Un
# `type` que el modelo devuelva fuera de este set no es un plugin real de
# Kettle — abrir ese .ktr en Spoon falla con "plugin missing". build_ktr()
# corrige cualquier type fuera de lista a Dummy antes de serializar, en vez
# de depender de que el modelo nunca alucine un id.
KNOWN_PDI_STEP_TYPES = set(STEP_BUILDERS.keys()) | set(STEP_TYPE_ALIASES.values()) | {
    "AddSequence", "Formula", "RegexEval", "JoinRows", "ExecSQL",
    "SetVariable", "GetVariable", "Abort", "BlockingStep",
    "TextFileInput", "TextFileOutput", "ExcelInput", "ExcelOutput",
    "JsonInput", "JsonOutput", "ScriptValueMod", "AnalyticQuery",
}


# ─── Auto-layout ──────────────────────────────────────────────────────────────

def _auto_layout(steps: list, hops: list) -> list:
    """Compute x/y for any step missing them, using topological column ordering."""
    # Build in-degree map
    in_degree = {s["name"]: 0 for s in steps}
    for hop in hops:
        to = hop.get("to")
        if to in in_degree:
            in_degree[to] += 1

    queue   = [name for name, deg in in_degree.items() if deg == 0]
    columns = {}
    col     = 0

    while queue:
        for name in queue:
            if name not in columns:
                columns[name] = col
        next_q = []
        for name in queue:
            for hop in hops:
                if hop.get("from") == name:
                    to = hop.get("to")
                    if to in in_degree:
                        in_degree[to] -= 1
                        if in_degree[to] == 0:
                            next_q.append(to)
        queue = next_q
        col += 1

    for s in steps:
        if s["name"] not in columns:
            columns[s["name"]] = col
            col += 1

    col_used: dict[int, int] = {}
    result = []
    for step in steps:
        name  = step["name"]
        c     = columns.get(name, 0)
        row   = col_used.get(c, 0)
        col_used[c] = row + 1
        new_step    = dict(step)
        if not step.get("x") or not step.get("y"):
            new_step["x"] = 100 + c * 200
            new_step["y"] = 100 + row * 120
        result.append(new_step)

    return result


# ─── KTR validation ───────────────────────────────────────────────────────────

def _validate_ktr(ktr: dict) -> list[str]:
    warnings = []
    step_names = {s["name"] for s in ktr.get("steps", [])}
    # Normalizar tipos usando los aliases, así reconocemos tanto "Table Input" como "TableInput"
    types = {STEP_TYPE_ALIASES.get(s["type"], s["type"]) for s in ktr.get("steps", [])}

    input_types  = {"TableInput", "CsvInput", "ExcelInput", "TextFileInput", "JsonInput", "DataGrid", "RowGenerator"}
    output_types = {"TableOutput", "InsertUpdate", "Update", "Delete"}

    if not input_types & types:
        warnings.append("KTR no tiene ningún step de entrada (TableInput, etc.)")
    if not output_types & types:
        warnings.append("KTR no tiene ningún step de salida (TableOutput, InsertUpdate, etc.)")

    for hop in ktr.get("hops", []):
        if hop.get("from") not in step_names:
            warnings.append(f"Hop hace referencia a step inexistente: '{hop.get('from')}'")
        if hop.get("to") not in step_names:
            warnings.append(f"Hop hace referencia a step inexistente: '{hop.get('to')}'")

    return warnings


# ─── Public entry point ───────────────────────────────────────────────────────

def _sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name).strip("_") or "Transformacion_ETL"


def build_ktr(
    ktr_data: dict,
    process_name: str = "",
    real_connections: dict[str, dict] | None = None,
    required_columns_by_table: dict[str, list[str]] | None = None,
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

    Returns (ktr_xml_string, filename, warnings). Returns ("", "", []) if ktr_data is empty.
    """
    if not ktr_data:
        return "", "", []

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

    name        = ktr_data.get("name") or process_name or "Transformacion_ETL"
    description = ktr_data.get("description", "")
    connections = ktr_data.get("connections", [])
    steps       = _auto_layout(ktr_data.get("steps", []), ktr_data.get("hops", []))
    hops        = ktr_data.get("hops", [])

    # Diagnóstico: loggear config completo de steps con campos críticos vacíos
    _CRITICAL_FIELDS = {
        "TableOutput":      ["table"],
        "InsertUpdate":     ["table"],
        "Update":           ["table"],
        "Delete":           ["table"],
        "DimensionLookup":  ["table", "returnfield"],
        "CombinationLookup":["table", "returnfield"],
        "DBLookup":         ["table"],
        "MergeRows":        ["step1", "step2"],
        "MergeJoin":        ["step1", "step2"],
        "ValueMapper":      ["field_to_use"],
    }
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
            resolved = _resolve_connection(cfg, canonical, connection_names)
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
    for conn in connections:
        _build_connection(trans, conn, real=(real_connections or {}).get(conn.get("name", "")))

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

        # Rechazo/corrección: un type fuera del whitelist de plugins PDI reales
        # no es "un tipo no soportado por el backend" — es un id inexistente en
        # Kettle, y Spoon rompe con "plugin missing" al abrir el .ktr. Se fuerza
        # a Dummy (mantiene el grafo/hops intactos) en vez de emitirlo tal cual.
        if canonical_type not in KNOWN_PDI_STEP_TYPES:
            warnings.append(
                f"Step '{step.get('name')}' usa type '{step_type}' — no es un plugin PDI 9.x "
                f"reconocido, se reemplazó por 'Dummy'. Reconfigurar manualmente en Spoon."
            )
            logger.warning("KTR: step type '%s' no está en KNOWN_PDI_STEP_TYPES, forzado a Dummy", step_type)
            canonical_type = "Dummy"
            cfg = {}

        if canonical_type != step_type:
            logger.info("KTR: step type '%s' normalizado a '%s'", step_type, canonical_type)
            # Reescribir el <type> en el XML para que Spoon lo reconozca
            type_el = step_el.find("type")
            if type_el is not None:
                type_el.text = canonical_type
        builder = STEP_BUILDERS.get(canonical_type)
        if builder:
            builder(step_el, cfg)
        else:
            logger.warning("KTR: step type '%s' (canonical: '%s') not supported, using generic builder", step_type, canonical_type)
            _step_generic(step_el, cfg)

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

    return ktr_xml, filename, warnings
