"""
Unit tests — H40 (docs/refactor/01-hallazgos.md), D41 (docs/refactor/02-decisiones.md):
Calculator agrega un campo que ningún step aguas abajo consume ni mapea a
tabla destino -> warning, sin mutar ktr_data. Puro/sin LLM/sin DB, mismo
espíritu que test_table_key_recovery.py.
"""
from __future__ import annotations

from app.services.ktr_builder.validators import ValidationContext, run_passes
from app.services.ktr_builder.validators.dead_computed_fields import flag_dead_computed_fields

STEP_TYPE_ALIASES: dict[str, str] = {}


def _step(name: str, type_: str, config: dict) -> dict:
    return {"name": name, "type": type_, "config": config}


def _hop(from_: str, to: str) -> dict:
    return {"from": from_, "to": to}


def test_calculated_field_never_consumed_downstream_reports_warning():
    ktr_data = {
        "steps": [
            _step("Calcular Valor Inventario", "Calculator", {
                "calculations": [{"field_name": "valor_inventario", "calc_type": "MULTIPLY",
                                   "field_a": "precio", "field_b": "stock"}],
            }),
            _step("Cargar stg_producto", "TableOutput", {
                "table": "stg_producto",
                "fields": [{"stream_name": "precio", "table_field": "precio"}],
            }),
        ],
        "hops": [_hop("Calcular Valor Inventario", "Cargar stg_producto")],
    }
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset())
    findings = flag_dead_computed_fields(ctx)

    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].repaired is False
    assert findings[0].step_name == "Calcular Valor Inventario"
    assert "valor_inventario" in findings[0].message
    # no mutación: el finding es aviso, no reparación
    assert ktr_data["steps"][0]["config"]["calculations"][0]["field_name"] == "valor_inventario"


def test_calculated_field_mapped_to_table_output_is_not_flagged():
    ktr_data = {
        "steps": [
            _step("Calcular Valor Inventario", "Calculator", {
                "calculations": [{"field_name": "valor_inventario", "calc_type": "MULTIPLY",
                                   "field_a": "precio", "field_b": "stock"}],
            }),
            _step("Cargar stg_producto", "TableOutput", {
                "table": "stg_producto",
                "fields": [{"stream_name": "valor_inventario", "table_field": "valor_inventario"}],
            }),
        ],
        "hops": [_hop("Calcular Valor Inventario", "Cargar stg_producto")],
    }
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset())
    findings = flag_dead_computed_fields(ctx)

    assert findings == []


def test_calculated_field_used_as_lookup_key_further_downstream_is_not_flagged():
    """El campo no se mapea a ninguna tabla, pero sí lo consume un DBLookup
    más adelante en el grafo — no es cómputo muerto."""
    ktr_data = {
        "steps": [
            _step("Calcular Categoria Precio", "Calculator", {
                "calculations": [{"field_name": "categoria_precio", "calc_type": "ROUND",
                                   "field_a": "precio"}],
            }),
            _step("Pasar", "SelectValues", {}),
            _step("Buscar SK", "DBLookup", {
                "table": "dim_categoria",
                "keys": [{"stream_field": "categoria_precio", "lookup_field": "nombre"}],
                "return_fields": [{"name": "sk", "rename": "sk"}],
            }),
        ],
        "hops": [_hop("Calcular Categoria Precio", "Pasar"), _hop("Pasar", "Buscar SK")],
    }
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset())
    findings = flag_dead_computed_fields(ctx)

    assert findings == []


def test_field_removed_from_result_is_not_flagged():
    """removed_from_result=Y: el propio Calculator lo descarta del stream a
    propósito (campo auxiliar de cálculo intermedio) — no es el caso que
    describe H40."""
    ktr_data = {
        "steps": [
            _step("Calcular", "Calculator", {
                "calculations": [{"field_name": "auxiliar", "calc_type": "ADD",
                                   "field_a": "a", "field_b": "b", "removed_from_result": "Y"}],
            }),
        ],
        "hops": [],
    }
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset())
    findings = flag_dead_computed_fields(ctx)

    assert findings == []


def test_non_calculator_steps_are_ignored():
    ktr_data = {
        "steps": [
            _step("Constante", "Constant", {"fields": [{"name": "stg_origen", "value": "productos"}]}),
        ],
        "hops": [],
    }
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset())
    findings = flag_dead_computed_fields(ctx)

    assert findings == []


def test_disabled_hop_does_not_count_as_reachable():
    ktr_data = {
        "steps": [
            _step("Calcular", "Calculator", {
                "calculations": [{"field_name": "valor_inventario", "calc_type": "MULTIPLY",
                                   "field_a": "precio", "field_b": "stock"}],
            }),
            _step("Cargar", "TableOutput", {
                "table": "stg_producto",
                "fields": [{"stream_name": "valor_inventario", "table_field": "valor_inventario"}],
            }),
        ],
        "hops": [{"from": "Calcular", "to": "Cargar", "enabled": False}],
    }
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset())
    findings = flag_dead_computed_fields(ctx)

    assert len(findings) == 1
    assert findings[0].step_name == "Calcular"


def test_run_passes_includes_dead_computed_field_warning():
    """Contrato hacia afuera: run_passes() (el default de PRE_EMIT_PASSES)
    incluye este pass junto a recover_table_key, sin que uno pise al otro."""
    ktr_data = {
        "steps": [
            _step("Cargar Ventas", "TableOutput", {"schema_table": "fact_venta", "fields": []}),
            _step("Calcular", "Calculator", {
                "calculations": [{"field_name": "valor_inventario", "calc_type": "MULTIPLY",
                                   "field_a": "precio", "field_b": "stock"}],
            }),
        ],
        "hops": [],
    }
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset({"fact_venta"}))
    findings = run_passes(ctx)

    by_step = {f.step_name: f for f in findings}
    assert "Cargar Ventas" in by_step
    assert "Calcular" in by_step
    assert by_step["Cargar Ventas"].message.startswith("[Clave de tabla] ")
    assert by_step["Calcular"].message.startswith("[Cómputo sin consumidor] ")
