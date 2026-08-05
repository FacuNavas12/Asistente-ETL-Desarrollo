"""
Unit tests — Fase 2-ter item 2 (S-5/H-5,
docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md):
guard_staging_layer detecta un FilterRows que alimenta, vía hops habilitados,
a un writer de tabla de staging — backstop determinista de D42. Puro/sin
LLM/sin DB.
"""
from __future__ import annotations

from app.services.ktr_builder.validators import ValidationContext
from app.services.ktr_builder.validators.guard_staging_layer import (
    STAGING_GUARD_PREFIX,
    guard_staging_layer,
)

STEP_TYPE_ALIASES: dict[str, str] = {}


def _table_input(name: str) -> dict:
    return {"name": name, "type": "TableInput", "config": {"table": "productos", "sql": "SELECT * FROM productos"}}


def _filter_rows(name: str) -> dict:
    return {"name": name, "type": "FilterRows", "config": {"field": "precio", "operator": ">=", "value": 0}}


def _table_output(name: str, table: str) -> dict:
    return {"name": name, "type": "TableOutput", "config": {"table": table, "fields": []}}


def _hop(frm: str, to: str, enabled: bool = True) -> dict:
    return {"from": frm, "to": to, "enabled": enabled}


def _ctx(steps: list[dict], hops: list[dict]) -> ValidationContext:
    return ValidationContext({"steps": steps, "hops": hops}, STEP_TYPE_ALIASES, frozenset(), {})


def test_filter_feeding_staging_writer_is_error():
    steps = [_table_input("Leer Productos"), _filter_rows("Filtrar Precios"), _table_output("Cargar Stg", "stg_producto")]
    hops = [_hop("Leer Productos", "Filtrar Precios"), _hop("Filtrar Precios", "Cargar Stg")]
    findings = guard_staging_layer(_ctx(steps, hops))
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].message.startswith(STAGING_GUARD_PREFIX)
    assert "stg_producto" in findings[0].message


def test_filter_on_unrelated_branch_produces_no_findings():
    steps = [
        _table_input("Leer Productos"), _filter_rows("Filtrar Precios"),
        _table_output("Cargar Stg", "stg_producto"), _table_output("Cargar Log", "log_errores"),
    ]
    hops = [
        _hop("Leer Productos", "Cargar Stg"),
        _hop("Leer Productos", "Filtrar Precios"), _hop("Filtrar Precios", "Cargar Log"),
    ]
    assert guard_staging_layer(_ctx(steps, hops)) == []


def test_no_filter_rows_produces_no_findings():
    steps = [_table_input("Leer Productos"), _table_output("Cargar Stg", "stg_producto")]
    hops = [_hop("Leer Productos", "Cargar Stg")]
    assert guard_staging_layer(_ctx(steps, hops)) == []


def test_filter_feeding_dwh_writer_produces_no_findings():
    steps = [_table_input("Leer Productos"), _filter_rows("Filtrar Precios"), _table_output("Cargar Dim", "dim_producto")]
    hops = [_hop("Leer Productos", "Filtrar Precios"), _hop("Filtrar Precios", "Cargar Dim")]
    assert guard_staging_layer(_ctx(steps, hops)) == []


def test_disabled_hop_breaks_reachability():
    steps = [_table_input("Leer Productos"), _filter_rows("Filtrar Precios"), _table_output("Cargar Stg", "stg_producto")]
    hops = [_hop("Leer Productos", "Filtrar Precios"), _hop("Filtrar Precios", "Cargar Stg", enabled=False)]
    assert guard_staging_layer(_ctx(steps, hops)) == []
