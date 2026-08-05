"""
Vocabulario de tipos de step PDI — dominio puro, cero conocimiento de cómo se
serializan a XML (eso es step_emitters.py).

  STEP_TYPE_ALIASES — nombres "display" de Spoon (con espacios) o internos
                       alternativos -> nombre canónico. Identidad: qué nombres
                       distintos se refieren al mismo step.
  _CRITICAL_FIELDS   — campos de config sin los cuales el step no tiene sentido
                        funcional, aunque el XML resultante sea válido.
                        build.py aborta el build (KtrBuilderError) si alguno
                        falta — no es un chequeo cosmético.

Split de registry.py (sesión de arquitectura): el criterio que separa este
módulo de step_emitters.py es GUIA_TECNICA.md, "vocabulario PDI es dominio" — acá
vive lo que un step ES (identidad, completitud mínima), no cómo se construye
su XML. `KNOWN_PDI_STEP_TYPES` (whitelist derivada de STEP_BUILDERS.keys(),
nunca consultada en runtime — build.py rechaza por STEP_BUILDERS.get() is
None, no por whitelist) se borró en el mismo split: no sobrevivió al split
porque no hacía nada, no porque no encajara en esta capa. La coherencia entre
lo que este módulo declara y lo que system_etl.txt le promete al LLM la cubre
test_pdi_step_coherence.py, no un símbolo acá.
"""
from __future__ import annotations

# ─── Alias map ────────────────────────────────────────────────────────────────
# El modelo a veces devuelve los nombres "display" de Spoon (con espacios) y otras
# veces los nombres "internos" (camelCase). Este mapa normaliza ambos a la forma
# canónica usada por step_emitters.STEP_BUILDERS antes de buscar el emisor.

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
