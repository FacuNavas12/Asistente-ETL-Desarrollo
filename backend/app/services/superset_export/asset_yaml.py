"""Builders YAML del formato de export de Superset (metadata/database/dataset/charts/
dashboard) + helpers de serializacion (deterministic_uuid, slugify, dump). Port 1:1 de
los *Yaml builders en frontend/src/utils/supersetExport.js — las claves de los dicts
NO se snake_case-an porque son literalmente el schema YAML que Superset espera.

deterministic_uuid es un port bit-a-bit del hash de 128 bits del JS (dos MurmurHash-like
de 32 bits con aritmetica Math.imul + shifts con y sin signo). Debe producir el MISMO
UUID que el JS para la misma seed: mismo ETL + misma tabla/chart -> mismo UUID en cada
export -> overwrite=true actualiza el mismo objeto en Superset en vez de duplicarlo.
Ver backend/tests/test_superset_export.py para los valores de referencia (calculados
corriendo el JS original con Node)."""

from __future__ import annotations

import json
import re
import unicodedata
from array import array
from datetime import datetime, timezone

import yaml

from app.services.superset_export.constants import DB_NAME, DB_SCHEMA, VERSION
from app.services.superset_export.chart_selection import count_metric
from app.services.superset_export.semantic_types import infer_type

_MASK32 = 0xFFFFFFFF


def _to_int32(x: int) -> int:
    x &= _MASK32
    return x - 0x100000000 if x >= 0x80000000 else x


def deterministic_uuid(seed: str) -> str:
    """UUID deterministico: misma seed -> mismo UUID siempre."""
    h1 = 0xDEADBEEF
    h2 = 0x41C6CE57

    units = array("H")
    units.frombytes(seed.encode("utf-16-le"))
    for c in units:
        h1 = ((h1 ^ c) * 2654435761) & _MASK32
        h2 = ((h2 ^ c) * 1597334677) & _MASK32

    h1 = (h1 ^ (h2 >> 17)) & _MASK32
    h2 = (h2 ^ (h1 >> 13)) & _MASK32
    h1 = (h1 * 2654435761) & _MASK32
    h2 = (h2 * 1597334677) & _MASK32

    h3 = (h1 ^ ((h2 << 5) & _MASK32)) & _MASK32
    h4 = (h2 ^ ((_to_int32(h1) >> 3) & _MASK32)) & _MASK32

    def pad(n: int) -> str:
        return format(n & _MASK32, "08x")

    a, b, c_, d = pad(h1), pad(h2), pad(h3), pad(h4)
    return f"{a}-{b[0:4]}-4{b[5:8]}-{format(8 + (h3 & 3), 'x')}{c_[1:4]}-{c_[4:]}{d}"


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    s = re.sub(r"^_", "", s)
    s = re.sub(r"_$", "", s)
    s = s[:60]
    return s or "etl"


def dump(obj) -> str:
    return yaml.safe_dump(
        obj, default_flow_style=False, sort_keys=False,
        width=1_000_000, allow_unicode=True,
    )


# ── Database / dataset YAML ───────────────────────────────────────────────────

