"""
Registro central de step types soportados por el KTR builder:

  STEP_TYPE_ALIASES   — nombres "display" de Spoon (con espacios) o internos
                         alternativos -> nombre canónico usado por STEP_BUILDERS.
  STEP_BUILDERS        — nombre canónico -> función que serializa <step><...></step>.
  KNOWN_PDI_STEP_TYPES — whitelist de todo `type` que build_ktr() acepta emitir tal
                         cual; cualquier otro valor se fuerza a Dummy (ver build.py).
  _CRITICAL_FIELDS     — campos de config sin los cuales el step no tiene sentido
                         funcional (usado por build.py solo para logging de diagnóstico,
                         no bloquea el build).

Mantener este archivo como ÚNICO lugar donde se ensamblan estos tres mapeos —
agregar un step nuevo implica: escribir el builder en steps/<familia>.py,
importarlo acá y sumarlo a STEP_BUILDERS (+ alias si aplica).
"""
from __future__ import annotations

from app.services.ktr_builder.steps.input import (
    _step_CsvInput,
    _step_ExcelInput,
    _step_JsonInput,
    _step_RowGenerator,
    _step_TableInput,
    _step_TextFileInput,
)
from app.services.ktr_builder.steps.output import (
    _step_Delete,
    _step_ExcelOutput,
    _step_InsertUpdate,
    _step_JsonOutput,
    _step_TableOutput,
    _step_TextFileOutput,
    _step_Update,
)
from app.services.ktr_builder.steps.lookups import (
    _step_CombinationLookup,
    _step_DBLookup,
    _step_DimensionLookup,
    _step_JoinRows,
    _step_MergeJoin,
    _step_MergeRows,
    _step_StreamLookup,
)
from app.services.ktr_builder.steps.transform import (
    _step_AddSequence,
    _step_AnalyticQuery,
    _step_Calculator,
    _step_ConcatFields,
    _step_Constant,
    _step_Denormaliser,
    _step_FieldSplitter,
    _step_FilterRows,
    _step_Formula,
    _step_GroupBy,
    _step_IfNull,
    _step_NumberRange,
    _step_RegexEval,
    _step_ReplaceString,
    _step_SelectValues,
    _step_SortRows,
    _step_SplitFieldToRows,
    _step_StringOperations,
    _step_Unique,
    _step_ValueMapper,
)
from app.services.ktr_builder.steps.control import (
    _step_Abort,
    _step_BlockingStep,
    _step_DataValidator,
    _step_Dummy,
    _step_ExecSQL,
    _step_GetSystemInfo,
    _step_GetVariable,
    _step_ScriptValueMod,
    _step_SetVariable,
    _step_WriteToLog,
)


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
    "Generate Rows":             "RowGenerator",
    "Row Generator":             "RowGenerator",
    "GenerateRows":              "RowGenerator",
    "XML input stream (SAX)":    "GetXMLData",
    "REST Client":               "Rest",
    # Transformación
    "Select values":             "SelectValues",
    "Filter rows":                "FilterRows",
    "Sort rows":                  "SortRows",
    "Group by":                   "GroupBy",
    "Memory Group by":            "MemoryGroupBy",
    "Unique rows":                "Unique",
    "Unique rows (HashSet)":      "UniqueRowsByHashSet",
    "Calculator":                 "Calculator",
    "String operations":          "StringOperations",
    "Replace in string":          "ReplaceString",
    "Concat fields":              "ConcatFields",
    "Split fields":               "SplitFieldToRows",
    "Value mapper":               "ValueMapper",
    "Null if...":                 "IfNull",
    "If field value is null":     "IfNull",
    "Add constants":              "Constant",
    "AddConstants":               "Constant",
    "Number range":               "NumberRange",
    "Regex evaluation":           "RegexEval",
    "Row Normaliser":             "Normaliser",
    "Row denormaliser":           "Denormaliser",
    # Joins / lookups
    "Database lookup":            "DBLookup",
    "Database Lookup":            "DBLookup",
    "DatabaseLookup":             "DBLookup",
    "Stream lookup":               "StreamLookup",
    "Merge rows (diff)":           "MergeRows",
    "Merge join":                  "MergeJoin",
    "Merge Join":                  "MergeJoin",
    # Salida
    "Table Output":               "TableOutput",
    "Insert / Update":            "InsertUpdate",
    "Update":                     "Update",
    "Delete":                     "Delete",
    "Microsoft Excel Writer":     "MicrosoftExcelWriter",
    "Text file output":           "TextFileOutput",
    "JSON output":                "JsonOutput",
    # Dimensiones / DWH
    "Dimension lookup/update":    "DimensionLookup",
    "Combination lookup/update":  "CombinationLookup",
    # Calidad / logging
    "Field meta data validation": "FieldMetaDataValidation",
    "Data validator":             "DataValidator",
    "Write to log":               "WriteToLog",
    # Control de flujo
    "Mapping (sub-transformation)": "Mapping",
    "Transformation executor":    "TransExecutor",
    "Get System Info":            "GetSystemInfo",
    "SystemInfo":                  "GetSystemInfo",
}


