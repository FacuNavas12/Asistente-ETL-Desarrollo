"""Fase 2-ter, item 1 (S-4/H45, docs/refactor/03c-investigacion-vocabulario-
dimension-kettle.md): backstop determinista de saneamiento de rango.

Evidencia: dos corridas del mismo caso (Set A/Set B) validaron cada una solo
1 de 3 columnas con CHECK de rango en el DDL destino, y una columna DISTINTA
cada vez — error de completitud sistémico (aparece en los dos modelos), no de
modelo. D43 (commit 6bfd018) ya extrae esos CHECK a
`CanonicalField.constraints.minimum/maximum` — este pass es el checker mínimo
que el plan pide: por cada columna con bound en la tabla DWH que un step
escribe, tiene que existir un `FilterRows` en el mismo KTR sobre el campo de
stream que alimenta esa columna. No hace falta reachability por hops (D6-bis:
mínimo aceptable, no sobre-construir) — presencia en el mismo archivo alcanza
para el caso que motiva esta entrada (steps de una sola etapa, sin ramas
cruzadas todavía materializadas — ver D48).

Cierra también la mitad de A-5 (constante `String` contra columna numérica):
si el FilterRows existe pero su `value_type` es `String` sobre una columna
`integer`/`number`, Kettle compara como texto (orden lexicográfico), no como
número — mismo severity, mensaje distinto."""
from __future__ import annotations

from app.services.ktr_builder.contracts import normalize_config, parse_cfg
from app.services.ktr_builder.validators.base import Finding, ValidationContext

CHECK_FILTER_PREFIX = "[FilterRows de CHECK] "

name = "check_constraint_filter_rows"

_NUMERIC_TYPES = {"integer", "number"}
_BOUND_OPERATORS = {">", ">=", "<", "<="}

# canonical_type -> (dest_col_keys, stream_field_keys), en orden de
# preferencia -- mismo layout que emiten steps/output.py y steps/lookups.py
# (invertido entre sí: TableOutput usa column_name/stream_name,
# InsertUpdate/Update/DimensionLookup usan table_field/stream_field).
_FIELD_KEYS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "TableOutput":      (("column_name", "dest"), ("stream_name", "source")),
    "InsertUpdate":     (("table_field", "rename"), ("stream_field", "name")),
    "Update":           (("table_field", "rename"), ("stream_field", "name")),
    "DimensionLookup":  (("table_field",), ("stream_field", "stream", "name")),
}


def _first(d: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = d.get(k)
        if v:
            return str(v)
    return ""


def _table_bounds(ctx: ValidationContext, table: str) -> dict[str, dict]:
    return ctx.dwh_constraints.get(table.lower().strip(), {})


def check_constraint_filter_rows(ctx: ValidationContext) -> list[Finding]:
    if not ctx.dwh_constraints:
        return []

    findings: list[Finding] = []
    steps = ctx.ktr_data.get("steps", [])

    filter_conditions: list[tuple[str, str, str]] = []  # (step_name, field, value_type)
    for step in steps:
        raw_type = step.get("type", "")
        canonical = ctx.step_type_aliases.get(raw_type, raw_type)
        if canonical != "FilterRows":
            continue
        cfg = parse_cfg(step.get("config", {}))
        field = str(cfg.get("field") or "").strip()
        if not field or str(cfg.get("operator", "")).upper() not in _BOUND_OPERATORS:
            continue
        filter_conditions.append((step.get("name", ""), field, str(cfg.get("value_type", "String"))))

    for step in steps:
        raw_type = step.get("type", "")
        canonical = ctx.step_type_aliases.get(raw_type, raw_type)
        field_keys = _FIELD_KEYS.get(canonical)
        if field_keys is None:
            continue
        if canonical == "DimensionLookup" and str(step.get("config", {}).get("update", "Y")).strip().upper() == "N":
            continue  # fact_lookup (solo lectura) no escribe la tabla — D16/D44
        step_name = step.get("name", "")
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        table = str(cfg.get("table") or "").strip()
        bounds = _table_bounds(ctx, table)
        if not bounds:
            continue

        dest_keys, stream_keys = field_keys
        for f in cfg.get("fields", []):
            if not isinstance(f, dict):
                continue
            dest_col = _first(f, dest_keys)
            bound = bounds.get(dest_col)
            if bound is None or (bound.get("minimum") is None and bound.get("maximum") is None):
                continue
            stream_field = _first(f, stream_keys)
            matches = [c for c in filter_conditions if c[1] == stream_field]
            if not matches:
                findings.append(Finding(
                    severity="error", step_name=step_name,
                    message=(
                        f"{CHECK_FILTER_PREFIX}Step '{step_name}': columna '{dest_col}' de '{table}' "
                        f"tiene CHECK de rango en el DDL (minimum={bound.get('minimum')}, "
                        f"maximum={bound.get('maximum')}) pero ningún FilterRows de este KTR valida "
                        f"'{stream_field}' antes de escribir — filas fuera de rango pueden llegar a "
                        "producción sin saneamiento previo."
                    ),
                ))
                continue
            col_type = bound.get("type")
            if col_type in _NUMERIC_TYPES:
                for filter_step_name, _, value_type in matches:
                    if value_type == "String":
                        findings.append(Finding(
                            severity="error", step_name=filter_step_name,
                            message=(
                                f"{CHECK_FILTER_PREFIX}Step '{filter_step_name}': filtra '{stream_field}' "
                                f"con value_type='String', pero la columna destino '{dest_col}' es "
                                f"'{col_type}' — Kettle compara la constante como texto (orden "
                                "lexicográfico), no como número. Cambiar value_type a 'Integer'/'Number'."
                            ),
                        ))
    return findings
