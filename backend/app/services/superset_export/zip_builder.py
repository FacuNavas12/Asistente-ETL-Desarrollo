"""Orquestador del export de Superset: arma el ZIP completo (metadata + database +
datasets + charts + dashboard) para un Etl ya persistido. Port de generateSupersetZip
en frontend/src/utils/supersetExport.js, con una diferencia arquitectonica clave:
NO reconstruye el esquema DWH re-parseando el XML .ktr generado (extractDwhSchemaFromKtrs
en el JS original). En su lugar, cuando result.dwh_sample viene vacio (flujo de 2 KTR,
ver etl_generator._build_response_from_two_ktr_data), parsea el DDL del DWH que el
usuario ya confirmo (form_data["dwh_model"]) con el ddl_adapter (sqlglot) existente —
la misma estructura que ya usa el resto del backend para DDL pegado por el usuario.

Prioridad de resolucion del esquema DWH:
  1. result["dwh_sample"] si tiene filas no vacias (flujo legacy monolitico).
  2. form_data["dwh_model"] (DDL string confirmado en la inferencia) parseado con
     ddl_adapter.parse_ddl -> CanonicalSchema[] -> fila sintetica tipada por CanonicalType.
  3. form_data["dwhModel"]["tables"] (shape estructurado legacy, si algun ETL viejo
     lo tiene) -> fila sintetica via synthetic_value (name-aware)."""

from __future__ import annotations

import io
import logging
import zipfile

from app.schemas.canonical import CanonicalType
from app.services.superset_export.asset_yaml import (
    bar_chart_yaml,
    big_number_yaml,
    dashboard_yaml,
    database_yaml,
    dataset_yaml,
    deterministic_uuid,
    line_chart_yaml,
    metadata_yaml,
    pie_chart_yaml,
    slugify,
    table_chart_yaml,
)
from app.services.superset_export.chart_selection import select_charts_for_table
from app.services.superset_export.constants import DB_NAME, DB_UUID, DESCRIPTIVE_KEYWORDS, STAGING_PREFIXES
from app.services.superset_export.semantic_types import infer_semantic_type, is_usable_column
from app.services.superset_export.synthetic_values import synthetic_value

logger = logging.getLogger(__name__)

_PLACEHOLDER_URI = "postgresql://user:password@host:5432/dwh"

_DDL_TYPE_TO_VALUE = {
    CanonicalType.BOOLEAN: True,
    CanonicalType.INTEGER: 1,
    CanonicalType.NUMBER: 0.0,
    CanonicalType.DATE: "2024-01-01",
    CanonicalType.DATETIME: "2024-01-01",
    CanonicalType.TIME: "2024-01-01",
}


def is_analytics_table(name: str) -> bool:
    lower = str(name).lower()
    return not any(lower.startswith(p) for p in STAGING_PREFIXES)


# ── Table builder ──────────────────────────────────────────────────────────────

def build_tables(dwh_sample: dict, dwh_model: dict | None = None) -> list[dict]:
    tables: list[dict] = []
    for name, rows in dwh_sample.items():
        if not is_analytics_table(name):
            continue
        if not isinstance(rows, list) or not rows:
            continue

        # Si la fila esta vacia (modelo no pobló valores), generar valores sinteticos
        # a partir del dwhModel estructurado legacy (si esta disponible para esta tabla).
        first_row = rows[0] or {}
        if not first_row:
            table_model = None
            for t in (dwh_model or {}).get("tables") or []:
                if str(t.get("nombre", "")).lower() == str(name).lower():
                    table_model = t
                    break
            if table_model and table_model.get("columnas"):
                synthetic_row = {
                    col["nombre"].lower(): synthetic_value(col["nombre"])
                    for col in table_model["columnas"]
                }
                rows = [synthetic_row]
            else:
                continue

        col_names: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for k in (row or {}).keys():
                lk = k.lower()
                if lk not in seen:
                    seen.add(lk)
                    col_names.append(lk)

        columns = []
        for col in col_names:
            values = [(row or {}).get(col, (row or {}).get(col.upper())) for row in rows]
            columns.append({
                "name": col,
                "values": values,
                "semantic_type": infer_semantic_type(col, values),
            })

        usable_columns = [
            c for c in columns
            if is_usable_column(c["name"]) and any(v is not None and v != "" for v in c["values"])
        ]

        pick_column = next(
            (c for c in usable_columns if any(k in c["name"].upper() for k in DESCRIPTIVE_KEYWORDS)),
            None,
        )
        if pick_column is None:
            for c in usable_columns:
                first_non_null = next((v for v in c["values"] if v is not None), None)
                if isinstance(first_non_null, str):
                    pick_column = c
                    break
        if pick_column is None and usable_columns:
            pick_column = usable_columns[0]
        if pick_column is None:
            pick_column = next(
                (c for c in columns if any(v is not None and v != "" for v in c["values"])),
                None,
            )

        if pick_column is not None:
            tables.append({"name": name, "columns": columns, "pick_column": pick_column})

    return tables


