"""
Emisores XML por tipo de step PDI — infraestructura: traduce el tipo canónico
(step_types.py) al `<step>` XML concreto de Kettle, y audita la fidelidad de
esa traducción.

  STEP_BUILDERS      — nombre canónico -> función que serializa <step><...></step>.
  STEP_CONFIG_KEYS    — claves de config que ese step SÍ mapea a XML (incluidos
                         alias que el builder acepta). build.py resta este set
                         de las claves presentes en el config real y loguea WARN
                         por cada sobrante — clave que el modelo declaró pero
                         el builder ignora deja rastro en vez de perderse en
                         silencio. Es auditoría de CAPACIDAD PRESENTE del
                         builder, no invariante de dominio — por eso vive acá
                         y no en step_types.py (split de registry.py, sesión
                         de arquitectura).
  unmapped_config_keys() — función pública sobre STEP_CONFIG_KEYS.

Mantener este archivo como ÚNICO lugar donde se ensambla STEP_BUILDERS —
agregar un step nuevo implica: escribir el builder en steps/<familia>.py,
importarlo acá y sumarlo a STEP_BUILDERS (+ alias en step_types.STEP_TYPE_ALIASES
si aplica, + entrada en STEP_CONFIG_KEYS si el builder acepta claves que valga
la pena auditar).
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
