"""
Tests de superset_export: deterministic_uuid (port bit-a-bit del hash del JS),
build_tables/build() con las 3 fuentes de esquema DWH (dwh_sample real, DDL
parseado, dwhModel legacy estructurado), y select_charts_for_table.

No requieren BD — build() solo lee atributos (.id/.name/.result/.form_data) de un
objeto Etl-like; usamos SimpleNamespace en vez del modelo SQLAlchemy real.
"""
from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest
import yaml

from app.services.superset_export.asset_yaml import deterministic_uuid
from app.services.superset_export.chart_selection import select_charts_for_table
from app.services.superset_export.zip_builder import build


def _fake_etl(*, etl_id="etl123", name="Ventas", result=None, form_data=None):
    return SimpleNamespace(id=etl_id, name=name, result=result or {}, form_data=form_data or {})


# ── deterministic_uuid: valores de referencia calculados corriendo el JS
# original (frontend/src/utils/supersetExport.js deterministicUUID) con Node,
# para las mismas seeds — garantiza overwrite=true idempotente en Superset. ───

@pytest.mark.parametrize("seed,expected", [
    ("etl123:dashboard", "0661b8c1-b73f-4057-919d-b221b7f3d74f"),
    ("etl123:dataset:dim_cliente", "361f64e7-5be6-4bd9-bad0-1fc75d259745"),
    ("etl123:dataset:fact_ventas", "d750c27c-7dbc-43b2-80ca-b43c8756cbfd"),
    ("etl123:chart:fact_ventas:big_number::", "50c05661-eb2b-4d11-95a7-f441e13337dd"),
    ("", "6251f24c-843c-4557-85c1-58ac8876bb1e"),
    ("a", "012d7d36-5f6b-44da-ac59-e6765f4e0b7c"),
    ("hello world", "402589d2-8f18-4b92-a326-fb92871caaa8"),
])
def test_deterministic_uuid_matches_js_reference(seed, expected):
    assert deterministic_uuid(seed) == expected


def test_deterministic_uuid_is_stable_across_calls():
    assert deterministic_uuid("same seed") == deterministic_uuid("same seed")


# ── build(): flujo de 2 KTR (dwh_sample vacio) → parsear DDL de dwh_model ─────

DWH_DDL = """
CREATE TABLE stg_facturas (
    id INTEGER,
    monto DECIMAL(10,2)
);

CREATE TABLE dim_cliente (
    sk_cliente INTEGER PRIMARY KEY,
    nombre VARCHAR(100),
    ciudad VARCHAR(50)
);

CREATE TABLE fact_ventas (
    sk_venta INTEGER PRIMARY KEY,
    fk_cliente INTEGER,
    fecha_venta DATE,
    monto_total DECIMAL(10,2)
);
"""


def test_build_from_empty_dwh_sample_parses_ddl():
    etl = _fake_etl(
        result={"dwh_sample": {}},
        form_data={"dwh_model": DWH_DDL},
    )
    zip_bytes, dwh_sample_returned = build(etl)

    # dwh_sample devuelto es el original (crudo), no el reconstruido internamente.
    assert dwh_sample_returned == {}

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert any(n.endswith("datasets/ETL_DWH/dim_cliente.yaml") for n in names)
        assert any(n.endswith("datasets/ETL_DWH/fact_ventas.yaml") for n in names)
        assert not any("stg_facturas" in n for n in names)
        assert any("/charts/" in n for n in names)
        assert any("/dashboards/" in n for n in names)

        dataset_name = next(n for n in names if n.endswith("datasets/ETL_DWH/fact_ventas.yaml"))
        dataset_doc = yaml.safe_load(zf.read(dataset_name))
        assert dataset_doc["table_name"] == "fact_ventas"
        col_names = {c["column_name"] for c in dataset_doc["columns"]}
        assert {"sk_venta", "fk_cliente", "fecha_venta", "monto_total"} <= col_names


def test_build_uses_real_dwh_sample_when_present():
    etl = _fake_etl(
        result={"dwh_sample": {"dim_producto": [{"sk_producto": 1, "nombre": "Widget"}]}},
        form_data={"dwh_model": DWH_DDL},  # presente pero no debe usarse
    )
    zip_bytes, dwh_sample_returned = build(etl)
    assert dwh_sample_returned == {"dim_producto": [{"sk_producto": 1, "nombre": "Widget"}]}

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert any(n.endswith("datasets/ETL_DWH/dim_producto.yaml") for n in names)
        # el DDL de dwh_model NO se usa porque dwh_sample ya tenia datos reales
        assert not any("fact_ventas" in n for n in names)


def test_build_raises_when_no_schema_available():
    etl = _fake_etl(result={"dwh_sample": {}}, form_data={})
    with pytest.raises(ValueError):
        build(etl)


# ── select_charts_for_table ────────────────────────────────────────────────────

def test_select_charts_for_fact_table_with_metric_and_date():
    table = {
        "name": "fact_ventas",
        "pick_column": {"name": "monto_total", "values": [100.0], "semantic_type": "metric"},
        "columns": [
            {"name": "sk_venta", "values": [1], "semantic_type": "id"},
            {"name": "fecha_venta", "values": ["2024-01-01"], "semantic_type": "date"},
            {"name": "monto_total", "values": [100.0], "semantic_type": "metric"},
        ],
    }
    charts = select_charts_for_table(table)
    types = [c["type"] for c in charts]
    assert "big_number" in types
    assert "line" in types
    assert "table" in types
