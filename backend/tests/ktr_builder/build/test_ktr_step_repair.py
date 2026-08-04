"""repair_ktr_steps: reparación dirigida de config incompleto (STEP_CONTRACTS.required_keys)
antes de llegar a build_ktr(). Cubre:
  1. Step incompleto que el LLM stub corrige en el primer intento.
  2. Step que sigue incompleto tras agotar max_retries -> warning + build_ktr()
     emite el step tal cual y reporta Finding(error) (D60, Sitio 1) — el repair
     loop no repara nada nuevo, solo deja de reintentar.
  3. Step ya completo -> no dispara ninguna llamada al LLM.
"""
from __future__ import annotations

import asyncio

from unittest.mock import MagicMock

from app.models.llm_base import BaseLLM, LLMResponse
from app.services.ktr_builder import build_ktr
from app.services.ktr_builder.repair import repair_ktr_steps
from app.services.ktr_builder.validators import PRE_EMIT_ERROR_PREFIX


def _run(coro):
    return asyncio.run(coro)


def _stub_llm(responses: list[dict | None]) -> BaseLLM:
    """Devuelve, en orden, un json_data distinto por llamada. None simula una
    respuesta no-dict (el caller la trata como intento fallido)."""
    calls = {"n": 0}

    async def _complete(prompt, system, schema=None):
        i = calls["n"]
        calls["n"] += 1
        data = responses[i] if i < len(responses) else responses[-1]
        return LLMResponse(content="", json_data=data, model="test", input_tokens=1, output_tokens=1, provider="test")

    llm = MagicMock(spec=BaseLLM)
    llm.complete = _complete
    llm._calls = calls
    return llm


def _ktr_with_calculator(cfg: dict) -> dict:
    return {
        "name": "Test",
        "description": "",
        "connections": [],
        "steps": [
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT monto FROM stg_ventas"}},
            {"name": "Convertir a USD", "type": "Calculator", "config": cfg},
        ],
        "hops": [{"from": "In", "to": "Convertir a USD"}],
    }


def test_repair_fixes_step_on_first_attempt():
    llm = _stub_llm([
        {"calculations": [{"field_name": "monto_usd", "calc_type": "MULTIPLY", "field_a": "monto", "field_b": "40"}]},
    ])
    ktr = _ktr_with_calculator({"calculations": []})

    fixed, warnings = _run(repair_ktr_steps(ktr, llm, context_text=""))

    assert warnings == []
    calc_step = next(s for s in fixed["steps"] if s["name"] == "Convertir a USD")
    assert calc_step["config"]["calculations"]
    # build_ktr ya no debe abortar con este step reparado
    build_ktr(fixed)


def test_repair_gives_up_after_max_retries_and_build_reports_error_not_abort():
    # El stub siempre devuelve un config igual de incompleto -> nunca converge.
    llm = _stub_llm([{"calculations": []}])
    ktr = _ktr_with_calculator({"calculations": []})

    fixed, warnings = _run(repair_ktr_steps(ktr, llm, context_text="", max_retries=2))

    assert len(warnings) == 1
    assert "Convertir a USD" in warnings[0]
    assert llm._calls["n"] == 2  # respetó max_retries, no reintentó infinito

    # D60 (Sitio 1, docs/refactor/02-decisiones.md): el repair loop sigue sin
    # reemplazar nada — build_ktr() ya no aborta, emite el step tal cual +
    # Finding(error).
    _, _, build_warnings = build_ktr(fixed)
    assert any(
        w.startswith(PRE_EMIT_ERROR_PREFIX) and "'Convertir a USD'" in w and "no declara calculations" in w
        for w in build_warnings
    )


def test_repair_skips_already_complete_step():
    llm = _stub_llm([])  # si se llama, IndexError -> el test falla
    ktr = _ktr_with_calculator({"calculations": [{"field_name": "monto_usd", "calc_type": "MULTIPLY", "field_a": "monto", "field_b": "40"}]})

    fixed, warnings = _run(repair_ktr_steps(ktr, llm, context_text=""))

    assert warnings == []
    assert llm._calls["n"] == 0
