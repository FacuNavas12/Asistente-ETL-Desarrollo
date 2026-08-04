"""
Unit tests — Fase 2-ter item 1 (S-4/H45,
docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md):
check_constraint_filter_rows exige un FilterRows en el mismo KTR por cada
columna con CHECK de rango (minimum/maximum) en la tabla DWH que un writer
escribe, y valida value_type contra el tipo de la columna (mitad de A-5).
Puro/sin LLM/sin DB.
"""
from __future__ import annotations

from app.services.ktr_builder.validators import ValidationContext
from app.services.ktr_builder.validators.check_constraint_filter import (
    CHECK_FILTER_PREFIX,
    check_constraint_filter_rows,
)

STEP_TYPE_ALIASES: dict[str, str] = {}

DWH_CONSTRAINTS = {
    "dim_producto": {
        "precio_lista": {"minimum": "0", "maximum": None, "type": "number"},
    },
}


def _table_output(name: str, table: str, fields: list[dict]) -> dict:
    return {"name": name, "type": "TableOutput", "config": {"table": table, "fields": fields}}


def _dim_lookup(name: str, table: str, fields: list[dict], update: str = "Y") -> dict:
    return {
        "name": name, "type": "DimensionLookup",
        "config": {"table": table, "update": update, "keys": [{"stream": "bk", "name": "bk"}], "fields": fields},
    }


def _filter_rows(name: str, field: str, operator: str, value_type: str = "Number") -> dict:
    return {
        "name": name, "type": "FilterRows",
        "config": {"field": field, "operator": operator, "value": 0, "value_type": value_type},
    }


def _ctx(steps: list[dict], dwh_constraints: dict = DWH_CONSTRAINTS) -> ValidationContext:
    return ValidationContext({"steps": steps, "hops": []}, STEP_TYPE_ALIASES, frozenset(), dwh_constraints)


def test_no_dwh_constraints_short_circuits():
    step = _table_output("Cargar Dim Producto", "dim_producto", [
        {"column_name": "precio_lista", "stream_name": "precio_lista"},
    ])
    assert check_constraint_filter_rows(_ctx([step], dwh_constraints={})) == []


def test_bounded_column_without_filter_is_error():
    step = _table_output("Cargar Dim Producto", "dim_producto", [
        {"column_name": "precio_lista", "stream_name": "precio_lista"},
    ])
    findings = check_constraint_filter_rows(_ctx([step]))
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].message.startswith(CHECK_FILTER_PREFIX)
    assert "precio_lista" in findings[0].message


def test_bounded_column_with_matching_filter_produces_no_findings():
    steps = [
        _filter_rows("Filtrar Precios Negativos", "precio_lista", ">="),
        _table_output("Cargar Dim Producto", "dim_producto", [
            {"column_name": "precio_lista", "stream_name": "precio_lista"},
        ]),
    ]
    assert check_constraint_filter_rows(_ctx(steps)) == []


def test_filter_with_string_value_type_on_numeric_column_is_error():
    steps = [
        _filter_rows("Filtrar Precios Negativos", "precio_lista", ">=", value_type="String"),
        _table_output("Cargar Dim Producto", "dim_producto", [
            {"column_name": "precio_lista", "stream_name": "precio_lista"},
        ]),
    ]
    findings = check_constraint_filter_rows(_ctx(steps))
    assert len(findings) == 1
    assert "value_type='String'" in findings[0].message


def test_unbounded_column_produces_no_findings():
    step = _table_output("Cargar Dim Producto", "dim_producto", [
        {"column_name": "nombre_producto", "stream_name": "nombre_producto"},
    ])
    assert check_constraint_filter_rows(_ctx([step])) == []


def test_dimension_lookup_loader_is_checked():
    step = _dim_lookup("Cargar Dim Producto", "dim_producto", [
        {"table_field": "precio_lista", "stream_field": "precio_lista", "type": "Update"},
    ])
    findings = check_constraint_filter_rows(_ctx([step]))
    assert len(findings) == 1
    assert "precio_lista" in findings[0].message


def test_dimension_lookup_fact_lookup_update_n_is_ignored():
    step = _dim_lookup("Buscar FK Producto", "dim_producto", [
        {"table_field": "precio_lista", "stream_field": "precio_lista", "type": "Update"},
    ], update="N")
    assert check_constraint_filter_rows(_ctx([step])) == []
