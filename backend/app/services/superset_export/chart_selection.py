"""Heuristica de seleccion de charts por tabla DWH: clasifica la tabla como
FACT/DIM/BRIDGE/generica por prefijo de nombre y decide que combinacion de
KPI/line/bar/pie/table mostrar segun las columnas usables. Port 1:1 de
selectChartsForTable en frontend/src/utils/supersetExport.js.

Cada tabla es un dict {"name": str, "columns": [...], "pick_column": {...}} y cada
columna {"name": str, "values": list, "semantic_type": str}. Devuelve una lista de
chart-specs: {"type", "column_name", "x_axis"?, "metric"?, "label", "is_metric"?}.

Las claves de count_metric/sum_metric NO se snake_case-an (expressionType,
sqlExpression, hasCustomLabel, optionName) porque se serializan tal cual al YAML
de Superset — ese es el schema que Superset espera, no una estructura interna."""

from __future__ import annotations

import re

from app.services.superset_export.constants import AUDIT_KEYWORDS, TECHNICAL_CAT_KEYWORDS
from app.services.superset_export.semantic_types import is_usable_column

count_metric = {
    "label": "COUNT(*)",
    "expressionType": "SQL",
    "sqlExpression": "COUNT(*)",
    "hasCustomLabel": False,
    "optionName": "metric_count",
}


def sum_metric(col_name: str) -> dict:
    safe = re.sub(r"\W", "_", col_name.lower())
    return {
        "label": f"SUM({col_name})",
        "expressionType": "SQL",
        "sqlExpression": f"SUM({col_name})",
        "hasCustomLabel": False,
        "optionName": f"metric_sum_{safe}",
    }


_FACT_RE = re.compile(r"^(fact_|hecho_|fct_|ft_)", re.IGNORECASE)
_DIM_RE = re.compile(r"^(dim_|dimension_|d_)", re.IGNORECASE)
_BRIDGE_RE = re.compile(r"^(bridge_|br_|rel_|relacion_)", re.IGNORECASE)


def _is_real_metric(col: dict) -> bool:
    u = col["name"].upper()
    return not (u.startswith("ID_") or u.endswith("_ID") or u.startswith("SK_") or u.startswith("FK_"))


