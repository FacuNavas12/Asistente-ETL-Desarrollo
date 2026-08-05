"""
Unit tests — R-K7 (docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md,
D51): check_insert_update_bypass reporta la combinación contradictoria
update_bypassed=N EXPLÍCITO + cero <value> con update=Y, que hace que Kettle
arme un 'UPDATE ... SET' vacío y falle en la primera fila
(InsertUpdateMeta.prepareUpdate()). Puro/sin LLM/sin DB.
"""
from __future__ import annotations

from app.services.ktr_builder.validators import ValidationContext
from app.services.ktr_builder.validators.insert_update_bypass import (
    INSERT_UPDATE_BYPASS_PREFIX,
    check_insert_update_bypass,
)

STEP_TYPE_ALIASES: dict[str, str] = {}


def _insert_update(name: str, config: dict) -> dict:
    return {"name": name, "type": "InsertUpdate", "config": config}


def _ctx(steps: list[dict]) -> ValidationContext:
    return ValidationContext({"steps": steps, "hops": []}, STEP_TYPE_ALIASES, frozenset())


def test_no_explicit_update_bypassed_is_not_flagged():
    """Sin declaración explícita, el emisor (steps/output.py) decide un
    default seguro — este pass solo cubre la contradicción EXPLÍCITA."""
    step = _insert_update("Cargar Fact", {
        "table": "fact_x", "fields": [{"table_field": "monto", "stream_field": "monto", "update": False}],
    })
    assert check_insert_update_bypass(_ctx([step])) == []


def test_explicit_bypass_n_with_zero_updatable_values_is_error():
    step = _insert_update("Cargar Fact", {
        "table": "fact_x", "update_bypassed": "N",
        "fields": [{"table_field": "monto", "stream_field": "monto", "update": False}],
    })
    findings = check_insert_update_bypass(_ctx([step]))
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].message.startswith(INSERT_UPDATE_BYPASS_PREFIX)


def test_explicit_bypass_n_with_at_least_one_updatable_value_is_fine():
    step = _insert_update("Cargar Fact", {
        "table": "fact_x", "update_bypassed": "N",
        "fields": [{"table_field": "monto", "stream_field": "monto", "update": True}],
    })
    assert check_insert_update_bypass(_ctx([step])) == []


def test_explicit_bypass_y_is_never_flagged():
    step = _insert_update("Cargar Fact", {
        "table": "fact_x", "update_bypassed": "Y",
        "fields": [{"table_field": "monto", "stream_field": "monto", "update": False}],
    })
    assert check_insert_update_bypass(_ctx([step])) == []


def test_other_step_types_are_ignored():
    step = {"name": "Cargar Dim", "type": "DimensionLookup", "config": {"table": "dim_x"}}
    assert check_insert_update_bypass(_ctx([step])) == []