# ── Resolucion de esquema DWH cuando dwh_sample viene vacio ───────────────────

def _ddl_field_synthetic_value(field) -> object:
    value = _DDL_TYPE_TO_VALUE.get(field.type)
    return value if value is not None else synthetic_value(field.name)


def _tables_from_ddl(ddl: str) -> dict:
    from app.services.adapters.ddl_adapter import parse_ddl

    if not ddl or not ddl.strip():
        return {}

    schemas = []
    for dialect in ("postgres", None):
        try:
            schemas = parse_ddl(ddl, dialect)
        except ValueError:
            continue
        if schemas:
            break

    dwh_sample: dict = {}
    for schema in schemas:
        table_name = schema.source_name.split(".")[-1].lower()
        if not is_analytics_table(table_name) or not schema.fields:
            continue
        dwh_sample[table_name] = [
            {field.name.lower(): _ddl_field_synthetic_value(field) for field in schema.fields}
        ]
    return dwh_sample


def _tables_from_legacy_dwh_model(dwh_model: dict) -> dict:
    dwh_sample: dict = {}
    for table in (dwh_model or {}).get("tables") or []:
        table_name = str(table.get("nombre", "")).lower()
        if not table_name:
            continue
        row = {
            col["nombre"].lower(): synthetic_value(col["nombre"])
            for col in (table.get("columnas") or [])
            if col.get("nombre")
        }
        if row:
            dwh_sample[table_name] = [row]
    return dwh_sample


def _is_dwh_sample_empty(dwh_sample: dict) -> bool:
    if not dwh_sample:
        return True
    return all(
        (not rows) or all(not (row or {}) for row in rows)
        for rows in dwh_sample.values()
    )


# ── Orquestador principal ──────────────────────────────────────────────────────

def build(etl, sqlalchemy_uri: str = _PLACEHOLDER_URI) -> tuple[bytes, dict]:
    """Arma el ZIP de export para `etl`. Devuelve (zip_bytes, dwh_sample_original) —
    el segundo elemento es result["dwh_sample"] SIN reconstruir, tal cual lo usa
    SupersetClient.import_dashboard como fallback secundario de seed (la fuente
    primaria de columnas para el seed es el propio ZIP, ver dwh_tables.py).
    Lanza ValueError si no hay ninguna tabla DWH exportable."""
    result = etl.result or {}
    form_data = etl.form_data or {}
    raw_dwh_sample = result.get("dwh_sample") or {}

    dwh_sample = raw_dwh_sample
    if _is_dwh_sample_empty(dwh_sample):
        dwh_ddl = form_data.get("dwh_model")
        if isinstance(dwh_ddl, str) and dwh_ddl.strip():
            try:
                dwh_sample = _tables_from_ddl(dwh_ddl)
            except Exception as exc:
                logger.warning("No se pudo parsear dwh_model DDL para export a Superset: %s", exc)
                dwh_sample = {}
        if not dwh_sample:
            legacy_model = form_data.get("dwhModel")
            if isinstance(legacy_model, dict):
                dwh_sample = _tables_from_legacy_dwh_model(legacy_model)

    legacy_dwh_model = form_data.get("dwhModel")
    tables = build_tables(dwh_sample, legacy_dwh_model if isinstance(legacy_dwh_model, dict) else None)
    if not tables:
        raise ValueError("No hay datos en el DWH para exportar a Superset.")

    zip_bytes = _package_zip(etl, tables, sqlalchemy_uri)
    return zip_bytes, raw_dwh_sample