def metadata_yaml() -> str:
    return dump({
        "version": VERSION,
        "type": "Dashboard",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def database_yaml(db_uuid: str, sqlalchemy_uri: str) -> str:
    return dump({
        "database_name": DB_NAME,
        "sqlalchemy_uri": sqlalchemy_uri,
        "cache_timeout": None,
        "expose_in_sqllab": True,
        "allow_run_async": False,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "allow_file_upload": False,
        "extra": json.dumps({
            "allows_virtual_table_explore": True,
            "schemas_allowed_for_csv_upload": [],
            "engine_params": {},
            "metadata_params": {},
        }),
        "uuid": db_uuid,
        "version": VERSION,
    })


def dataset_yaml(table: dict, ds_uuid: str, db_uuid: str) -> str:
    return dump({
        "table_name": table["name"],
        "main_dttm_col": None,
        "description": None,
        "default_endpoint": None,
        "offset": 0,
        "cache_timeout": None,
        "schema": DB_SCHEMA,
        "sql": None,
        "params": None,
        "template_params": None,
        "filter_select_enabled": True,
        "fetch_values_predicate": None,
        "extra": None,
        "normalize_columns": False,
        "always_filter_main_dttm": False,
        "uuid": ds_uuid,
        "metrics": [{
            "metric_name": "count",
            "verbose_name": "COUNT(*)",
            "metric_type": "count",
            "expression": "COUNT(*)",
            "description": None,
            "d3format": None,
            "extra": None,
            "warning_text": None,
        }],
        "columns": [
            {
                "column_name": c["name"].lower(),
                "verbose_name": None,
                "is_dttm": False,
                "is_active": True,
                "type": infer_type(c["values"]),
                "advanced_data_type": None,
                "groupby": True,
                "filterable": True,
                "expression": None,
                "description": None,
                "python_date_format": None,
                "extra": None,
            }
            for c in table["columns"]
        ],
        "version": VERSION,
        "database_uuid": db_uuid,
    })


# ── Superset chart YAML generators ────────────────────────────────────────────
# IMPORTANTE: params se serializa como objeto YAML (no JSON string).
# slice_name siempre se recibe como parametro sliceName/slice_name para garantizar
# que coincida exactamente con el sliceName del dashboard position_json.

def _chart_envelope(viz_type: str, params: dict, chart_uuid: str, ds_uuid: str, slice_name: str) -> dict:
    return {
        "slice_name": slice_name,
        "description": None,
        "certified_by": None,
        "certification_details": None,
        "viz_type": viz_type,
        "params": params,
        "query_context": None,
        "cache_timeout": None,
        "uuid": chart_uuid,
        "version": VERSION,
        "dataset_uuid": ds_uuid,
        "is_managed_externally": False,
        "external_url": None,
    }


def table_chart_yaml(*, column_name, ds_uuid, chart_uuid, slice_name, is_metric=False) -> str:
    params = {
        "datasource": f"{ds_uuid}__table",
        "viz_type": "table",
        "url_params": {},
        "time_grain_sqla": None,
        "time_range": "No filter",
        "query_mode": "raw" if is_metric else "aggregate",
        "groupby": [] if is_metric else [column_name],
        "metrics": [] if is_metric else [count_metric],
        "all_columns": [column_name] if is_metric else [],
        "percent_metrics": [],
        "adhoc_filters": [],
        "order_by_cols": [],
        "order_desc": True,
        "row_limit": 1000,
        "include_time": False,
        "show_cell_bars": True,
        "align_pn": False,
        "page_length": 25,
        "include_search": True,
        "extra_form_data": {},
    }
    return dump(_chart_envelope("table", params, chart_uuid, ds_uuid, slice_name))


def pie_chart_yaml(*, column_name, ds_uuid, chart_uuid, slice_name, metric=None) -> str:
    metric = metric if metric is not None else count_metric
    params = {
        "datasource": f"{ds_uuid}__table",
        "viz_type": "pie",
        "url_params": {},
        "time_range": "No filter",
        "metric": metric,
        "adhoc_filters": [],
        "groupby": [column_name],
        "row_limit": 100,
        "color_scheme": "supersetColors",
        "show_legend": True,
        "rich_tooltip": True,
        "donut": True,
        "show_labels": True,
        "labels_outside": True,
        "extra_form_data": {},
    }
    return dump(_chart_envelope("pie", params, chart_uuid, ds_uuid, slice_name))


def bar_chart_yaml(*, column_name, ds_uuid, chart_uuid, slice_name, x_axis=None, metric=None) -> str:
    params = {
        "datasource": f"{ds_uuid}__table",
        "viz_type": "echarts_timeseries_bar",
        "x_axis": x_axis if x_axis is not None else column_name,
        "metrics": [metric if metric is not None else count_metric],
        "groupby": [],
        "adhoc_filters": [],
        "row_limit": 10000,
        "time_range": "No filter",
        "color_scheme": "supersetColors",
        "extra_form_data": {},
        "orientation": "vertical",
        "x_axis_sort_asc": True,
        "x_axis_sort_series": "name",
    }
    return dump(_chart_envelope("echarts_timeseries_bar", params, chart_uuid, ds_uuid, slice_name))


def line_chart_yaml(*, column_name, ds_uuid, chart_uuid, slice_name, x_axis=None, metric=None) -> str:
    params = {
        "datasource": f"{ds_uuid}__table",
        "viz_type": "echarts_timeseries_line",
        "x_axis": x_axis,
        "metrics": [metric if metric is not None else count_metric],
        "groupby": [],
        "adhoc_filters": [],
        "row_limit": 10000,
        "time_range": "No filter",
        "color_scheme": "supersetColors",
        "extra_form_data": {},
    }
    return dump(_chart_envelope("echarts_timeseries_line", params, chart_uuid, ds_uuid, slice_name))


def big_number_yaml(*, column_name, ds_uuid, chart_uuid, slice_name) -> str:
    if column_name:
        kpi_metric = {
            "label": f"SUM({column_name})",
            "expressionType": "SQL",
            "sqlExpression": f"SUM({column_name})",
            "hasCustomLabel": False,
            "optionName": f"metric_sum_{column_name}",
        }
    else:
        kpi_metric = count_metric
    params = {
        "datasource": f"{ds_uuid}__table",
        "viz_type": "big_number_total",
        "metric": kpi_metric,
        "adhoc_filters": [],
        "time_range": "No filter",
        "extra_form_data": {},
    }
    return dump(_chart_envelope("big_number_total", params, chart_uuid, ds_uuid, slice_name))


# ── Dashboard layout builder ──────────────────────────────────────────────────

def build_dashboard_config(*, etl_name: str, dash_uuid: str, charts: list[dict]) -> dict:
    rows = [charts[i:i + 2] for i in range(0, len(charts), 2)]

    position = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {
            "type": "GRID", "id": "GRID_ID",
            "children": [f"ROW-{i}" for i in range(len(rows))],
            "parents": ["ROOT_ID"],
        },
    }

    for row_idx, row in enumerate(rows):
        row_id = f"ROW-{row_idx}"
        chart_ids = [f"CHART-{c['chart_uuid'][:8]}" for c in row]
        position[row_id] = {
            "type": "ROW", "id": row_id, "children": chart_ids,
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
            "parents": ["ROOT_ID", "GRID_ID"],
        }
        for chart_id, c in zip(chart_ids, row):
            position[chart_id] = {
                "type": "CHART", "id": chart_id, "children": [],
                "meta": {"width": 6, "height": 50, "chartId": 0, "sliceName": c["slice_name"], "uuid": c["chart_uuid"]},
                "parents": ["ROOT_ID", "GRID_ID", row_id],
            }

    return {
        "dashboard_title": f"ETL - {etl_name}",
        "description": None,
        "css": "",
        "slug": None,
        "uuid": dash_uuid,
        "position": position,
        "metadata": {
            "show_native_filters": True,
            "default_filters": "{}",
            "filter_scopes": {},
            "expanded_slices": {},
            "refresh_frequency": 0,
            "timed_refresh_immune_slices": [],
            "color_scheme": "",
            "label_colors": {},
            "shared_label_colors": {},
            "cross_filters_enabled": False,
            "global_chart_configuration": {},
            "chart_configuration": {},
        },
        "version": VERSION,
        "is_managed_externally": False,
        "external_url": None,
        "certified_by": None,
        "certification_details": None,
        "published": False,
    }


def dashboard_yaml(*, etl_name: str, dash_uuid: str, charts: list[dict]) -> str:
    return dump(build_dashboard_config(etl_name=etl_name, dash_uuid=dash_uuid, charts=charts))
