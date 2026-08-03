"""_repair_dimension_loader_fields (etl_generator.py) — repair dirigido para
el finding 'repairable' de enforce_dimension_step_policy (hallazgo en
01-hallazgos.md, corpus real etl-llm-raw-test-01_sonnet_fase4.json). Cubre:
  1. Repair exitoso (cubre el mapeo, verificado contra el stream) -> step
     reclasificado a loader, mapeo visible como finding info.
  2. Repair insuficiente tras agotar reintentos -> step intacto, piso de hoy.
  3. Sin candidatos 'repairable' -> cero llamadas al LLM.
Mismo patrón asyncio.run() que test_ktr_step_repair.py — sin pytest-asyncio.
"""
from __future__ import annotations

import asyncio

from unittest.mock import MagicMock

import app.services.etl_generator as eg
from app.models.llm_base import BaseLLM
from app.services.ktr_builder.dimension_step_policy import enforce_dimension_step_policy
from app.services.ktr_builder.step_types import STEP_TYPE_ALIASES

from tests.test_dimension_step_policy import _dim_producto_contract, _dim_producto_ktr_with_stream


def _run(coro):
    return asyncio.run(coro)


def test_repair_dimension_loader_fields_success(monkeypatch):
    async def _fake_repair_step_config(step_name, canonical, cfg, missing, context_text, llm):
        assert canonical == "DimensionLookup"
        # Alcance de autoridad: el caller solo debe leer 'fields' de acá —
        # agrego 'keys'/'table' de más para confirmar que se descartan.
        return {
            "table": "otra_tabla_que_no_deberia_usarse",
            "keys": [{"stream_field": "x", "table_field": "y"}],
            "fields": [{"table_field": "nombre_categoria", "stream_field": "categoria", "type": "Update"}],
        }

    monkeypatch.setattr(eg, "repair_step_config", _fake_repair_step_config)

    ktr_data = _dim_producto_ktr_with_stream()
    contracts = [_dim_producto_contract()]
    llm = MagicMock(spec=BaseLLM)

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])
    assert any(r.get("repairable") for r in results)

    final = _run(eg._repair_dimension_loader_fields(ktr_data, contracts, results, [], llm))

    assert not any(r.get("repairable") for r in final)  # el finding original quedó obsoleto
    step = next(s for s in ktr_data["steps"] if s["name"] == "Cargar dim_producto")
    assert step["config"]["update"] == "Y"
    by_dest = {f["table_field"]: f["stream_field"] for f in step["config"]["fields"]}
    assert by_dest["nombre_categoria"] == "categoria"   # mapeo del repair, no identidad
    assert by_dest["nombre_producto"] == "nombre_producto"
    # Alcance de autoridad: 'table'/'keys' del repair NO se usaron — la tabla
    # y las keys del step siguen siendo las originales.
    assert step["config"]["table"] == "dim_producto"
    assert step["config"]["keys"] == [{"stream_field": "cod_producto", "table_field": "id_producto_origen"}]
    assert any(r["tipo"] == "info" for r in final)  # mapeo inferido, visible


def test_repair_dimension_loader_fields_floor_when_gate_fails(monkeypatch):
    """El repair propone un stream_field que no existe de verdad en el
    stream (alucinación) — el gate lo rechaza en TODOS los intentos, el
    step queda intacto y el finding 'repairable' original sobrevive: mismo
    piso que antes de este cambio (build_ktr aborta más abajo)."""
    calls = {"n": 0}

    async def _fake_repair_step_config(step_name, canonical, cfg, missing, context_text, llm):
        calls["n"] += 1
        return {"fields": [{"table_field": "nombre_categoria", "stream_field": "campo_inexistente"}]}

    monkeypatch.setattr(eg, "repair_step_config", _fake_repair_step_config)

    ktr_data = _dim_producto_ktr_with_stream()
    contracts = [_dim_producto_contract()]
    llm = MagicMock(spec=BaseLLM)

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])
    final = _run(eg._repair_dimension_loader_fields(ktr_data, contracts, results, [], llm))

    assert final == results  # sin cambios
    step = next(s for s in ktr_data["steps"] if s["name"] == "Cargar dim_producto")
    assert step["config"]["update"] == "N"  # intacto
    assert calls["n"] == 2  # max_retries default (2), agotados


def test_repair_dimension_loader_fields_noop_without_candidates(monkeypatch):
    calls = {"n": 0}

    async def _counting(*a, **kw):
        calls["n"] += 1
        return None

    monkeypatch.setattr(eg, "repair_step_config", _counting)
    llm = MagicMock(spec=BaseLLM)

    final = _run(eg._repair_dimension_loader_fields({"steps": [], "hops": []}, [], [], [], llm))

    assert final == []
    assert calls["n"] == 0


def test_repair_dimension_loader_fields_noop_without_llm(monkeypatch):
    calls = {"n": 0}

    async def _counting(*a, **kw):
        calls["n"] += 1
        return None

    monkeypatch.setattr(eg, "repair_step_config", _counting)

    ktr_data = _dim_producto_ktr_with_stream()
    contracts = [_dim_producto_contract()]
    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    final = _run(eg._repair_dimension_loader_fields(ktr_data, contracts, results, [], None))

    assert final == results
    assert calls["n"] == 0
