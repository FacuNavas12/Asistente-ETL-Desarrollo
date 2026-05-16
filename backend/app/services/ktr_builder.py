"""
KTR serializer: converts the ktr JSON structure returned by Gemini into valid .ktr XML.
No AI calls — pure Python data transformation.
"""
import re
import logging
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

logger = logging.getLogger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sub(parent: Element, tag: str, text: str = "") -> Element:
    el = SubElement(parent, tag)
    if text:
        el.text = str(text)
    return el


# ─── Connection block ─────────────────────────────────────────────────────────

def _build_connection(trans: Element, conn: dict) -> None:
    c = SubElement(trans, "connection")
    _sub(c, "name",     conn.get("name", "conn_default"))
    _sub(c, "server",   conn.get("host", "PLACEHOLDER_HOST"))
    _sub(c, "type",     conn.get("type", "GENERIC"))
    _sub(c, "access",   "Native")
    _sub(c, "database", conn.get("database", "PLACEHOLDER_DATABASE"))
    _sub(c, "port",     str(conn.get("port", 0)))
    _sub(c, "username", conn.get("username", "PLACEHOLDER_USER"))
    _sub(c, "password", "Encrypted ")
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
    _sub(el, "connection",     cfg.get("connection", ""))
    _sub(el, "schema",         cfg.get("schema", ""))
    _sub(el, "table",          cfg.get("table", ""))
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
    _sub(el, "connection", cfg.get("connection", ""))
    _sub(el, "schema",     cfg.get("schema", ""))
    _sub(el, "table",      cfg.get("table", ""))
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


def _step_SelectValues(el: Element, cfg: dict) -> None:
    fe = SubElement(el, "fields")
    for f in cfg.get("select", []):
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "rename",    f.get("rename", ""))
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))
    re_el = SubElement(el, "remove")
    for r in cfg.get("remove", []):
        _sub(re_el, "field", r if isinstance(r, str) else r.get("name", ""))
    meta = SubElement(el, "meta")
    for f in cfg.get("cast", []):
        field = SubElement(meta, "field")
        _sub(field, "name",                 f.get("name", ""))
        _sub(field, "rename")
        _sub(field, "type",                 f.get("type", "String"))
        _sub(field, "length",               "-1")
        _sub(field, "precision",            "-1")
        _sub(field, "conversion_mask")
        _sub(field, "date_format_lenient",  "false")
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
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        name = f.get("name", f) if isinstance(f, dict) else str(f)
        asc  = f.get("ascending", True) if isinstance(f, dict) else True
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
        _sub(field, "aggregate", agg.get("name", agg.get("aggregate", "")))
        _sub(field, "subject",   agg.get("subject", agg.get("field", "")))
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
    _sub(el, "schema",                    cfg.get("schema", ""))
    _sub(el, "table",                     cfg.get("table", ""))
    _sub(el, "connection",                cfg.get("connection", ""))
    _sub(el, "update",                    "Y")
    _sub(el, "returnfield",               cfg.get("return_field", "id_sk"))
    _sub(el, "preload_cache",             "N")
    _sub(el, "cache_size",                "5000")
    _sub(el, "use_start_date_alternative","N")
    _sub(el, "start_date_alternative")
    _sub(el, "use_alternative_start_date","N")
    _sub(el, "batch_size",                "0")
    fe = SubElement(el, "fields")
    for k in cfg.get("keys", []):
        ke = SubElement(fe, "key")
        _sub(ke, "name",   k.get("stream", k.get("name", "")))
        _sub(ke, "lookup", k.get("lookup", k.get("name", "")))
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",   f.get("stream", f.get("name", "")))
        _sub(field, "lookup", f.get("lookup", f.get("name", "")))
        _sub(field, "update", "Y" if f.get("update", True) else "N")
        _sub(field, "type",   f.get("type", "Insert"))
    date_el = SubElement(fe, "date")
    _sub(date_el, "name",       cfg.get("date_from", "fecha_desde"))
    _sub(date_el, "datename",   cfg.get("date_to",   "fecha_hasta"))
    _sub(date_el, "dateformat", "yyyy-MM-dd")


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


def _step_generic(el: Element, cfg: dict) -> None:
    for key, val in cfg.items():
        if isinstance(val, (str, int, float)):
            _sub(el, key, str(val))
        elif isinstance(val, bool):
            _sub(el, key, "Y" if val else "N")


STEP_BUILDERS = {
    "TableInput":          _step_TableInput,
    "TableOutput":         _step_TableOutput,
    "InsertUpdate":        _step_InsertUpdate,
    "SelectValues":        _step_SelectValues,
    "FilterRows":          _step_FilterRows,
    "SortRows":            _step_SortRows,
    "GroupBy":             _step_GroupBy,
    "MemoryGroupBy":       _step_GroupBy,
    "MergeJoin":           _step_MergeJoin,
    "DimensionLookup":     _step_DimensionLookup,
    "CombinationLookup":   _step_CombinationLookup,
    "WriteToLog":          _step_WriteToLog,
    "StringOperations":    _step_StringOperations,
    "IfNull":              _step_IfNull,
    "Unique":              _step_Unique,
    "UniqueRowsByHashSet": _step_Unique,
    "Dummy":               _step_Dummy,
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
    types = {s["type"] for s in ktr.get("steps", [])}

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


def build_ktr(ktr_data: dict, process_name: str = "") -> tuple[str, str]:
    """
    Convert KTR JSON dict from Gemini response to .ktr XML string.
    Returns (ktr_xml_string, filename).  Returns ("", "") if ktr_data is empty.
    """
    if not ktr_data:
        return "", ""

    warnings = _validate_ktr(ktr_data)
    for w in warnings:
        logger.warning("KTR validation: %s", w)

    name        = ktr_data.get("name") or process_name or "Transformacion_ETL"
    description = ktr_data.get("description", "")
    connections = ktr_data.get("connections", [])
    steps       = _auto_layout(ktr_data.get("steps", []), ktr_data.get("hops", []))
    hops        = ktr_data.get("hops", [])

    trans = Element("transformation")

    # Info
    info = SubElement(trans, "info")
    _sub(info, "name",                 name)
    _sub(info, "description",          description)
    _sub(info, "extended_description")
    _sub(info, "trans_version")
    _sub(info, "trans_status",         "0")
    dir_el = SubElement(info, "directory")
    dir_el.text = "/"

    # Connections
    for conn in connections:
        _build_connection(trans, conn)

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

        cfg     = step.get("config", {})
        builder = STEP_BUILDERS.get(step_type)
        if builder:
            builder(step_el, cfg)
        else:
            logger.warning("KTR: step type '%s' not supported, using generic builder", step_type)
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

    return ktr_xml, filename