STEP_BUILDERS = {
    # Entrada
    "TableInput":          _step_TableInput,
    "CsvInput":            _step_CsvInput,
    "TextFileInput":       _step_TextFileInput,
    "ExcelInput":          _step_ExcelInput,
    "JsonInput":           _step_JsonInput,
    "RowGenerator":        _step_RowGenerator,
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


# Campos críticos por tipo de step: sin ellos el step no cumple su función
# aunque el XML sea válido. build.py aborta el build si alguno falta.
_CRITICAL_FIELDS: dict[str, list[str]] = {
    "TableInput":        ["sql"],
    "WriteToLog":        ["message"],
    "GroupBy":           ["group_fields"],
    "MemoryGroupBy":     ["group_fields"],
    "SortRows":          ["fields"],
    "Constant":          ["fields"],
    "GetSystemInfo":     ["fields"],
    "TableOutput":       ["table"],
    "InsertUpdate":      ["table"],
    "Update":            ["table"],
    "Delete":            ["table"],
    # "return_field" es la clave canónica post-normalize_config() (ver
    # contracts.py) — returnfield/sk_field/surrogate_key son alias que ya
    # se resolvieron a esta antes de llegar acá.
    "DimensionLookup":   ["table", "return_field"],
    "CombinationLookup": ["table", "return_field"],
    "DBLookup":          ["table"],
    "MergeRows":         ["step1", "step2"],
    "MergeJoin":         ["step1", "step2"],
    "ValueMapper":       ["field_to_use"],
}


# ─── Fidelidad de config: claves reconocidas por emisor ───────────────────────
# Todas las claves de config (incluidos los alias que cada builder acepta del
# LLM) que ese step SÍ mapea a XML. build.py resta este set de las claves
# presentes en el config real y loguea WARN por cada sobrante — así una clave
# que el modelo declaró pero que el builder ignora (el bug de ignore_errors en
# TableOutput, p. ej.) deja rastro en vez de perderse en silencio. Un type
# ausente de este dict no se audita (todavía no relevado) — no genera falsos
# positivos.
STEP_CONFIG_KEYS: dict[str, frozenset[str]] = {
    "WriteToLog":      frozenset({"level", "message", "fields"}),
    "Constant":        frozenset({"fields"}),
    "RowGenerator":    frozenset({"fields", "limit"}),
    "GetSystemInfo":   frozenset({"fields"}),
    "TableInput":      frozenset({"connection", "sql"}),
    "SelectValues":    frozenset({"select", "fields", "columns", "remove", "cast"}),
    "TableOutput":     frozenset({
        "table", "target_table", "table_name", "connection", "schema",
        "truncate", "ignore_errors", "specify_fields", "use_batch",
        "fields", "commit",
    }),
    "SortRows":        frozenset({"fields", "sort_fields"}),
    "Unique":          frozenset({"fields"}),
    "DimensionLookup": frozenset({
        "table", "target_table", "table_name", "return_field", "returnfield",
        "sk_field", "surrogate_key", "schema", "connection", "keys", "fields",
        "date_field", "date_from", "date_to",
    }),
    "DBLookup":        frozenset({
        "table", "target_table", "table_name", "connection", "schema",
        "keys", "return_fields", "returns",
    }),
    "Formula":         frozenset({"formulas", "fields"}),
    "Calculator":      frozenset({"calculations"}),
    "InsertUpdate":    frozenset({
        "table", "target_table", "table_name", "schema", "connection",
        "keys", "fields", "commit",
    }),
    "GroupBy":         frozenset({"group_fields", "aggregates"}),
    "NumberRange":     frozenset({"input_field", "output_field", "fallback", "ranges"}),
    "IfNull":          frozenset({"fields"}),
    "StreamLookup":    frozenset({"step", "from", "keys", "values", "fields"}),
}
# MemoryGroupBy comparte builder y config con GroupBy (ver STEP_BUILDERS).
STEP_CONFIG_KEYS["MemoryGroupBy"] = STEP_CONFIG_KEYS["GroupBy"]


def unmapped_config_keys(canonical_type: str, cfg: dict) -> list[str]:
    """Claves de cfg que ese step no reconoce, según STEP_CONFIG_KEYS. Lista
    vacía si el type no está relevado (no auditado) o si no hay sobrantes."""
    known = STEP_CONFIG_KEYS.get(canonical_type)
    if known is None or not isinstance(cfg, dict):
        return []
    return [k for k in cfg.keys() if k not in known]
