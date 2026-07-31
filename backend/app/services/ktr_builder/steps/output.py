"""Builders de steps de salida: TableOutput, InsertUpdate, Update, Delete,
TextFileOutput, ExcelOutput, JsonOutput."""
from __future__ import annotations

import logging
from xml.etree.ElementTree import Element, SubElement

from app.services.ktr_builder.common import _sub, _yn

logger = logging.getLogger(__name__)


def _step_TableOutput(el: Element, cfg: dict) -> None:
    table = cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or ""
    fields = cfg.get("fields", [])
    _sub(el, "connection",     cfg.get("connection", ""))
    _sub(el, "schema",         cfg.get("schema", ""))
    _sub(el, "table",          table)
    _sub(el, "commit",         str(cfg.get("commit", 1000)))
    truncate      = _yn(cfg.get("truncate"), default=False)
    ignore_errors = _yn(cfg.get("ignore_errors"), default=False)
    use_batch     = _yn(cfg.get("use_batch"), default=True)
    if ignore_errors == "Y" and use_batch == "Y":
        # PDI: ignore_errors=Y es incompatible con batch inserts (el batch se
        # descarta entero ante un error de fila, así que "ignorar errores" no
        # tiene efecto con batching activo). Forzar use_batch=N en vez de
        # apagar ignore_errors en silencio, que es lo que el modelo pidió.
        logger.warning(
            "TableOutput: ignore_errors=Y con use_batch=Y es incompatible en PDI, forzando use_batch=N"
        )
        use_batch = "N"
    _sub(el, "truncate",       truncate)
    _sub(el, "ignore_errors",  ignore_errors)
    _sub(el, "use_batch",      use_batch)
    _sub(el, "specify_fields", _yn(cfg.get("specify_fields"), default=bool(fields)))
    fe = SubElement(el, "fields")
    for f in fields:
        field = SubElement(fe, "field")
        _sub(field, "column_name", f.get("column_name", f.get("dest", "")))
        _sub(field, "stream_name", f.get("stream_name", f.get("source", "")))


def _step_InsertUpdate(el: Element, cfg: dict) -> None:
    table = cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or ""
    fields = cfg.get("fields", [])
    has_updatable_value = any(f.get("update", True) for f in fields)
    _sub(el, "connection", cfg.get("connection", ""))
    _sub(el, "commit",     "100")
    # R-K7 (docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md,
    # D51): InsertUpdateMeta.readData() hace
    # "Y".equalsIgnoreCase(getTagValue(stepnode, "update_bypassed")) -- tag
    # AUSENTE equivale a "N". Antes de esto el tag no se emitía NUNCA, así que
    # cualquier InsertUpdate con todos sus <value> en update="N" caía siempre
    # en el modo peligroso: prepareUpdate() arma un "UPDATE t SET ... WHERE
    # ..." con SET vacío y explota en la primera fila. Default seguro: bypass
    # automático (Y) cuando no hay ningún <value> updatable, salvo que cfg lo
    # declare explícito (ver validators/insert_update_bypass.py para el
    # chequeo de la combinación contradictoria explícita).
    update_bypassed = cfg.get("update_bypassed")
    if update_bypassed is None:
        update_bypassed = not has_updatable_value
    _sub(el, "update_bypassed", _yn(update_bypassed, default=not has_updatable_value))
    # InsertUpdateMeta.readData() lee schema/table anidados en <lookup>
    # (getTagValue(stepnode, "lookup", "schema"/"table")), no como hijos
    # directos del step — si van sueltos, tableName queda null.
    lookup = SubElement(el, "lookup")
    _sub(lookup, "schema", cfg.get("schema", ""))
    _sub(lookup, "table",  table)
    for k in cfg.get("keys", []):
        ke = SubElement(lookup, "key")
        _sub(ke, "name",      k.get("stream_field", k.get("name", "")))
        _sub(ke, "field",     k.get("table_field",  k.get("field", "")))
        _sub(ke, "condition", "=")
        _sub(ke, "name2")
    for f in cfg.get("fields", []):
        ve = SubElement(lookup, "value")
        # InsertUpdateMeta.getXML()/readData() (pentaho-kettle): <name> es la
        # columna de la tabla (updateLookup), <rename> es el campo del stream
        # (updateStream) -- invertido de <key>, donde <name> SÍ es el stream.
        # Antes acá iba al revés (name=stream_field, rename=table_field): todo
        # InsertUpdate emitido escribía en una "columna" con nombre de campo de
        # stream, que no existe en la tabla real.
        _sub(ve, "name",   f.get("table_field",  f.get("rename", "")))
        _sub(ve, "rename", f.get("stream_field", f.get("name", "")))
        _sub(ve, "update", "Y" if f.get("update", True) else "N")


def _step_Update(el: Element, cfg: dict) -> None:
    table = cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or ""
    _sub(el, "connection",             cfg.get("connection", ""))
    _sub(el, "commit",                 "100")
    _sub(el, "use_batch",              "Y")
    # UpdateMeta.readData() lee "error_ignored" (no "ignore_lookup_failure")
    # y schema/table anidados en <lookup>, igual que InsertUpdate.
    _sub(el, "error_ignored",          "N")
    lookup = SubElement(el, "lookup")
    _sub(lookup, "schema", cfg.get("schema", ""))
    _sub(lookup, "table",  table)
    for k in cfg.get("keys", []):
        ke = SubElement(lookup, "key")
        _sub(ke, "name",      k.get("stream_field", k.get("name", "")))
        _sub(ke, "field",     k.get("table_field",  k.get("field", "")))
        _sub(ke, "condition", "=")
        _sub(ke, "name2")
    for f in cfg.get("fields", []):
        ve = SubElement(lookup, "value")
        # Mismo layout que InsertUpdate (UpdateMeta.getXML() usa el mismo
        # readData de <value>) -- ver comentario en _step_InsertUpdate.
        _sub(ve, "name",   f.get("table_field",  f.get("rename", "")))
        _sub(ve, "rename", f.get("stream_field", f.get("name", "")))


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
