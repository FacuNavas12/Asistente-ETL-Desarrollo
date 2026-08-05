"""
F1.5/H6 — parse_cfg deja de degradar un config roto a `{}` en silencio
(D5: "ante la duda entre tolerar y fallar, se falla"). Fail-fast en el
parseo (ConfigParseError), pero mejor-esfuerzo en la generación completa
(D15): normalize_step_configs() es el único punto del pipeline que atrapa
esa excepción, marca el step como config vacío y emite un warning accionable
— el resto de los ~20 call-sites que leen `config` aguas abajo (build.py,
fields_validate.py, repair.py, dimension_step_policy.py, lineage_builder.py,
validate.py, ktr_default_validator.py) reciben siempre un dict ya resuelto
y no vuelven a ver la excepción.
"""
from __future__ import annotations

import pytest

from app.services.ktr_builder import build_ktr, normalize_step_configs, ConfigParseError
from app.services.ktr_builder.contracts import parse_cfg


def test_parse_cfg_raises_on_invalid_json_string():
    with pytest.raises(ConfigParseError):
        parse_cfg("{esto no es json")


def test_parse_cfg_empty_string_is_still_empty_dict():
    assert parse_cfg("") == {}
    assert parse_cfg("   ") == {}


def test_parse_cfg_dict_passthrough_unaffected():
    assert parse_cfg({"table": "dim_x"}) == {"table": "dim_x"}


def test_normalize_step_configs_replaces_broken_config_with_warning():
    ktr_data = {
        "steps": [
            {"name": "Step OK", "type": "SelectValues", "config": '{"select": [{"name": "a"}]}'},
            {"name": "Step Roto", "type": "SelectValues", "config": "{esto no es json"},
        ],
        "hops": [],
    }
    ktr_data, warnings = normalize_step_configs(ktr_data)

    ok_step = next(s for s in ktr_data["steps"] if s["name"] == "Step OK")
    broken_step = next(s for s in ktr_data["steps"] if s["name"] == "Step Roto")
    assert ok_step["config"] == {"select": [{"name": "a"}]}
    assert broken_step["config"] == {}  # degrada, pero ya no en silencio
    assert len(warnings) == 1
    assert "Step Roto" in warnings[0]
    assert "config no es JSON válido" in warnings[0]


def test_normalize_step_configs_is_idempotent_noop_on_dict_config():
    """Config ya-dict (el caso normal tras la primera normalización, o
    cualquier caller que ya arma dicts) no dispara ningún warning."""
    ktr_data = {"steps": [{"name": "s", "type": "TableOutput", "config": {"table": "t"}}], "hops": []}
    ktr_data, warnings = normalize_step_configs(ktr_data)
    assert warnings == []
    assert ktr_data["steps"][0]["config"] == {"table": "t"}


def test_build_ktr_survives_broken_config_without_crashing():
    """Defensa en profundidad: build_ktr() tiene su propio catch (build.py)
    para un caller que no haya pasado por normalize_step_configs() antes —
    no debe propagar ConfigParseError sin atrapar."""
    ktr_data = {
        "name": "Test_ETL",
        "description": "",
        "connections": [{"name": "conn_origen", "type": "POSTGRESQL"}],
        "steps": [
            {
                "name": "Renombrar Campos",
                "type": "SelectValues",
                "config": "{esto no es json",  # roto, y SelectValues no tiene critical fields
            },
        ],
        "hops": [],
    }
    ktr_xml, _filename, warnings = build_ktr(ktr_data, "Test_ETL")
    assert ktr_xml  # se generó igual (D15: mejor esfuerzo, no aborta)
    assert any("config no es JSON válido" in w for w in warnings)
