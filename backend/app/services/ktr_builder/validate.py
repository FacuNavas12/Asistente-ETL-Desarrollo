"""Validación pre-serialización del ktr JSON (estructura de steps/hops), previo
a construir el XML. Ver ktr_xml_validator.py para la validación post-XML."""
from __future__ import annotations

from app.services.ktr_builder.registry import STEP_TYPE_ALIASES


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