def select_charts_for_table(table: dict) -> list[dict]:
    charts: list[dict] = []
    all_usable = [c for c in table["columns"] if is_usable_column(c["name"])]
    date_columns = [c for c in all_usable if c["semantic_type"] == "date"]
    metric_cols = [c for c in all_usable if c["semantic_type"] == "metric"]
    cat_cols = [c for c in all_usable if c["semantic_type"] == "category"]

    is_fact = bool(_FACT_RE.match(table["name"]))
    is_dim = bool(_DIM_RE.match(table["name"]))
    is_bridge = bool(_BRIDGE_RE.match(table["name"]))

    def cardinality(col: dict) -> int | None:
        has_values = any(v is not None for c in table["columns"] for v in c["values"])
        if not has_values:
            return None
        return len({v for v in col["values"] if v is not None})

    # Business dates — exclude audit/ETL load timestamps
    business_dates = [
        c for c in date_columns
        if not any(k in c["name"].upper() for k in AUDIT_KEYWORDS)
    ]

    # Real metric columns — exclude any ID-like numerics that slipped through
    real_metrics = [c for c in metric_cols if _is_real_metric(c)]
    best_metric = real_metrics[0] if real_metrics else (metric_cols[0] if metric_cols else None)
    best_metric_obj = sum_metric(best_metric["name"]) if best_metric else count_metric

    if is_bridge:
        charts.append({"type": "big_number", "column_name": None, "label": "Total registros"})
        detail_col = all_usable[0] if all_usable else table["pick_column"]
        charts.append({"type": "table", "column_name": detail_col["name"], "label": "Detalle"})
        return charts

    if is_fact:
        charts.append({
            "type": "big_number",
            "column_name": best_metric["name"] if best_metric else None,
            "label": "KPI",
        })
        second = real_metrics[1] if len(real_metrics) > 1 else None
        if second:
            charts.append({"type": "big_number", "column_name": second["name"], "label": "KPI"})
        if business_dates and best_metric:
            charts.append({
                "type": "line",
                "column_name": best_metric["name"],
                "x_axis": business_dates[0]["name"],
                "metric": best_metric_obj,
                "label": "Evolución temporal",
            })
        business_cat_cols = [
            c for c in cat_cols
            if not any(k in c["name"].upper() for k in TECHNICAL_CAT_KEYWORDS)
        ]
        if business_cat_cols and best_metric:
            charts.append({
                "type": "bar",
                "column_name": best_metric["name"],
                "x_axis": business_cat_cols[0]["name"],
                "metric": best_metric_obj,
                "label": "Por categoría",
            })
        detail_col = best_metric if best_metric else table["pick_column"]
        charts.append({
            "type": "table",
            "column_name": detail_col["name"],
            "label": "Detalle",
            "is_metric": bool(best_metric),
        })
        return charts

    if is_dim:
        # Dimensiones: solo pie/bar de distribución + tabla de detalle.
        # NUNCA line chart — las dims no son series temporales.
        col = cat_cols[0] if cat_cols else table["pick_column"]
        col_name = col["name"] if col else table["pick_column"]["name"]
        source_values = col["values"] if col else table["pick_column"]["values"]
        unique_count = len({v for v in source_values if v is not None})

        dim_real_metrics = [
            c for c in metric_cols
            if not (
                c["name"].upper().startswith("SK_") or c["name"].upper().startswith("FK_")
                or c["name"].upper().startswith("ID_") or c["name"].upper().endswith("_ID")
                or c["name"].upper().startswith("COD_") or c["name"].upper().startswith("BK_")
            )
        ]

        if dim_real_metrics:
            dim_best_metric = dim_real_metrics[0]
            # Nota: a diferencia de sum_metric(), este optionName NO se
            # lowercasea/sanitiza — port 1:1 del inline object del JS original.
            dim_metric_obj = {
                "label": f"SUM({dim_best_metric['name']})",
                "expressionType": "SQL",
                "sqlExpression": f"SUM({dim_best_metric['name']})",
                "hasCustomLabel": False,
                "optionName": f"metric_sum_{dim_best_metric['name']}",
            }
            if unique_count <= 15:
                charts.append({"type": "pie_with_metric", "column_name": col_name, "metric": dim_metric_obj, "label": "Distribución"})
            else:
                charts.append({"type": "bar_with_metric", "column_name": col_name, "metric": dim_metric_obj, "x_axis": col_name, "label": "Distribución"})
        else:
            if unique_count <= 15:
                charts.append({"type": "pie", "column_name": col_name, "label": "Distribución"})
            else:
                charts.append({"type": "bar", "column_name": col_name, "x_axis": col_name, "label": "Distribución"})
        charts.append({"type": "table", "column_name": col_name, "label": "Detalle"})
        return charts

    # Generic / unknown table type — clasificación semántica por contenido, no por nombre
    # Caso A: tiene métricas reales + fechas → comportamiento fact-like
    if real_metrics and business_dates:
        charts.append({"type": "big_number", "column_name": best_metric["name"] if best_metric else None, "label": "KPI"})
        second = real_metrics[1] if len(real_metrics) > 1 else None
        if second:
            charts.append({"type": "big_number", "column_name": second["name"], "label": "KPI"})
        charts.append({
            "type": "line",
            "column_name": best_metric["name"],
            "x_axis": business_dates[0]["name"],
            "metric": best_metric_obj,
            "label": "Evolución temporal",
        })
        if cat_cols:
            charts.append({
                "type": "bar",
                "column_name": best_metric["name"],
                "x_axis": cat_cols[0]["name"],
                "metric": best_metric_obj,
                "label": "Por categoría",
            })
        detail_col = best_metric if best_metric else table["pick_column"]
        charts.append({"type": "table", "column_name": detail_col["name"], "label": "Detalle", "is_metric": True})
        return charts

    # Caso B: tiene métricas reales sin fechas → KPI + bar por categoría + tabla
    if real_metrics:
        charts.append({"type": "big_number", "column_name": best_metric["name"] if best_metric else None, "label": "KPI"})
        second = real_metrics[1] if len(real_metrics) > 1 else None
        if second:
            charts.append({"type": "big_number", "column_name": second["name"], "label": "KPI"})
        if cat_cols:
            charts.append({
                "type": "bar",
                "column_name": best_metric["name"],
                "x_axis": cat_cols[0]["name"],
                "metric": best_metric_obj,
                "label": "Por categoría",
            })
        detail_col = best_metric if best_metric else table["pick_column"]
        charts.append({"type": "table", "column_name": detail_col["name"], "label": "Detalle", "is_metric": True})
        return charts

    # Caso C: tiene fechas sin métricas → bar de COUNT + tabla
    if business_dates:
        charts.append({
            "type": "bar",
            "column_name": table["pick_column"]["name"],
            "x_axis": business_dates[0]["name"],
            "metric": count_metric,
            "label": "Evolución temporal",
        })
        charts.append({"type": "table", "column_name": table["pick_column"]["name"], "label": "Detalle"})
        return charts

    # Caso D: solo categorías → pie/bar según cardinalidad + tabla
    col = cat_cols[0] if cat_cols else table["pick_column"]
    card = cardinality(col)
    if card is not None and card > 15:
        charts.append({"type": "bar", "column_name": col["name"], "x_axis": col["name"], "metric": count_metric, "label": "Distribución"})
    else:
        charts.append({"type": "pie", "column_name": col["name"], "label": "Distribución"})
    charts.append({"type": "table", "column_name": col["name"], "label": "Detalle"})
    return charts
