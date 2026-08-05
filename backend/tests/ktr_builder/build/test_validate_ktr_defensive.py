"""
F5/H12 — `_validate_ktr` (validate.py) accedía a `s["name"]`/`s["type"]` con
bracket directo mientras el resto de la función ya usaba `.get()` en todo
lado (hops, steps de Calculator/TableInput). Un step sin esas claves no
debería pasar el schema del LLM en producción, pero la función es de
mejor-esfuerzo (D15: warnings, nunca aborta) — no tiene sentido que sea la
única rama de todo el archivo que puede lanzar KeyError.
"""
from __future__ import annotations

from app.services.ktr_builder.validate import _validate_ktr


def test_step_missing_name_does_not_raise():
    ktr = {
        "steps": [{"type": "TableInput", "config": "{}"}],
        "hops": [],
    }
    warnings = _validate_ktr(ktr)
    assert isinstance(warnings, list)


def test_step_missing_type_does_not_raise():
    ktr = {
        "steps": [{"name": "Step sin tipo", "config": "{}"}],
        "hops": [],
    }
    warnings = _validate_ktr(ktr)
    assert isinstance(warnings, list)
    assert any("entrada" in w for w in warnings)
    assert any("salida" in w for w in warnings)


def test_normal_ktr_still_detects_missing_input_and_output():
    ktr = {
        "steps": [{"name": "Solo Calculator", "type": "Calculator", "config": "{}"}],
        "hops": [],
    }
    warnings = _validate_ktr(ktr)
    assert any("entrada" in w for w in warnings)
    assert any("salida" in w for w in warnings)
