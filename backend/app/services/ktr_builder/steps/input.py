"""Builders de steps de entrada: TableInput, CsvInput, TextFileInput, ExcelInput, JsonInput."""
from __future__ import annotations

import logging
from xml.etree.ElementTree import Element, SubElement

from app.services.ktr_builder.xml_helpers import _sub

logger = logging.getLogger(__name__)


def _step_RowGenerator(el: Element, cfg: dict) -> None:
    """Generate Rows — única forma de sembrar filas SIN depender de ningún step
    aguas arriba (a diferencia de Constant/GetVariable, que necesitan una fila
    de entrada para poder agregarle campos). Usar con limit=1 + un hop hacia
    Add constants para materializar parámetros/literales de negocio (factores,
    umbrales) que no vienen de ninguna tabla — nunca encadenar esos steps
    detrás de un WriteToLog: WriteToLog no genera filas, solo loggea las que
    ya recibió, y como primer step del flujo no recibe ninguna."""
    _sub(el, "limit", str(cfg.get("limit", 1)))
    fe = SubElement(el, "fields")
    for f in cfg.get("fields", []):
        field = SubElement(fe, "field")
        _sub(field, "name",      f.get("name", ""))
        _sub(field, "type",      f.get("type", "String"))
        _sub(field, "format",    f.get("format", ""))
        _sub(field, "currency")
        _sub(field, "decimal")
        _sub(field, "group")
        _sub(field, "nullif",    str(f.get("value", "")))
        _sub(field, "length",    str(f.get("length", -1)))
        _sub(field, "precision", str(f.get("precision", -1)))
        _sub(field, "set_empty_string", "N")


def _step_TableInput(el: Element, cfg: dict) -> None:
    _sub(el, "connection",             cfg.get("connection", ""))
    _sub(el, "sql",                    cfg.get("sql", "SELECT 1"))
    _sub(el, "limit",                  "0")
    _sub(el, "lookup")
    _sub(el, "execute_each_row",       "N")
    _sub(el, "variables_active",       "N")
    _sub(el, "lazy_conversion_active", "N")


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
    # ExcelInputMeta.readData(): SpreadSheetType.valueOf(getTagValue(...)) --
    # tag ausente o no-parseable cae, en un catch, a SpreadSheetType.JXL (motor
    # legado que no lee .xlsx). El emisor nunca lo escribía, así que todo
    # ExcelInput caía siempre a JXL sin importar el archivo real
    # (docs/refactor/investigacion-tags-validos-por-step.md § A.6). Valores
    # reales del enum: JXL, POI, SAX_POI, ODS (SpreadSheetType.java). Por
    # extensión: .xls -> JXL (el motor que sí lo lee), cualquier otro caso
    # (.xlsx/.xlsm/sin extensión) -> POI, que sí lee Excel 2007+.
    spreadsheet_type = str(cfg.get("spreadsheet_type", "")).strip().upper()
    if spreadsheet_type not in ("JXL", "POI", "SAX_POI", "ODS"):
        spreadsheet_type = "JXL" if filename.lower().endswith(".xls") else "POI"
    _sub(el, "spreadsheet_type", spreadsheet_type)

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
    # JsonInputMeta.getincludeNulls(): si el tag <includeNulls> está ausente,
    # cae a getIncludeNullsProperty() -- lee kettle.properties del entorno que
    # ejecuta Spoon (KETTLE_JSON_INPUT_INCLUDE_NULLS, default "N"). El emisor
    # nunca lo escribía: el mismo .ktr se comportaba distinto según la máquina
    # (docs/refactor/investigacion-tags-validos-por-step.md § A.7). Escribirlo
    # siempre explícito saca la ambigüedad del entorno.
    _sub(el, "includeNulls",         "Y" if cfg.get("include_nulls", False) else "N")

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
