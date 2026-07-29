"""
Unit tests — H29 (docs/refactor/01-hallazgos.md), D40 (docs/refactor/02-decisiones.md):
recuperación determinista de la clave 'table' cuando el LLM la declaró bajo un
nombre no cubierto por contracts.STEP_CONTRACTS.key_aliases. Puro/sin LLM/sin
DB, mismo espíritu que test_scd_policy.py.
"""
from __future__ import annotations

from app.services.ktr_builder.validators import ValidationContext, run_passes
from app.services.ktr_builder.validators.table_key_recovery import recover_table_key

STEP_TYPE_ALIASES: dict[str, str] = {}  # los steps de este test ya usan el tipo canónico


def _step(name: str, type_: str, config: dict) -> dict:
    return {"name": name, "type": type_, "config": config}


def test_recovers_table_from_unknown_key_by_content_match():
    """'schema_table' no es un alias conocido de TableOutput — pero su valor
    coincide con una tabla real conocida, así que se renombra a 'table'."""
    ktr_data = {"steps": [
        _step("Cargar Ventas", "TableOutput", {"schema_table": "fact_venta", "fields": []}),
    ]}
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset({"fact_venta", "dim_producto"}))
    findings = recover_table_key(ctx)

    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].repaired is True
    assert findings[0].step_name == "Cargar Ventas"

    cfg = ktr_data["steps"][0]["config"]
    assert cfg["table"] == "fact_venta"
    assert "schema_table" not in cfg


def test_table_already_present_is_noop():
    ktr_data = {"steps": [
        _step("Cargar Ventas", "TableOutput", {"table": "fact_venta", "fields": []}),
    ]}
    before = dict(ktr_data["steps"][0]["config"])
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset({"fact_venta"}))
    findings = recover_table_key(ctx)

    assert findings == []
    assert ktr_data["steps"][0]["config"] == before


def test_running_pass_twice_is_idempotent():
    ktr_data = {"steps": [
        _step("Cargar Ventas", "TableOutput", {"schema_table": "fact_venta", "fields": []}),
    ]}
    known = frozenset({"fact_venta"})
    findings_1 = recover_table_key(ValidationContext(ktr_data, STEP_TYPE_ALIASES, known))
    findings_2 = recover_table_key(ValidationContext(ktr_data, STEP_TYPE_ALIASES, known))

    assert len(findings_1) == 1
    assert findings_2 == []
    assert ktr_data["steps"][0]["config"]["table"] == "fact_venta"


def test_no_candidate_matches_reports_error_without_mutating():
    ktr_data = {"steps": [
        _step("Cargar Ventas", "TableOutput", {"schema_table": "tabla_inexistente", "fields": []}),
    ]}
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset({"fact_venta", "dim_producto"}))
    findings = recover_table_key(ctx)

    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].repaired is False
    assert "table" not in ktr_data["steps"][0]["config"]


def test_ambiguous_candidates_reports_error_without_guessing():
    """Dos claves del mismo step matchean tablas reales distintas — no se
    adivina cuál es la correcta."""
    ktr_data = {"steps": [
        _step("Buscar SK", "DBLookup", {
            "origen_ref": "dim_cliente", "otro_ref": "dim_producto",
            "keys": [{"stream_field": "x", "lookup_field": "y"}],
            "return_fields": [{"name": "sk", "rename": "sk"}],
        }),
    ]}
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset({"dim_cliente", "dim_producto"}))
    findings = recover_table_key(ctx)

    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].repaired is False
    assert "table" not in ktr_data["steps"][0]["config"]


def test_step_outside_table_bearing_types_is_untouched():
    """Calculator no tiene tabla física — aunque un campo suyo coincida por
    casualidad con un nombre de tabla real, no se toca."""
    ktr_data = {"steps": [
        _step("Calcular", "Calculator", {
            "calculations": [{"field_name": "dim_producto", "calc_type": "ADD", "field_a": "a", "field_b": "b"}],
        }),
    ]}
    before = dict(ktr_data["steps"][0]["config"])
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset({"dim_producto"}))
    findings = recover_table_key(ctx)

    assert findings == []
    assert ktr_data["steps"][0]["config"] == before


def test_run_passes_repaired_findings_match_real_mutation():
    """Contrato hacia afuera: todo Finding con repaired=True corresponde a
    una mutación real de ktr_data (ver base.py — invariante D5/D15)."""
    ktr_data = {"steps": [
        _step("Cargar Ventas", "TableOutput", {"schema_table": "fact_venta", "fields": []}),
        _step("Cargar Producto", "DimensionLookup", {
            "target_table": "dim_producto",
            "keys": [{"stream_field": "id_producto", "table_field": "bk_producto"}],
        }),
    ]}
    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset({"fact_venta", "dim_producto"}))
    findings = run_passes(ctx)

    # "Cargar Producto" ya resuelve vía key_aliases conocido (target_table),
    # no genera Finding — solo "Cargar Ventas" necesita la recuperación por
    # contenido (schema_table no está en key_aliases de TableOutput).
    repaired = [f for f in findings if f.repaired]
    assert len(repaired) == 1
    assert repaired[0].step_name == "Cargar Ventas"
    assert ktr_data["steps"][0]["config"]["table"] == "fact_venta"
    assert ktr_data["steps"][1]["config"]["table"] == "dim_producto"
