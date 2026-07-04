"""
Validador post-generación del .ktr — red de seguridad general (no depende de
nombres de tabla/columna de ningún caso puntual).

Causa raíz confirmada: un step Constant (Add constants) puede setear un campo
Date/Timestamp con el texto de una función SQL (ej. "NOW()") como si fuera un
valor literal. Pentaho intenta parsear ese string como fecha y falla
("Couldn't parse Timestamp ... value [NOW()]"), y el step no inicializa.

Este módulo actúa DESPUÉS de que el modelo generó el ktr JSON, sin importar si
el prompt logró evitar el problema en origen (ver system_etl.txt) — es la
última barrera antes de serializar el XML.

Dos chequeos, ambos derivables solo de la estructura del ktr (+ opcionalmente
la lista de columnas NOT-NULL-sin-default provista por el caller a partir del
DDL, para el segundo chequeo):

  1. scrub_function_default_constants — quita de los steps Constant cualquier
     campo Date/Timestamp cuyo valor sea una función/expresión SQL, y limpia
     las referencias a ese campo en los mapeos de salida (TableOutput,
     InsertUpdate, Update, DimensionLookup, CombinationLookup) para que el
     grafo quede consistente. La BD destino aplica su propio DEFAULT.

  2. check_missing_required_fields — con la lista de columnas NOT NULL sin
     default (informada por el caller), reporta (no repara — no hay valor que
     inventar) cualquier tabla destino a la que le falte el mapeo de una de
     esas columnas.
"""
from __future__ import annotations

import json
import logging

from app.services.sql_defaults import looks_like_sql_function

logger = logging.getLogger(__name__)

_DATE_TIME_TYPES = frozenset({"date", "timestamp"})

# Steps cuyo config trae una lista "fields" con mapeo columna-destino <- campo-stream.
# Se listan las claves candidatas (en orden de preferencia) que identifican el
# nombre del campo del STREAM en cada tipo de step — es la punta que puede
# quedar colgando cuando se elimina un campo en el Constant que lo originó.
_STREAM_FIELD_KEYS: dict[str, tuple[str, ...]] = {
    "TableOutput":       ("stream_name", "source"),
    "InsertUpdate":      ("stream_field", "name"),
    "Update":            ("stream_field", "name"),
    "DimensionLookup":   ("stream", "stream_field", "name"),
    "CombinationLookup": ("stream", "name"),
}

# Mismas claves, pero del lado de la columna DESTINO — usadas por
# check_missing_required_fields para saber qué columnas ya están cubiertas.
_TABLE_FIELD_KEYS: dict[str, tuple[str, ...]] = {
    "TableOutput":       ("column_name", "dest"),
    "InsertUpdate":      ("table_field", "field"),
    "Update":            ("table_field", "field"),
    "DimensionLookup":   ("lookup", "table_field"),
    "CombinationLookup": ("lookup", "table_field"),
}


def _parse_cfg(raw) -> dict:
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    return raw or {}


def scrub_function_default_constants(ktr_data: dict, step_type_aliases: dict[str, str]) -> list[str]:
    """Elimina de los steps Constant cualquier campo Date/Timestamp cuyo valor
    sea una función/expresión SQL, y limpia los mapeos que lo referenciaban.
    Devuelve la lista de warnings (vacía si no hubo nada que corregir)."""
    warnings: list[str] = []
    steps = ktr_data.get("steps", [])

    dropped: set[str] = set()
    for step in steps:
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        if canonical != "Constant":
            continue
        cfg = _parse_cfg(step.get("config", {}))
        fields = cfg.get("fields", [])
        if not fields:
            continue
        kept = []
        for f in fields:
            ftype = str(f.get("type", "")).strip().lower()
            value = f.get("value")
            if ftype in _DATE_TIME_TYPES and looks_like_sql_function(str(value) if value is not None else ""):
                name = f.get("name", "")
                dropped.add(name)
                warnings.append(
                    f"Step '{step.get('name')}': campo '{name}' (tipo {f.get('type')}) tenía "
                    f"'{value}' como constante — es una función/expresión SQL, no un literal. "
                    "Se omitió el campo para que la BD destino aplique su propio DEFAULT."
                )
                continue
            kept.append(f)
        if len(kept) != len(fields):
            cfg["fields"] = kept
            step["config"] = cfg

    if not dropped:
        return warnings

    for step in steps:
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        source_keys = _STREAM_FIELD_KEYS.get(canonical)
        if source_keys is None:
            continue
        cfg = _parse_cfg(step.get("config", {}))
        fields = cfg.get("fields", [])
        if not fields:
            continue

        def _source_name(f: dict) -> str | None:
            for k in source_keys:
                if f.get(k):
                    return f[k]
            return None

        new_fields = [f for f in fields if _source_name(f) not in dropped]
        if len(new_fields) != len(fields):
            cfg["fields"] = new_fields
            step["config"] = cfg
            warnings.append(
                f"Step '{step.get('name')}': se quitó el mapeo de columna(s) con default de "
                "función ya omitidas aguas arriba — la BD las completa por su cuenta."
            )

    return warnings


def check_missing_required_fields(
    ktr_data: dict,
    step_type_aliases: dict[str, str],
    required_columns_by_table: dict[str, list[str]] | None,
) -> list[str]:
    """required_columns_by_table: {nombre_tabla: [columnas NOT NULL sin default]},
    derivado por el caller a partir del DDL (ver etl_generator). None o {} => no-op.
    Solo reporta — no hay valor que el validador pueda inventar para una columna
    obligatoria sin origen declarado."""
    if not required_columns_by_table:
        return []

    warnings: list[str] = []
    lookup = {**required_columns_by_table, **{k.lower(): v for k, v in required_columns_by_table.items()}}

    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        field_keys = _TABLE_FIELD_KEYS.get(canonical)
        if field_keys is None:
            continue
        cfg = _parse_cfg(step.get("config", {}))
        table = (cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or "").strip()
        if not table:
            continue
        required = lookup.get(table) or lookup.get(table.lower())
        if not required:
            continue

        mapped: set[str] = set()
        for f in cfg.get("fields", []):
            for k in field_keys:
                if f.get(k):
                    mapped.add(f[k])
                    break

        for col in required:
            if col not in mapped:
                warnings.append(
                    f"Tabla '{table}' (step '{step.get('name')}'): columna NOT NULL sin default "
                    f"'{col}' no tiene mapeo de origen en este step — el ETL debe proveerla."
                )

    return warnings
