"""
Context-safety guard tests.

These tests verify that neither a connection identifier nor raw column values
ever appear in the prompt payload that is sent to the model.

Covered call sites:
  - etl_generator.generate_etl
  - etl_generator.generate_etl_from_inference
  - structure_inferrer.infer_structures
  - structure_inferrer.refine_structures
  - validator.validate_etl          (processes only model output — no table data)
  - documenter.document_etl         (processes only model output — no table data)

Run with:  pytest tests/test_context_safety.py -v
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.models.llm_base import BaseLLM, LLMResponse


def _run(coro):
    """Run a coroutine synchronously — no pytest-asyncio dependency needed."""
    return asyncio.run(coro)
from app.schemas.etl_schemas import (
    ColumnaOrigen,
    ColumnaDwh,
    ETLDocumentRequest,
    ETLFromInferenceRequest,
    ETLRequest,
    ETLValidateRequest,
    InferRequest,
    ModeloDwh,
    RefineRequest,
    TablaOrigen,
    TablaStaging,
    TablaDwh,
)

# ─── Sentinel values that must never appear in any prompt ──────────────────────

_CONN_ID    = "real-connection-id-abc123"
_RAW_VALUES = ["john.doe@acme.com", "jane.smith@corp.com", "555-1234-5678", "rawsecret99"]


# ─── Mock LLM factory ─────────────────────────────────────────────────────────

def _make_llm(captured: list[str], response_json: dict | None = None) -> BaseLLM:
    """Returns a mock BaseLLM that records every prompt string."""
    default_resp = {
        "proceso_etl": {"nombre": "TEST", "descripcion": "", "steps": []},
        "validaciones": [],
        "documentacion": "",
        "advertencias_buenas_practicas": [],
        "ktr": {},
    }
    payload = json.dumps(response_json or default_resp)

    async def _complete(user_message: str, system: str, schema=None) -> LLMResponse:
        captured.append(user_message)
        return LLMResponse(
            content=payload,
            json_data=response_json or default_resp,
            model="test",
            input_tokens=0,
            output_tokens=0,
            provider="test",
        )

    llm = MagicMock(spec=BaseLLM)
    llm.complete = _complete
    return llm


# ─── Sample request builders ──────────────────────────────────────────────────

def _etl_request(with_conn_id: bool = False) -> ETLRequest:
    col = ColumnaOrigen(name="email", dataType="string", data=list(_RAW_VALUES))
    tabla = TablaOrigen(
        tableName="customers",
        columns=[col],
        connection_id=_CONN_ID if with_conn_id else None,
    )
    return ETLRequest(
        descripcionObjetivo="Test safety",
        origenTables=[tabla],
        stagingDef=[TablaStaging(tableName="STG_CUSTOMERS", columns=[])],
        dwhModel=ModeloDwh(tables=[
            TablaDwh(
                tipo="Dimension", nombre="DIM_CUSTOMERS",
                columnas=[ColumnaDwh(nombre="SK", tipo="INTEGER", esSurrogateKey=True)],
            )
        ]),
        reglasNegocio="",
    )


def _from_inference_request() -> ETLFromInferenceRequest:
    col = ColumnaOrigen(name="email", dataType="string", data=list(_RAW_VALUES))
    return ETLFromInferenceRequest(
        descripcionObjetivo="Test",
        origenTables=[TablaOrigen(tableName="customers", columns=[col])],
        stg_definition="CREATE TABLE STG_CUSTOMERS (email VARCHAR(255));",
        dwh_model="CREATE TABLE DIM_CUSTOMERS (SK INTEGER PRIMARY KEY);",
        reglasNegocio="",
    )


def _infer_request() -> InferRequest:
    origin_with_data = [
        {
            "tableName": "customers",
            "columns": [{"name": "email", "dataType": "string", "data": list(_RAW_VALUES)}],
        }
    ]
    return InferRequest(
        source_structure=json.dumps(origin_with_data),
        process_description="Load customers",
        business_rules="",
    )


def _refine_request() -> RefineRequest:
    origin_with_data = [
        {
            "tableName": "customers",
            "columns": [{"name": "email", "dataType": "string", "data": list(_RAW_VALUES)}],
        }
    ]
    return RefineRequest(
        source_structure=json.dumps(origin_with_data),
        process_description="Load customers",
        business_rules="",
        current_stg="CREATE TABLE STG_CUSTOMERS (email VARCHAR(255));",
        current_dwh="CREATE TABLE DIM_CUSTOMERS (SK INTEGER PRIMARY KEY);",
        correction="Add a name column",
        history=[],
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _assert_safe(prompt: str, label: str):
    for raw in _RAW_VALUES:
        assert raw not in prompt, f"[{label}] Raw value '{raw}' leaked into prompt"
    assert _CONN_ID not in prompt, f"[{label}] connection_id leaked into prompt"


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_generate_etl_no_raw_data():
    captured: list[str] = []
    from app.services.etl_generator import generate_etl
    _run(generate_etl(_etl_request(), _make_llm(captured), db=None))
    assert captured, "LLM was never called"
    _assert_safe(captured[0], "generate_etl / memory path")


def test_generate_etl_no_connection_id_with_db_flag():
    """connection_id must not reach the prompt even when set in the request."""
    captured: list[str] = []
    from app.services.etl_generator import generate_etl
    # db=None forces memory fallback; connection_id is still in the request object.
    _run(generate_etl(_etl_request(with_conn_id=True), _make_llm(captured), db=None))
    assert captured
    _assert_safe(captured[0], "generate_etl / with connection_id but db=None")


def test_generate_etl_from_inference_no_raw_data():
    captured: list[str] = []
    from app.services.etl_generator import generate_etl_from_inference
    _run(generate_etl_from_inference(_from_inference_request(), _make_llm(captured), db=None))
    assert captured
    _assert_safe(captured[0], "generate_etl_from_inference")


def test_infer_structures_no_raw_data():
    captured: list[str] = []
    infer_resp = {
        "stg_definition": "CREATE TABLE STG_TEST (id INTEGER);",
        "dwh_model":      "CREATE TABLE DIM_TEST (SK INTEGER PRIMARY KEY);",
        "stg_rationale":  "",
        "dwh_rationale":  "",
        "iteration":      1,
    }
    from app.services.structure_inferrer import infer_structures
    _run(infer_structures(_infer_request(), _make_llm(captured, infer_resp)))
    assert captured
    _assert_safe(captured[0], "infer_structures")


def test_refine_structures_no_raw_data():
    captured: list[str] = []
    infer_resp = {
        "stg_definition": "CREATE TABLE STG_TEST (id INTEGER, name VARCHAR);",
        "dwh_model":      "CREATE TABLE DIM_TEST (SK INTEGER PRIMARY KEY);",
        "stg_rationale":  "",
        "dwh_rationale":  "",
        "iteration":      2,
    }
    from app.services.structure_inferrer import refine_structures
    _run(refine_structures(_refine_request(), _make_llm(captured, infer_resp)))
    assert captured
    _assert_safe(captured[0], "refine_structures")


def test_validate_etl_no_raw_data():
    """validate_etl receives model-generated ETL output, not raw table data.
    Verify the prompt does not contain the sentinel raw values either way."""
    captured: list[str] = []
    validate_resp = {"validaciones": [], "advertencias_buenas_practicas": []}
    req = ETLValidateRequest(proceso_etl={"nombre": "TEST", "steps": []})

    from app.services.validator import validate_etl
    _run(validate_etl(req, _make_llm(captured, validate_resp)))
    assert captured
    _assert_safe(captured[0], "validate_etl")


def test_document_etl_no_raw_data():
    """document_etl receives model-generated ETL output, not raw table data."""
    captured: list[str] = []
    doc_resp = {"documentacion": "OK"}
    req = ETLDocumentRequest(proceso_etl={"nombre": "TEST", "steps": []})

    from app.services.documenter import document_etl
    _run(document_etl(req, _make_llm(captured, doc_resp)))
    assert captured
    _assert_safe(captured[0], "document_etl")
