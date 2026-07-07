"""Builders de transformación de fila/columna: SelectValues, FilterRows, SortRows,
GroupBy, Unique, Calculator, Formula, Constant, StringOperations, ReplaceString,
ConcatFields, ValueMapper, IfNull, NumberRange, SplitFieldToRows, FieldSplitter,
Denormaliser, RegexEval, AnalyticQuery, AddSequence."""
from __future__ import annotations

import logging
from xml.etree.ElementTree import Element, SubElement

from app.services.ktr_builder.common import _sub, _yn

logger = logging.getLogger(__name__)


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
    # SortRowsMeta.readData() lee "directory" y "free_memory" (no
    # "sort_path"/"free_memory_treshold") — con esos nombres, directory
    # quedaba null (falla solo si el sort excede memoria y vuelca a disco).
    _sub(el, "directory",              "%%java.io.tmpdir%%")
    _sub(el, "prefix",                 "sort")
    _sub(el, "sort_size",              "1000000")
    _sub(el, "free_memory",            "25")
    _sub(el, "compress",               "N")
    _sub(el, "compress_variable")
    _sub(el, "unique_rows",            "N")
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", cfg.get("sort_fields", [])):
        field = SubElement(fe, "field")
        if isinstance(f, dict):
            name = f.get("name") or f.get("field") or f.get("column") or ""
            asc  = _yn(f.get("ascending"), default=True)
        else:
            name = str(f)
            asc  = "Y"
        _sub(field, "name",           name)
        _sub(field, "ascending",      asc)
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


def _step_Unique(el: Element, cfg: dict) -> None:
    _sub(el, "error_description")
    _sub(el, "redirect_rows", "N")
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",           f if isinstance(f, str) else f.get("name", ""))
        _sub(field, "case_sensitive", "N")


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
        # StringOperationsMeta.readData() lee "mask_xml" (minúscula) y "digits"
        # (no "mask_XML"/"digits_only") con valores enum string, no Y/N ni
        # índices: maskXMLCode = {none,escapexml,cdata,unescapexml,escapesql,
        # escapehtml,unescapehtml}; digitsCode = {none,digits_only,remove_digits}.
        _sub(field, "mask_xml",                "none")
        _sub(field, "digits",                  "none")
        _sub(field, "remove_special_characters","N")


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


def _step_IfNull(el: Element, cfg: dict) -> None:
    fields = cfg.get("fields", [])
    _sub(el, "selectFields",     "Y" if fields else "N")
    _sub(el, "selectValuesType")
    fe = SubElement(el, "fields")
    for f in fields:
        # IfNullMeta.loadXML() busca nodos <field> (singular) dentro de <fields>;
        # con tag "fields" repetido acá, Kettle contaba 0 matches y cargaba el
        # step vacío aunque el config trajera datos.
        field = SubElement(fe, "field")
        _sub(field, "name",  f.get("name", ""))
        _sub(field, "type",  f.get("type", ""))
        _sub(field, "value", str(f.get("replace_value", "")))
        _sub(field, "mask",  f.get("mask", ""))


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
