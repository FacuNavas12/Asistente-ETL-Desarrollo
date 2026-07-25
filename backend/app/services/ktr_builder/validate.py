"""Validación pre-serialización del ktr JSON (estructura de steps/hops), previo
a construir el XML. Ver ktr_xml_validator.py para la validación post-XML."""
from __future__ import annotations

import difflib
import re

from app.services.ktr_builder.contracts import parse_cfg as _parse_cfg
from app.services.ktr_builder.registry import STEP_TYPE_ALIASES


def _select_column_names(sql: str) -> list[str]:
    """Nombres de columna de un SELECT simple, EN ORDEN y sin deduplicar (a
    diferencia de fields_validate._select_columns) — acá interesa detectar
    duplicados, no calcular el set de campos disponibles. [] si no se puede
    parsear con certeza (SELECT *, expresión no reconocida)."""
    if not sql or not sql.strip():
        return []
    m = re.search(r"select\s+(.*?)\s+from\s", sql, re.IGNORECASE | re.DOTALL)
    if not m or "*" in m.group(1):
        return []
    parts, current, depth = [], "", 0
    for ch in m.group(1):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)

    names = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        alias_match = re.search(r"\bas\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", p, re.IGNORECASE)
        token = alias_match.group(1) if alias_match else (p.split()[-1] if " " in p else p)
        token = token.split(".")[-1].strip('`"[]')
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", token):
            names.append(token.lower())
    return names


def _validate_ktr(ktr: dict) -> list[str]:
    warnings = []
    step_names = {s.get("name") for s in ktr.get("steps", [])}
    # Normalizar tipos usando los aliases, así reconocemos tanto "Table Input" como "TableInput"
    types = {STEP_TYPE_ALIASES.get(s.get("type", ""), s.get("type", "")) for s in ktr.get("steps", [])}

    input_types  = {"TableInput", "CsvInput", "ExcelInput", "TextFileInput", "JsonInput", "DataGrid", "RowGenerator"}
    output_types = {"TableOutput", "InsertUpdate", "Update", "Delete"}

    if not input_types & types:
        warnings.append("KTR no tiene ningún step de entrada (TableInput, etc.)")
    if not output_types & types:
        warnings.append("KTR no tiene ningún step de salida (TableOutput, InsertUpdate, etc.)")

    for hop in ktr.get("hops", []):
        for endpoint in ("from", "to"):
            val = hop.get(endpoint)
            if val in step_names:
                continue
            matches = difflib.get_close_matches(val, step_names, n=1, cutoff=0.6)
            if matches:
                warnings.append(
                    f"Hop hace referencia a step inexistente: '{val}' — "
                    f"autocorregido a '{matches[0]}' (nombre más parecido en la lista de steps)."
                )
                hop[endpoint] = matches[0]
            else:
                warnings.append(f"Hop hace referencia a step inexistente: '{val}'")

    for step in ktr.get("steps", []):
        canonical = STEP_TYPE_ALIASES.get(step.get("type", ""), step.get("type", ""))
        if canonical != "TableInput":
            continue
        cfg = _parse_cfg(step.get("config", {}))
        names = _select_column_names(cfg.get("sql", ""))
        seen, dupes = set(), []
        for n in names:
            if n in seen and n not in dupes:
                dupes.append(n)
            seen.add(n)
        for d in dupes:
            warnings.append(
                f"TableInput '{step.get('name')}': columna '{d}' repetida en el SELECT — "
                "Kettle expone ambas con el mismo nombre y solo una llega aguas abajo."
            )

    # Detectar Calculator con cálculos que referencian field_name de otro cálculo
    # del mismo step — Kettle no encadena dentro del mismo step y falla en runtime.
    for step in ktr.get("steps", []):
        canonical = STEP_TYPE_ALIASES.get(step.get("type", ""), step.get("type", ""))
        if canonical not in ("Calculator", "Formula"):
            continue
        cfg = _parse_cfg(step.get("config", {}))
        calcs = cfg.get("calculations", cfg.get("formulas", []))
        produced: set[str] = set()
        for i, calc in enumerate(calcs):
            field_name = calc.get("field_name", "")
            for arg in ("field_a", "field_b", "field_c"):
                ref = calc.get(arg, "")
                if ref and ref in produced:
                    warnings.append(
                        f"{canonical} '{step.get('name')}': cálculo #{i + 1} "
                        f"('{field_name}') usa '{ref}' en '{arg}', pero '{ref}' es el "
                        f"resultado de un cálculo anterior del mismo step — "
                        "Calculator no encadena sus propios cálculos. "
                        "Separar en dos steps Calculator conectados por un hop."
                    )
            if field_name:
                produced.add(field_name)

    return warnings
