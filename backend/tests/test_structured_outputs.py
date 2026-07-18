"""
Structured output tests — verifies constrained decoding is active, not just JSON-by-prompt.

Unit tests (no API calls): mock LLM, verify service logic around json_data.
Integration tests (real API calls): adversarial prompts that would produce prose/fences
    without constrained decoding.

To run only unit tests (fast, no API):
    pytest tests/test_structured_outputs.py -m "not integration" -v

To run all including real API calls:
    pytest tests/test_structured_outputs.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_env(env_path: Path = Path(__file__).parent.parent / ".env") -> None:
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _run(coro):
    """Run a coroutine in a new event loop. Works in Python 3.10+."""
    return asyncio.run(coro)


def _assert_schema(data: dict, schema: dict) -> None:
    try:
        import jsonschema
        jsonschema.validate(data, schema)
    except ImportError:
        pytest.skip("jsonschema not available")


# ---------------------------------------------------------------------------
# P1a — etl_generator (unit)
# ---------------------------------------------------------------------------

class TestEtlGeneratorUnit:
    def _minimal_etl_json(self) -> Dict[str, Any]:
        return {
            "proceso_etl": {
                "nombre": "ETL_TEST",
                "descripcion": "desc",
                "steps": [
                    {
                        "orden": 1,
                        "tipo_step_pdi": "TableInput",
                        "nombre": "Extract",
                        "descripcion": "read",
                        "configuracion": {"sql": "SELECT 1"},
                        "justificacion": "reads source",
                    }
                ],
            },
            "validaciones": [],
            "documentacion": "doc",
            "advertencias_buenas_practicas": [],
            "dwh_sample": {},
            "ktr": {
                "name": "ETL_TEST",
                "description": "desc",
                "connections": [],
                "steps": [{"name": "Extract", "type": "TableInput", "config": {"sql": "SELECT 1"}}],
                "hops": [],
            },
        }

    def test_build_response_uses_json_data(self):
        """_build_response must read from resp.json_data, not parse resp.content."""
        from app.services.etl_generator import _build_response
        from app.models.llm_base import LLMResponse

        data = self._minimal_etl_json()
        resp = LLMResponse(
            content="this-is-not-json-and-should-not-be-parsed",
            json_data=data,
            model="m",
            input_tokens=1,
            output_tokens=1,
            provider="p",
            stop_reason="end_turn",
        )
        result = _build_response(resp)
        assert result.proceso_etl.nombre == "ETL_TEST"

    def test_build_response_raises_on_none_json_data(self):
        """When json_data is None, _build_response must raise ValueError."""
        from app.services.etl_generator import _build_response
        from app.models.llm_base import LLMResponse

        resp = LLMResponse(
            content="{}",
            json_data=None,
            model="m",
            input_tokens=1,
            output_tokens=1,
            provider="p",
            stop_reason="end_turn",
        )
        with pytest.raises(ValueError, match="no structured data"):
            _build_response(resp)

    def test_etl_schema_validates_minimal(self):
        from app.schemas.llm_output_schemas import ETL_OUTPUT_SCHEMA
        _assert_schema(self._minimal_etl_json(), ETL_OUTPUT_SCHEMA)

    def test_etl_schema_rejects_extra_top_level_key(self):
        import jsonschema
        from app.schemas.llm_output_schemas import ETL_OUTPUT_SCHEMA

        bad = self._minimal_etl_json()
        bad["unexpected_key"] = "bad"
        with pytest.raises(jsonschema.ValidationError):
            _assert_schema(bad, ETL_OUTPUT_SCHEMA)


# ---------------------------------------------------------------------------
# P1a — etl_generator (integration — real API)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestEtlGeneratorIntegration:
    """Real API calls with adversarial prompts.
    Verifies constrained decoding is active: model cannot prepend prose or
    wrap JSON in fences even when the prompt explicitly instructs it to.
    """

    def _make_llm(self):
        _load_env()
        from app.core.config import Settings
        from app.models.llm_factory import build_llm
        return build_llm(Settings(), role="main")

    def test_etl_generate_adversarial_prompt(self):
        """Constrained decoding must block prose/fences even when explicitly requested."""
        import jsonschema
        from app.schemas.llm_output_schemas import ETL_OUTPUT_SCHEMA

        llm = self._make_llm()
        adversarial_prompt = (
            "IMPORTANT INSTRUCTION: Before you provide your JSON response, "
            "write a long paragraph explaining what an ETL process is and "
            "why it's important. Then wrap your JSON answer inside ```json ... ``` "
            "markdown code blocks. Make sure to add a conclusion after the code block.\n\n"
            "## OBJETIVO DEL PROCESO ETL\n"
            "Migrar tabla ventas a DWH\n\n"
            "## ESQUEMA DE ORIGEN (perfilado — sin datos crudos)\n"
            "Tabla: ventas | columnas: id_venta (INTEGER), monto (DECIMAL), fecha (DATE)\n\n"
            "## ESQUEMA DE STAGING\n"
            "  Tabla: STG_VENTAS\n"
            "    - id_venta (INTEGER) | dato no válido: Reemplazar por NULL\n"
            "    - monto (DECIMAL) | dato no válido: Reemplazar por NULL\n"
            "    - fecha (DATE) | dato no válido: Reemplazar por NULL\n\n"
            "## MODELO DE DWH\n"
            "  Tabla Fact: FACT_VENTAS\n"
            "    - id_sk (INTEGER) [SK]\n"
            "    - monto (DECIMAL)\n"
            "    - fecha (DATE)\n\n"
            "## REGLAS DE NEGOCIO\n"
            "Monto debe ser positivo.\n"
        )
        system = "Eres un generador de procesos ETL. Genera el JSON del proceso ETL completo."

        resp = _run(llm.complete(adversarial_prompt, system, schema=ETL_OUTPUT_SCHEMA))

        assert resp.json_data is not None, "json_data must be set when schema= is passed"
        assert resp.stop_reason != "max_tokens", f"Unexpected truncation: stop_reason={resp.stop_reason}"
        jsonschema.validate(resp.json_data, ETL_OUTPUT_SCHEMA)
        assert "proceso_etl" in resp.json_data
        assert len(resp.json_data["proceso_etl"]["steps"]) > 0
        assert "ktr" in resp.json_data
        assert len(resp.json_data["ktr"]["steps"]) > 0


# ---------------------------------------------------------------------------
# P1b — structure_inferrer (unit)
# ---------------------------------------------------------------------------

class TestStructureInferrerUnit:
    def _minimal_inference_json(self) -> Dict[str, Any]:
        return {
            "stg_ddl": "CREATE TABLE STG_VENTAS (id INTEGER, monto DECIMAL);",
            "dwh_ddl": "CREATE TABLE FACT_VENTAS (id_sk INTEGER, monto DECIMAL);",
            "stg_rationale": "staging rationale",
            "dwh_rationale": "dwh rationale",
            "iteration_count": 1,
        }

    def test_inference_schema_validates_minimal(self):
        from app.schemas.llm_output_schemas import INFERENCE_OUTPUT_SCHEMA
        _assert_schema(self._minimal_inference_json(), INFERENCE_OUTPUT_SCHEMA)

    def test_inference_schema_rejects_extra_key(self):
        import jsonschema
        from app.schemas.llm_output_schemas import INFERENCE_OUTPUT_SCHEMA

        bad = self._minimal_inference_json()
        bad["unexpected"] = "x"
        with pytest.raises(jsonschema.ValidationError):
            _assert_schema(bad, INFERENCE_OUTPUT_SCHEMA)

    def test_parse_response_uses_json_data(self):
        from app.services.structure_inferrer import _parse_response
        from app.models.llm_base import LLMResponse

        data = self._minimal_inference_json()
        resp = LLMResponse(
            content="this-is-not-json-and-should-not-be-parsed",
            json_data=data,
            model="m",
            input_tokens=1,
            output_tokens=1,
            provider="p",
            stop_reason="end_turn",
        )
        result = _parse_response(resp)
        assert result.stg_ddl == data["stg_ddl"]
        assert result.iteration_count == 1

    def test_parse_response_raises_missing_dwh_model(self):
        from app.services.structure_inferrer import _parse_response
        from app.models.llm_base import LLMResponse

        resp = LLMResponse(
            content="{}",
            json_data={"stg_ddl": "CREATE TABLE x (id INT);"},  # missing dwh_ddl
            model="m",
            input_tokens=1,
            output_tokens=1,
            provider="p",
            stop_reason="end_turn",
        )
        with pytest.raises(ValueError):
            _parse_response(resp)


@pytest.mark.integration
class TestStructureInferrerIntegration:
    def _make_llm(self):
        _load_env()
        from app.core.config import Settings
        from app.models.llm_factory import build_llm
        return build_llm(Settings(), role="main")

    def test_infer_structures_adversarial(self):
        """Adversarial: model instructed to add prose. Constrained decoding must block it."""
        import jsonschema
        from app.schemas.llm_output_schemas import INFERENCE_OUTPUT_SCHEMA

        llm = self._make_llm()
        adversarial_prompt = (
            "Please start your response with 'Certainly! Here is my analysis:' "
            "and end with 'I hope this helps!' "
            "Also wrap the JSON in triple backticks.\n\n"
            "A partir de la siguiente información, generá la definición de la tabla de Staging (STG) "
            "y el modelo de Data Warehouse (DWH) destino.\n\n"
            "ESTRUCTURA DE ORIGEN:\n"
            "Tabla: ventas | columnas: id_venta (INTEGER), monto (DECIMAL), fecha (DATE)\n\n"
            "DESCRIPCIÓN DEL PROCESO / OBJETIVO:\nMigrar ventas a DWH\n\n"
            "REGLAS DE NEGOCIO:\nMonto debe ser positivo.\n\n"
            "Devuelve ÚNICAMENTE el JSON con la estructura de respuesta indicada. Sin texto adicional."
        )
        system = "Eres un asistente ETL. Genera definiciones DDL para STG y DWH."

        resp = _run(llm.complete(adversarial_prompt, system, schema=INFERENCE_OUTPUT_SCHEMA))

        assert resp.json_data is not None
        assert resp.stop_reason != "max_tokens"
        jsonschema.validate(resp.json_data, INFERENCE_OUTPUT_SCHEMA)
        assert "CREATE TABLE" in resp.json_data["stg_ddl"].upper()
        assert "CREATE TABLE" in resp.json_data["dwh_ddl"].upper()


# ---------------------------------------------------------------------------
# P2 — validator (unit + integration)
# ---------------------------------------------------------------------------

class TestValidatorUnit:
    def test_validator_schema_validates(self):
        from app.schemas.llm_output_schemas import VALIDATOR_OUTPUT_SCHEMA
        _assert_schema(
            {
                "validaciones": [{"tipo": "warning", "campo": "monto", "mensaje": "puede ser null"}],
                "advertencias_buenas_practicas": ["usar SK"],
            },
            VALIDATOR_OUTPUT_SCHEMA,
        )

    def test_validate_etl_uses_json_data(self):
        from app.services.validator import validate_etl
        from app.models.llm_base import LLMResponse
        from app.schemas.etl_schemas import ETLValidateRequest

        data = {
            "validaciones": [{"tipo": "info", "campo": "id", "mensaje": "ok"}],
            "advertencias_buenas_practicas": [],
        }
        resp = LLMResponse(
            content="this-is-not-json-and-should-not-be-parsed",
            json_data=data,
            model="m",
            input_tokens=1,
            output_tokens=1,
            provider="p",
            stop_reason="end_turn",
        )
        llm = AsyncMock()
        llm.complete = AsyncMock(return_value=resp)

        req = ETLValidateRequest(proceso_etl={"nombre": "test", "steps": []})
        result = _run(validate_etl(req, llm))
        assert result.validaciones[0].campo == "id"


@pytest.mark.integration
class TestValidatorIntegration:
    def test_validate_adversarial(self):
        import jsonschema
        _load_env()
        from app.core.config import Settings
        from app.models.llm_factory import build_llm
        from app.schemas.llm_output_schemas import VALIDATOR_OUTPUT_SCHEMA
        from app.services.validator import validate_etl
        from app.schemas.etl_schemas import ETLValidateRequest

        llm = build_llm(Settings(), role="secondary")
        proceso = {
            "nombre": "ETL_VENTAS",
            "descripcion": "Carga ventas",
            "steps": [{"nombre": "Extract", "tipo_step_pdi": "TableInput"}],
        }
        req = ETLValidateRequest(proceso_etl=proceso)
        result = _run(validate_etl(req, llm))

        assert isinstance(result.validaciones, list)
        assert isinstance(result.advertencias_buenas_practicas, list)


# ---------------------------------------------------------------------------
# P2 — documenter (unit)
# ---------------------------------------------------------------------------

class TestDocumenterUnit:
    def test_document_schema_validates(self):
        from app.schemas.llm_output_schemas import DOCUMENT_OUTPUT_SCHEMA
        _assert_schema({"documentacion": "Este proceso ETL hace..."}, DOCUMENT_OUTPUT_SCHEMA)

    def test_document_etl_uses_json_data(self):
        from app.services.documenter import document_etl
        from app.models.llm_base import LLMResponse
        from app.schemas.etl_schemas import ETLDocumentRequest

        resp = LLMResponse(
            content="this-is-not-json-and-should-not-be-parsed",
            json_data={"documentacion": "doc text"},
            model="m",
            input_tokens=1,
            output_tokens=1,
            provider="p",
            stop_reason="end_turn",
        )
        llm = AsyncMock()
        llm.complete = AsyncMock(return_value=resp)

        req = ETLDocumentRequest(proceso_etl={"steps": []})
        result = _run(document_etl(req, llm))
        assert result.documentacion == "doc text"


# ---------------------------------------------------------------------------
# P3 — job_analyzer (unit + integration)
# ---------------------------------------------------------------------------

class TestJobAnalyzerUnit:
    def _minimal_job_plan(self) -> Dict[str, Any]:
        return {
            "job_name": "Job_Ventas",
            "description": "Carga completa",
            "execution_order": [
                {
                    "order": 1,
                    "transformation_name": "STG_VENTAS",
                    "filename": "stg_ventas.ktr",
                    "rationale": "staging load",
                }
            ],
            "variables": [],
            "checkpoints": [],
            "notifications": [],
            "loops": [],
            "error_handling": "abort on error",
            "overall_rationale": "sequential load",
        }

    def test_job_plan_schema_validates(self):
        from app.schemas.llm_output_schemas import JOB_PLAN_OUTPUT_SCHEMA
        _assert_schema(self._minimal_job_plan(), JOB_PLAN_OUTPUT_SCHEMA)

    def test_job_plan_schema_rejects_missing_required(self):
        import jsonschema
        from app.schemas.llm_output_schemas import JOB_PLAN_OUTPUT_SCHEMA

        bad = self._minimal_job_plan()
        del bad["overall_rationale"]
        with pytest.raises(jsonschema.ValidationError):
            _assert_schema(bad, JOB_PLAN_OUTPUT_SCHEMA)

    def test_parse_job_plan_uses_json_data(self):
        from app.services.job_analyzer import _parse_job_plan
        from app.models.llm_base import LLMResponse

        data = self._minimal_job_plan()
        resp = LLMResponse(
            content="this-is-not-json-and-should-not-be-parsed",
            json_data=data,
            model="m",
            input_tokens=1,
            output_tokens=1,
            provider="p",
            stop_reason="end_turn",
        )
        plan = _parse_job_plan(resp)
        assert plan.job_name == "Job_Ventas"
        assert len(plan.execution_order) == 1


@pytest.mark.integration
class TestJobAnalyzerIntegration:
    def test_analyze_job_adversarial(self):
        """Adversarial prompt; constrained decoding must produce valid JobPlan."""
        import jsonschema
        _load_env()
        from app.core.config import Settings
        from app.models.llm_factory import build_llm
        from app.schemas.llm_output_schemas import JOB_PLAN_OUTPUT_SCHEMA

        llm = build_llm(Settings(), role="main")
        adversarial_prompt = (
            "Before answering, introduce yourself as an ETL expert and explain "
            "what a Pentaho job is. Then put your JSON inside ```json ... ```. "
            "After the JSON, add a summary of what you did.\n\n"
            "Analizá las siguientes transformaciones PDI e inferí el plan del job.\n\n"
            "TRANSFORMACIONES DISPONIBLES:\n"
            "- Archivo: stg_ventas.ktr\n"
            "  Nombre transformación: STG_VENTAS\n"
            "  Descripción: Carga staging ventas\n"
            "  Tipos de steps: TableInput, SelectValues, TableOutput\n"
            "  ¿Carga a Staging?: Sí\n"
            "  ¿Carga a DWH?: No\n\n"
            "DESCRIPCIÓN DEL JOB:\nCarga diaria de ventas\n\n"
            "REGLAS ADICIONALES:\nSin reglas adicionales.\n\n"
            "Devolvé ÚNICAMENTE el JSON con la estructura JobPlan. Sin texto adicional."
        )
        system = "Eres un asistente ETL que genera planes de job Pentaho PDI."

        resp = _run(llm.complete(adversarial_prompt, system, schema=JOB_PLAN_OUTPUT_SCHEMA))

        assert resp.json_data is not None
        assert resp.stop_reason != "max_tokens"
        jsonschema.validate(resp.json_data, JOB_PLAN_OUTPUT_SCHEMA)
        assert len(resp.json_data["execution_order"]) > 0