def _normalize_label(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _package_zip(etl, tables: list[dict], sqlalchemy_uri: str) -> bytes:
    buf = io.BytesIO()
    folder = f"etl_{slugify(etl.name)}_export"
    etl_seed = str(getattr(etl, "id", None) or etl.name or "etl")
    dash_uuid = deterministic_uuid(f"{etl_seed}:dashboard")
    all_charts: list[dict] = []

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{folder}/metadata.yaml", metadata_yaml())
        zf.writestr(f"{folder}/databases/{DB_NAME}.yaml", database_yaml(DB_UUID, sqlalchemy_uri))

        for table in tables:
            ds_uuid = deterministic_uuid(f"{etl_seed}:dataset:{table['name']}")
            zf.writestr(f"{folder}/datasets/{DB_NAME}/{table['name']}.yaml", dataset_yaml(table, ds_uuid, DB_UUID))

            for spec in select_charts_for_table(table):
                column_name = spec.get("column_name")
                x_axis = spec.get("x_axis")
                chart_uuid = deterministic_uuid(
                    f"{etl_seed}:chart:{table['name']}:{spec['type']}:{column_name or ''}:{x_axis or ''}"
                )
                if spec["type"] == "line":
                    chart_label = _normalize_label(f"{table['name']} - {column_name} por {x_axis} ({spec['label']})")
                else:
                    chart_label = _normalize_label(
                        f"{table['name']} - {x_axis or column_name or spec['label']} ({spec['label']})"
                    )

                common = {
                    "column_name": column_name,
                    "ds_uuid": ds_uuid,
                    "chart_uuid": chart_uuid,
                    "slice_name": chart_label,
                }

                chart_type = spec["type"]
                if chart_type == "table":
                    yaml_content = table_chart_yaml(**common, is_metric=spec.get("is_metric", False))
                elif chart_type == "pie":
                    yaml_content = pie_chart_yaml(**common)
                elif chart_type == "pie_with_metric":
                    yaml_content = pie_chart_yaml(**common, metric=spec.get("metric"))
                elif chart_type == "bar":
                    yaml_content = bar_chart_yaml(**common, x_axis=x_axis, metric=spec.get("metric"))
                elif chart_type == "bar_with_metric":
                    yaml_content = bar_chart_yaml(**common, x_axis=x_axis or column_name, metric=spec.get("metric"))
                elif chart_type == "line":
                    yaml_content = line_chart_yaml(**common, x_axis=x_axis, metric=spec.get("metric"))
                elif chart_type == "big_number":
                    yaml_content = big_number_yaml(**common)
                else:
                    yaml_content = None

                if yaml_content is None:
                    continue
                zf.writestr(f"{folder}/charts/{slugify(chart_label)}_{chart_uuid[:8]}.yaml", yaml_content)
                all_charts.append({"chart_uuid": chart_uuid, "slice_name": chart_label})

        zf.writestr(
            f"{folder}/dashboards/{slugify(etl.name)}_{dash_uuid[:8]}.yaml",
            dashboard_yaml(etl_name=etl.name, dash_uuid=dash_uuid, charts=all_charts),
        )

        table_names = ", ".join(t["name"] for t in tables)
        zf.writestr(
            f"{folder}/README.md",
            f"# Dashboard Superset - {etl.name}\n\n"
            f"Importar en Superset: Settings -> Import Dashboards -> seleccionar este ZIP.\n"
            f"Si la URI no esta configurada, editar en Settings -> Database Connections -> {DB_NAME}.\n\n"
            f"Tablas: {table_names}\n"
            f"Charts: {len(all_charts)}\n",
        )

    return buf.getvalue()
