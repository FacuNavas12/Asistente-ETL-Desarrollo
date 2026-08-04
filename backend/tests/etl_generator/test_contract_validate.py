"""D23/D13 (docs/refactor/02-decisiones.md) — dos tests:

1. Lo que esta fase trabajó: validate_ktr_contracts() detecta que un archivo
   escritor no puebla una columna NOT NULL que otro archivo, en otro punto
   del grafo, necesita de esa misma tabla — incluso cuando el lector no es
   un TableInput plano (DBLookup), el caso que _resolve_table_endpoints
   (lineage_builder.py, matching solo TableInput/TableOutput terminal) no
   puede ver y que motivó elegir build_rw_matrix como fuente de aristas.
2. El contrato que expone hacia la fase siguiente: un mismatch real, en el
   flujo HTTP completo (LLM mockeado), llega a ETLGenerateResponse.validaciones
   como Validacion(tipo="error", campo="contrato_ktr") — no como texto
   perdido entre advertencias cosméticas.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.core.dependencies import get_main_llm
from app.main import app
from app.models.llm_base import BaseLLM, LLMResponse
from app.services.ktr_builder.contract_validate import validate_ktr_contracts
from app.services.ktr_builder.step_types import STEP_TYPE_ALIASES


# ─── 1. El validador en sí ─────────────────────────────────────────────────

def test_validate_ktr_contracts_catches_missing_column_read_via_dblookup():
    """Archivo 0 escribe 'stg_productos' sin la columna 'categoria'. Archivo 1
    la lee vía DBLookup (no TableInput) — el matching de linaje no vería este
    lector; build_rw_matrix sí."""
    file_0 = {
        "steps": [
            {"name": "Leer Origen", "type": "TableInput",
             "config": {"connection": "c", "sql": "SELECT id_producto FROM productos"}},
            {"name": "Escribir Stg Productos", "type": "TableOutput",
             "config": {
                 "connection": "c", "table": "stg_productos",
                 "fields": [{"column_name": "id_producto", "stream_name": "id_producto"}],
             }},
        ],
        "hops": [{"from": "Leer Origen", "to": "Escribir Stg Productos", "enabled": True}],
    }
    file_1 = {
        "steps": [
            {"name": "Lookup Categoria", "type": "DBLookup",
             "config": {
                 "connection": "c", "table": "stg_productos",
                 "return_fields": [{"name": "categoria"}],
                 "keys": [{"stream_field": "id_producto", "table_field": "id_producto"}],
             }},
        ],
        "hops": [],
    }
    stg_ddl = "CREATE TABLE stg_productos (id_producto INT NOT NULL, categoria VARCHAR(50) NOT NULL);"

    messages = validate_ktr_contracts([file_0, file_1], stg_ddl, "", STEP_TYPE_ALIASES)

    assert len(messages) == 1
    assert "stg_productos" in messages[0]
    assert "categoria" in messages[0]


def test_validate_ktr_contracts_clean_when_all_required_columns_written():
    file_0 = {
        "steps": [{
            "name": "Escribir Stg Productos", "type": "TableOutput",
            "config": {
                "connection": "c", "table": "stg_productos",
                "fields": [
                    {"column_name": "id_producto", "stream_name": "id_producto"},
                    {"column_name": "categoria", "stream_name": "categoria"},
                ],
            },
        }],
        "hops": [],
    }
    file_1 = {
        "steps": [{
            "name": "Leer Stg Productos", "type": "TableInput",
            "config": {"connection": "c", "sql": "SELECT * FROM stg_productos"},
        }],
        "hops": [],
    }
    stg_ddl = "CREATE TABLE stg_productos (id_producto INT NOT NULL, categoria VARCHAR(50) NOT NULL);"

    assert validate_ktr_contracts([file_0, file_1], stg_ddl, "", STEP_TYPE_ALIASES) == []


# ─── 2. Contrato expuesto hacia la fase siguiente (D13) ────────────────────

def _fake_llm_two_calls(ktr_1: dict, ktr_2: dict) -> BaseLLM:
    calls = {"n": 0}

    async def _complete(user_message, system, schema=None):
        calls["n"] += 1
        data = ktr_1 if calls["n"] == 1 else ktr_2
        return LLMResponse(
            content=json.dumps(data), json_data=data,
            model="test", input_tokens=1, output_tokens=1, provider="test",
        )

    from unittest.mock import MagicMock
    llm = MagicMock(spec=BaseLLM)
    llm.complete = _complete
    return llm


def _wrap(ktr: dict, descripcion: str) -> dict:
    return {
        "proceso_etl": {"nombre": "ETL_Test", "descripcion": descripcion, "steps": []},
        "validaciones": [], "documentacion": descripcion, "advertencias_buenas_practicas": [],
        "ktr": ktr,
    }


def test_contract_mismatch_reaches_http_response_as_error_validacion():
    ktr_1 = {
        "name": "KTR1", "description": "", "connections": [],
        "steps": [
            {"name": "Leer Origen", "type": "TableInput",
             "config": {"connection": "conn_origen", "sql": "SELECT id_producto FROM productos"}},
            {"name": "Escribir Stg Productos", "type": "TableOutput",
             "config": {
                 "connection": "conn_staging", "table": "stg_productos",
                 "fields": [{"column_name": "id_producto", "stream_name": "id_producto"}],
             }},
        ],
        "hops": [{"from": "Leer Origen", "to": "Escribir Stg Productos", "enabled": True}],
    }
    ktr_2 = {
        "name": "KTR2", "description": "", "connections": [],
        "steps": [
            {"name": "Leer Stg Productos", "type": "TableInput",
             "config": {"connection": "conn_staging", "sql": "SELECT * FROM stg_productos"}},
            {"name": "Escribir Dim Producto", "type": "TableOutput",
             "config": {"connection": "conn_dwh", "table": "dim_producto"}},
        ],
        "hops": [{"from": "Leer Stg Productos", "to": "Escribir Dim Producto", "enabled": True}],
    }
    llm = _fake_llm_two_calls(_wrap(ktr_1, "d1"), _wrap(ktr_2, "d2"))

    app.dependency_overrides[get_main_llm] = lambda: llm
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/etl/generate-from-inference", json={
                "descripcionObjetivo": "Test D23 contrato entre KTR",
                "origenTables": [{"tableName": "productos", "columns": [{"name": "id_producto", "dataType": "int"}]}],
                "stg_definition": (
                    "CREATE TABLE stg_productos (id_producto INT NOT NULL, categoria VARCHAR(50) NOT NULL);"
                ),
                "dwh_model": "CREATE TABLE dim_producto (id_producto INT);",
                "reglasNegocio": "",
                "dim_contracts": [],
            })
    finally:
        app.dependency_overrides.pop(get_main_llm, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    contrato_validaciones = [v for v in body["validaciones"] if v["campo"] == "contrato_ktr"]
    assert len(contrato_validaciones) == 1
    assert contrato_validaciones[0]["tipo"] == "error"
    assert "categoria" in contrato_validaciones[0]["mensaje"]
    assert "stg_productos" in contrato_validaciones[0]["mensaje"]
