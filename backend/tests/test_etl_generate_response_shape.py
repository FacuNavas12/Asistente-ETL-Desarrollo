"""D20 (docs/refactor/02-decisiones.md) + D13 — dos tests que cierra F3:

1. Lo que esta fase trabajó: _build_response_from_two_ktr_data /
   _build_response_from_data ahora aplican el corte de verdad (D19 solo
   notificaba) — cuando compute_cut() detecta groups>1 en una etapa, el
   flujo en vivo entrega N archivos + un .kjb intermedio, no un .ktr sin
   partir con una advertencia.
2. El contrato que esta fase expone hacia la fase siguiente (frontend,
   D20-punto5): la forma de EtapaOutput/ArchivoKtr en ETLGenerateResponse —
   incluido el round-trip de (de)serialización que usa KtrJobStatusResponse
   (job.result_json) en el flujo async.

También cubre, vía TestClient contra /api/v1/etl/generate-from-inference con
LLM mockeado, el punto 2 de "NO hecho" en 03-plan.md (fila F3): un test de
integración end-to-end contra el pipeline HTTP completo con un caso que
dispare un corte real — sin depender del bug preexistente y no relacionado
de ConnectionsMapRequest/InlineConnection (ver test_ktr_build_job_api.py)."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.core.dependencies import get_main_llm
from app.main import app
from app.models.llm_base import BaseLLM, LLMResponse
from app.schemas.etl_schemas import ArchivoKtr, EtapaOutput, ETLGenerateResponse, MetadataResponse
from app.services import etl_generator
from app.services.kjb_xml_validator import validate_kjb_xml


def _origen_stg_ktr() -> dict:
    """2 ramas independientes (ventas / productos) sin ningún conflicto de
    tabla — caso común (2 tablas de origen cargando 2 de staging) que NO
    debe disparar corte (D6-bis) aunque sean 2 componentes de hop
    desconectados entre sí."""
    return {
        "name": "KTR1", "description": "", "connections": [],
        "steps": [
            {"name": "Leer Ventas Origen", "type": "TableInput",
             "config": {"connection": "conn_origen", "sql": "SELECT id_venta, id_producto, monto FROM ventas"}},
            {"name": "Cargar Stg Ventas", "type": "TableOutput",
             "config": {"connection": "conn_staging", "table": "stg_ventas"}},
            {"name": "Leer Productos Origen", "type": "TableInput",
             "config": {"connection": "conn_origen", "sql": "SELECT id_producto, nombre FROM productos"}},
            {"name": "Cargar Stg Productos", "type": "TableOutput",
             "config": {"connection": "conn_staging", "table": "stg_productos"}},
        ],
        "hops": [
            {"from": "Leer Ventas Origen", "to": "Cargar Stg Ventas", "enabled": True},
            {"from": "Leer Productos Origen", "to": "Cargar Stg Productos", "enabled": True},
        ],
    }


def _stg_dwh_ktr_with_real_cut() -> dict:
    """Misma forma que err1.ktr/err2.ktr (H21, test_fragmentation.py): dim_producto
    escrita por 'Cargar Dim Producto' (loader) y leída por 'Lookup Dim Producto'
    (fact_lookup, update=N) en componentes de hop ya distintos -> C1 dispara,
    2 grupos."""
    return {
        "name": "KTR2", "description": "", "connections": [],
        "steps": [
            {"name": "Leer Staging Productos", "type": "TableInput",
             "config": {"connection": "conn_staging", "sql": "SELECT id_producto FROM stg_productos"}},
            {"name": "Cargar Dim Producto", "type": "DimensionLookup",
             "config": {"table": "dim_producto", "connection": "conn_dwh", "returnfield": "sk_producto",
                        "keys": [{"stream_field": "id_producto", "table_field": "id_producto"}]}},
            {"name": "Leer Staging Ventas", "type": "TableInput",
             "config": {"connection": "conn_staging", "sql": "SELECT id_producto, monto FROM stg_ventas"}},
            {"name": "Lookup Dim Producto", "type": "DimensionLookup",
             "config": {"table": "dim_producto", "connection": "conn_dwh", "returnfield": "sk_producto",
                        "update": "N",
                        "keys": [{"stream_field": "id_producto", "table_field": "id_producto"}]}},
            {"name": "Cargar Fact Venta", "type": "InsertUpdate",
             "config": {"table": "fact_venta", "connection": "conn_dwh"}},
        ],
        "hops": [
            {"from": "Leer Staging Productos", "to": "Cargar Dim Producto", "enabled": True},
            {"from": "Leer Staging Ventas", "to": "Lookup Dim Producto", "enabled": True},
            {"from": "Lookup Dim Producto", "to": "Cargar Fact Venta", "enabled": True},
        ],
    }


def _wrap(ktr: dict, descripcion: str) -> dict:
    return {
        "proceso_etl": {"nombre": "ETL_Ventas", "descripcion": descripcion, "steps": []},
        "validaciones": [], "documentacion": descripcion, "advertencias_buenas_practicas": [],
        "ktr": ktr,
    }


# ─── 1. Lo que esta fase trabajó: el corte se aplica de verdad ────────────

def test_two_ktr_flow_splits_the_stage_that_needs_it_and_leaves_the_other_alone():
    metadata = MetadataResponse(modelo_usado="t", tokens_input=0, tokens_output=0, region_inferencia="t")
    result = etl_generator._build_response_from_two_ktr_data(
        _wrap(_origen_stg_ktr(), "d1"), _wrap(_stg_dwh_ktr_with_real_cut(), "d2"), metadata,
    )

    assert len(result.etapas) == 2
    etapa_origen_stg, etapa_stg_dwh = result.etapas

    # origen_stg: 2 componentes de hop desconectados pero SIN señal
    # estructural (D6-bis) -> 1 solo archivo, no partido.
    assert etapa_origen_stg.tipo == "ktr"
    assert etapa_origen_stg.archivo is not None
    assert etapa_origen_stg.archivos == []

    # stg_dwh: dim_producto dispara C1 -> 2 archivos + su .kjb intermedio.
    assert etapa_stg_dwh.tipo == "kjb"
    assert etapa_stg_dwh.kjb is not None
    assert len(etapa_stg_dwh.archivos) == 2
    # Nombres de archivo distintos entre sí (bug encontrado en esta sesión:
    # build_ktr() prioriza ktr_data["name"] sobre el nombre pasado por
    # parámetro — sin el fix en _build_ktr_stage, los N sub-dicts de un
    # corte comparten "name" y terminan pisándose filename/<name> interno).
    filenames = [a.filename for a in etapa_stg_dwh.archivos]
    assert len(set(filenames)) == 2

    # El .kjb maestro siempre orquesta las 2 etapas (D20-punto3), y el .kjb
    # intermedio de la etapa partida es válido standalone.
    assert result.kjb_master is not None
    validate_kjb_xml(result.kjb_master.xml)
    validate_kjb_xml(etapa_stg_dwh.kjb.xml)

    # El linaje cose los 3 archivos físicos reales (1 de origen_stg + 2 de
    # stg_dwh), no los 2 KTR lógicos — stitch_lineage_many(), no stitch_lineage().
    node_names = {n.step_name for n in result.lineage.nodes}
    assert "Cargar Stg Productos" in node_names          # origen_stg, sin prefijo (índice 0)
    assert "F1::Cargar Dim Producto" in node_names        # 1er sub-archivo de stg_dwh
    assert "F2::Cargar Fact Venta" in node_names           # 2do sub-archivo de stg_dwh


def test_monolithic_flow_splits_into_a_single_etapa_with_n_archivos():
    """_build_response_from_data (flujo legacy, 1 sola llamada al modelo) —
    mismo corte real, pero expone 1 sola etapa (no hay fase Origen/Staging
    separada en este flujo)."""
    metadata = MetadataResponse(modelo_usado="t", tokens_input=0, tokens_output=0, region_inferencia="t")
    data = _wrap(_stg_dwh_ktr_with_real_cut(), "d")
    result = etl_generator._build_response_from_data(data, metadata)

    assert len(result.etapas) == 1
    etapa = result.etapas[0]
    assert etapa.tipo == "kjb"
    assert len(etapa.archivos) == 2
    assert len({a.filename for a in etapa.archivos}) == 2
    validate_kjb_xml(etapa.kjb.xml)
    # 1 sola etapa total -> nada que secuenciar por encima de ella.
    assert result.kjb_master is None


# ─── 2. Contrato expuesto hacia la fase siguiente (D13) ────────────────────

def test_etl_generate_response_round_trips_through_json_like_the_async_job_does():
    """KtrJobStatusResponse.result reconstruye ETLGenerateResponse desde
    job.result_json (ver routers/ai.py::_status_response) — si el shape de
    EtapaOutput/ArchivoKtr no sobrevive un dump/load de JSON, ese flujo
    rompe en producción sin que ningún test lo vea."""
    metadata = MetadataResponse(modelo_usado="t", tokens_input=0, tokens_output=0, region_inferencia="t")
    original = etl_generator._build_response_from_two_ktr_data(
        _wrap(_origen_stg_ktr(), "d1"), _wrap(_stg_dwh_ktr_with_real_cut(), "d2"), metadata,
    )

    dumped = original.model_dump(mode="json")
    restored = ETLGenerateResponse(**json.loads(json.dumps(dumped)))

    assert restored.etapas[0].tipo == "ktr"
    assert restored.etapas[1].tipo == "kjb"
    assert len(restored.etapas[1].archivos) == 2
    assert restored.kjb_master.filename == original.kjb_master.filename


# ─── dwh_ddl/stg_ddl passthrough (bug reportado: "Reutilizar respuesta" no
# mostraba el DDL en EtlDetail — build_etl_from_raw() nunca los pasaba a
# estas dos funciones, a diferencia del flujo de generación normal) ────────

def test_two_ktr_flow_carries_dwh_and_stg_ddl_through():
    metadata = MetadataResponse(modelo_usado="t", tokens_input=0, tokens_output=0, region_inferencia="t")
    result = etl_generator._build_response_from_two_ktr_data(
        _wrap(_origen_stg_ktr(), "d1"), _wrap(_stg_dwh_ktr_with_real_cut(), "d2"), metadata,
        dwh_ddl="CREATE TABLE dim_producto (sk_producto INT);",
        stg_ddl="CREATE TABLE stg_ventas (id_venta INT);",
    )
    assert result.dwh_ddl == "CREATE TABLE dim_producto (sk_producto INT);"
    assert result.stg_ddl == "CREATE TABLE stg_ventas (id_venta INT);"


def test_two_ktr_flow_defaults_ddl_to_none_when_not_passed():
    metadata = MetadataResponse(modelo_usado="t", tokens_input=0, tokens_output=0, region_inferencia="t")
    result = etl_generator._build_response_from_two_ktr_data(
        _wrap(_origen_stg_ktr(), "d1"), _wrap(_stg_dwh_ktr_with_real_cut(), "d2"), metadata,
    )
    assert result.dwh_ddl is None
    assert result.stg_ddl is None


def test_monolithic_flow_carries_dwh_and_stg_ddl_through():
    metadata = MetadataResponse(modelo_usado="t", tokens_input=0, tokens_output=0, region_inferencia="t")
    data = _wrap(_stg_dwh_ktr_with_real_cut(), "d")
    result = etl_generator._build_response_from_data(
        data, metadata,
        dwh_ddl="CREATE TABLE dim_producto (sk_producto INT);",
        stg_ddl="CREATE TABLE stg_ventas (id_venta INT);",
    )
    assert result.dwh_ddl == "CREATE TABLE dim_producto (sk_producto INT);"
    assert result.stg_ddl == "CREATE TABLE stg_ventas (id_venta INT);"


def test_etapa_output_tipo_rejects_unknown_value():
    """El contrato es un Literal["ktr","kjb"] — un valor fuera de eso (ej. un
    consumidor futuro que agregue un tercer tipo sin coordinar) debe fallar
    en el borde, no colarse silencioso."""
    import pydantic
    import pytest

    with pytest.raises(pydantic.ValidationError):
        EtapaOutput(tipo="zip", archivo=ArchivoKtr(xml="<x/>", filename="a.ktr"))


# ─── End-to-end HTTP: el caso de corte real llega servido por el endpoint ──

def _fake_llm_two_calls(ktr_1: dict, ktr_2: dict) -> BaseLLM:
    """generate_etl_from_inference llama a llm.complete() 2 veces en orden
    (prompt_1=origen_stg, luego prompt_2=stg_dwh) — sin dim_contracts,
    validate_and_correct_ddl() no llama al modelo (short-circuit), así que
    estas son las únicas 2 llamadas reales."""
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


def test_generate_from_inference_http_endpoint_delivers_real_split():
    data_1 = _wrap(_origen_stg_ktr(), "d1")
    data_2 = _wrap(_stg_dwh_ktr_with_real_cut(), "d2")
    llm = _fake_llm_two_calls(data_1, data_2)

    app.dependency_overrides[get_main_llm] = lambda: llm
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/etl/generate-from-inference", json={
                "descripcionObjetivo": "Test E2E fragmentación",
                "origenTables": [{"tableName": "ventas", "columns": [{"name": "id_venta", "dataType": "int"}]}],
                "stg_definition": "CREATE TABLE stg_ventas (id_venta INT); CREATE TABLE stg_productos (id_producto INT);",
                "dwh_model": "CREATE TABLE dim_producto (sk_producto INT); CREATE TABLE fact_venta (sk_producto INT);",
                "reglasNegocio": "",
                "dim_contracts": [],
            })
    finally:
        app.dependency_overrides.pop(get_main_llm, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    etapas = body["etapas"]
    assert len(etapas) == 2
    assert etapas[0]["tipo"] == "ktr"
    assert etapas[1]["tipo"] == "kjb"
    assert len(etapas[1]["archivos"]) == 2
    assert body["kjb_master"] is not None
