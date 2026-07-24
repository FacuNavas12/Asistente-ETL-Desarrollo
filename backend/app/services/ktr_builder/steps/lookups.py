"""Builders de joins/lookups: DBLookup, StreamLookup, DimensionLookup,
CombinationLookup, MergeJoin, MergeRows, JoinRows."""
from __future__ import annotations

import logging
from xml.etree.ElementTree import Element, SubElement

from app.services.ktr_builder.common import _sub

logger = logging.getLogger(__name__)


def _step_MergeJoin(el: Element, cfg: dict) -> None:
    # Kettle acepta INNER / LEFT OUTER / RIGHT OUTER / FULL OUTER — sin " JOIN" al final.
    # El LLM suele generar "INNER JOIN" / "LEFT OUTER JOIN"; los normalizamos acá.
    jt_map = {
        "INNER": "INNER", "LEFT": "LEFT OUTER",
        "RIGHT": "RIGHT OUTER", "FULL": "FULL OUTER",
        "INNER JOIN": "INNER", "LEFT OUTER JOIN": "LEFT OUTER",
        "RIGHT OUTER JOIN": "RIGHT OUTER", "FULL OUTER JOIN": "FULL OUTER",
        "LEFT OUTER": "LEFT OUTER", "RIGHT OUTER": "RIGHT OUTER", "FULL OUTER": "FULL OUTER",
    }
    _sub(el, "join_type", jt_map.get(str(cfg.get("join_type", "INNER")).upper(), "INNER"))
    _sub(el, "step1",     cfg.get("step1", ""))
    _sub(el, "step2",     cfg.get("step2", ""))
    k1 = SubElement(el, "keys_1")
    for k in cfg.get("keys1", []):
        _sub(k1, "key", k if isinstance(k, str) else k.get("name", ""))
    k2 = SubElement(el, "keys_2")
    for k in cfg.get("keys2", []):
        _sub(k2, "key", k if isinstance(k, str) else k.get("name", ""))


def _step_DimensionLookup(el: Element, cfg: dict) -> None:
    logger.warning("### DIMLOOKUP_MARKER — cfg recibido: %s ###", cfg)
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
    # D16: update=N cuando dimension_step_policy clasificó este step como
    # lookup de FK del lado del hecho (solo lectura) — ver Paso 4 en
    # dimension_step_policy.py. Default "Y" preserva el comportamiento
    # anterior para cualquier caller que no pase por esa política.
    _sub(el, "update",                    "Y" if str(cfg.get("update", "Y")).strip().upper() != "N" else "N")
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
    # DimensionLookupMeta espera <date><name>/<from>/<to></date> (readData L920-923).
    # "name" = campo stream con la fecha de referencia; vacío = usa fecha de
    # sistema (comportamiento válido de Kettle, "No datefield: use system date").
    # "from"/"to" = columnas de la tabla dimensión para el rango de vigencia SCD2.
    date_el = SubElement(fe, "date")
    _sub(date_el, "name", cfg.get("date_field", ""))
    _sub(date_el, "from", cfg.get("date_from", "fecha_desde"))
    _sub(date_el, "to",   cfg.get("date_to",   "fecha_hasta"))
    # Bloque <return> obligatorio para PDI — identifica el surrogate key generado
    ret_el = SubElement(fe, "return")
    _sub(ret_el, "name",            return_field)
    _sub(ret_el, "rename",          return_field)
    _sub(ret_el, "creation_method", "autoinc")
    _sub(ret_el, "use_autoinc",     "Y")
    _sub(ret_el, "version",         cfg.get("version_field", "version"))


def _step_DBLookup(el: Element, cfg: dict) -> None:
    table = cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or ""
    if not table:
        logger.warning("DBLookup: 'table' vacío — PDI fallará buscando campo en tabla null")
    _sub(el, "connection", cfg.get("connection", ""))
    _sub(el, "cache", "N")
    _sub(el, "cache_load_all", "N")
    _sub(el, "cache_size", "9999")
    # DatabaseLookupMeta.loadXML() espera schema/table/orderby/fail_on_multiple/
    # eat_row_on_failure y los bloques key/value ANIDADOS dentro de <lookup> —
    # si van sueltos como hijos directos del <step>, Kettle los interpreta como
    # step sin configurar (table=null) y falla en runtime con
    # "SELECT * FROM null" al ejecutar la transformación.
    lookup = SubElement(el, "lookup")
    _sub(lookup, "schema",     cfg.get("schema", ""))
    _sub(lookup, "table",      table)
    _sub(lookup, "orderby")
    _sub(lookup, "fail_on_multiple", "N")
    _sub(lookup, "eat_row_on_failure", "N")
    for k in cfg.get("keys", []):
        ke = SubElement(lookup, "key")
        _sub(ke, "name",      k.get("stream_field") or k.get("name", ""))
        _sub(ke, "field",     k.get("lookup_field") or k.get("table_field") or k.get("field", ""))
        _sub(ke, "condition", k.get("condition", "="))
        _sub(ke, "name2",     k.get("stream_field2") or k.get("name2", ""))
    for r in cfg.get("return_fields", cfg.get("returns", [])):
        ret = SubElement(lookup, "value")
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
