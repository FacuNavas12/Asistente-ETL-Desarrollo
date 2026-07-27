"""
Tests de D29/D30/D31/D32 (docs/refactor/02-decisiones.md): progreso observable
del job async, checkpoint por etapa, reanudación con reuse_stage_1, y el
contrato inmutable de raw_llm_data (lo parcial va en `stages`).
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock

from app.core.auth import require_auth
from app.core.database import Base, get_db, get_session_factory
from app.core.dependencies import get_main_llm
from app.main import app
from app.models.ktr_build_job import KtrBuildJob
from app.models.llm_base import BaseLLM, LLMResponse
from app.services import job_progress

_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
_Session = sessionmaker(bind=_engine)

_KTR_JSON = {
    "proceso_etl": {"nombre": "TEST_PROC", "descripcion": "", "steps": []},
    "validaciones": [],
    "documentacion": "",
    "advertencias_buenas_practicas": [],
    "ktr": {
        "name": "TEST_PROC",
        "description": "",
        "connections": [{"name": "conn_dwh", "type": "GENERIC", "host": "PLACEHOLDER_HOST", "database": "PLACEHOLDER_DATABASE", "port": 0, "username": "PLACEHOLDER_USER"}],
        # "SELECT 1" dispara el detector de placeholder de build.py (ver
        # test_ktr_build_job_api.py::test_attaching_a_foreign_connection_id_to_own_job_falls_back_to_placeholder,
        # mismo motivo) — usar una query con forma real.
        "steps": [
            {"name": "Leer", "type": "TableInput", "config": {"connection": "conn_dwh", "sql": "SELECT id FROM origen"}},
            {"name": "Escribir", "type": "TableOutput", "config": {"connection": "conn_dwh", "table": "dim_x"}},
        ],
        "hops": [{"from": "Leer", "to": "Escribir", "enabled": True}],
    },
}


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


def _fake_llm_ok() -> BaseLLM:
    async def _complete(user_message, system, schema=None):
        return LLMResponse(
            content=json.dumps(_KTR_JSON), json_data=copy.deepcopy(_KTR_JSON),
            model="test", input_tokens=1, output_tokens=1, provider="test",
        )

    llm = MagicMock(spec=BaseLLM)
    llm.complete = _complete
    return llm


def _fake_llm_fails_on_call(n: int) -> BaseLLM:
    """Responde OK en las primeras n-1 llamadas, revienta en la n-ésima."""
    calls = {"count": 0}

    async def _complete(user_message, system, schema=None):
        calls["count"] += 1
        if calls["count"] < n:
            return LLMResponse(
                content=json.dumps(_KTR_JSON), json_data=copy.deepcopy(_KTR_JSON),
                model="test", input_tokens=1, output_tokens=1, provider="test",
            )
        raise RuntimeError("stage 2 boom")

    llm = MagicMock(spec=BaseLLM)
    llm.complete = _complete
    llm._calls = calls
    return llm


def _fake_llm_counting() -> BaseLLM:
    calls = {"count": 0}

    async def _complete(user_message, system, schema=None):
        calls["count"] += 1
        return LLMResponse(
            content=json.dumps(_KTR_JSON), json_data=copy.deepcopy(_KTR_JSON),
            model="test", input_tokens=1, output_tokens=1, provider="test",
        )

    llm = MagicMock(spec=BaseLLM)
    llm.complete = _complete
    llm._calls = calls
    return llm


@pytest.fixture
def client():
    def _override_get_db():
        db = _Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_session_factory] = lambda: _Session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_session_factory, None)
    app.dependency_overrides.pop(get_main_llm, None)
    app.dependency_overrides.pop(require_auth, None)


def _req_body(**overrides) -> dict:
    body = {
        "descripcionObjetivo": "obj",
        "origenTables": [{"tableName": "src", "columns": [{"name": "id", "dataType": "int"}]}],
        "stg_definition": "CREATE TABLE STG_X (id INT);",
        "dwh_model": "CREATE TABLE DIM_X (id INT);",
        "reglasNegocio": "",
    }
    body.update(overrides)
    return body


async def _drain_pending_tasks():
    await asyncio.sleep(0.05)


def _codes(progress: list[dict]) -> list[str]:
    return [e["code"] for e in progress]


# ─── D29 — progreso persistido, secuencia y tope ─────────────────────────────

def test_progress_sequence_recorded_in_order(client):
    app.dependency_overrides[get_main_llm] = lambda: _fake_llm_ok()
    resp = client.post("/api/v1/etl/generate-async", json=_req_body())
    job_id = resp.json()["job_id"]

    asyncio.run(_drain_pending_tasks())

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    body = resp.json()
    progress = body["progress"]

    # seq denso y monotónico
    assert [e["seq"] for e in progress] == list(range(len(progress)))

    codes = _codes(progress)
    assert codes == [
        "job.started",
        "ddl.audit.started", "ddl.audit.done",
        "stage.llm.started", "stage.llm.done",
        "stage.repair.started", "stage.repair.done",
        "stage.checkpoint",
        "stage.llm.started", "stage.llm.done",
        "stage.repair.started", "stage.repair.done",
        "stage.checkpoint",
        "build.waiting_connections",
    ]
    # las dos etapas están etiquetadas correctamente, no ambas "job"
    assert progress[3]["stage"] == "origen_stg"
    assert progress[8]["stage"] == "stg_dwh"


def test_progress_truncates_at_max_events():
    db = _Session()
    job = KtrBuildJob(expires_at=datetime.now(timezone.utc) + timedelta(minutes=30))
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
    db.close()

    for i in range(150):
        job_progress.emit(job_id, _Session, stage="job", code="job.started", message=f"evento {i}")

    db = _Session()
    j = db.get(KtrBuildJob, job_id)
    events = j.progress_json["events"]
    assert j.progress_json["truncated"] is True
    # _MAX_EVENTS eventos reales + 1 marcador de truncamiento agregado al
    # alcanzar el tope (después de eso, emit() no vuelve a escribir nada).
    assert len(events) == job_progress._MAX_EVENTS + 1
    assert events[-1]["code"] == "job.progress_truncated"
    # no se repite el evento de truncamiento aunque sigan llegando emit() de más
    assert sum(1 for e in events if e["code"] == "job.progress_truncated") == 1
    db.close()


def test_progress_message_is_truncated_to_max_len():
    db = _Session()
    job = KtrBuildJob(expires_at=datetime.now(timezone.utc) + timedelta(minutes=30))
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
    db.close()

    job_progress.emit(job_id, _Session, stage="job", code="job.started", message="x" * 500)

    db = _Session()
    j = db.get(KtrBuildJob, job_id)
    msg = j.progress_json["events"][0]["message"]
    assert len(msg) <= job_progress._MAX_MSG
    assert msg.endswith("…")
    db.close()


# ─── D29 — handler de reintentos, sin tocar gemini_llm.py/anthropic_llm.py ───

def test_gemini_retry_log_captured_when_sink_active():
    db = _Session()
    job = KtrBuildJob(expires_at=datetime.now(timezone.utc) + timedelta(minutes=30))
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
    db.close()

    sink = job_progress.ProgressSink(job_id, _Session, current_stage="origen_stg")
    logger = logging.getLogger("app.models.gemini_llm")
    with job_progress.active_sink(sink):
        logger.warning(
            "[Gemini] Transient error (attempt %d/%d): %s — retrying in %ds",
            2, 4, RuntimeError("503 from provider, prompt leaked here"), 4,
        )

    db = _Session()
    j = db.get(KtrBuildJob, job_id)
    events = j.progress_json["events"]
    assert len(events) == 1
    assert events[0]["code"] == "stage.llm.retry"
    assert events[0]["level"] == "warning"
    assert "2/4" in events[0]["message"]
    # nunca reenvía el texto crudo del proveedor (record.getMessage() renderizado)
    assert "503" not in events[0]["message"]
    assert "prompt leaked" not in events[0]["message"]
    db.close()


def test_gemini_fallback_log_captured():
    db = _Session()
    job = KtrBuildJob(expires_at=datetime.now(timezone.utc) + timedelta(minutes=30))
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
    db.close()

    sink = job_progress.ProgressSink(job_id, _Session, current_stage="stg_dwh")
    logger = logging.getLogger("app.models.anthropic_llm")
    with job_progress.active_sink(sink):
        logger.warning(
            "[Anthropic] BadRequestError with output_config (attempt %d) — "
            "entering text-mode fallback: %s",
            1, RuntimeError("boom"),
        )

    db = _Session()
    j = db.get(KtrBuildJob, job_id)
    events = j.progress_json["events"]
    assert len(events) == 1
    assert events[0]["code"] == "stage.llm.fallback"
    db.close()


def test_unrelated_log_record_is_not_captured():
    db = _Session()
    job = KtrBuildJob(expires_at=datetime.now(timezone.utc) + timedelta(minutes=30))
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
    db.close()

    sink = job_progress.ProgressSink(job_id, _Session)
    logger = logging.getLogger("app.models.gemini_llm")
    with job_progress.active_sink(sink):
        logger.info("Gemini complete — model: %s | attempt: %d", "test-model", 1)

    db = _Session()
    j = db.get(KtrBuildJob, job_id)
    assert j.progress_json is None  # ningún evento — el template no matchea nada conocido
    db.close()


def test_no_active_sink_means_no_capture():
    assert job_progress.current_sink() is None
    logger = logging.getLogger("app.models.gemini_llm")
    # No debe tirar excepción ni requerir un job activo.
    logger.warning(
        "[Gemini] Transient error (attempt %d/%d): %s — retrying in %ds",
        1, 4, RuntimeError("x"), 2,
    )


# ─── D30/D32 — checkpoint por etapa sobrevive al fallo de la etapa 2 ─────────

def test_stage1_checkpoint_survives_stage2_failure(client):
    app.dependency_overrides[get_main_llm] = lambda: _fake_llm_fails_on_call(2)
    resp = client.post("/api/v1/etl/generate-async", json=_req_body())
    job_id = resp.json()["job_id"]

    asyncio.run(_drain_pending_tasks())

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    body = resp.json()

    assert body["model_status"] == "failed"
    assert body["build_status"] == "failed"
    assert "stage 2 boom" in body["error"]

    # D32: el contrato de raw_llm_data NO cambia — nunca lleva una etapa en null.
    assert body["raw_llm_data"] is None

    # D30: lo parcial va en `stages`, separado.
    stages = {s["nombre"]: s for s in body["stages"]}
    assert stages["origen_stg"]["status"] == "done"
    assert stages["origen_stg"]["data"] is not None
    assert stages["stg_dwh"]["status"] == "failed"
    assert "stage 2 boom" in stages["stg_dwh"]["error"]

    # el checkpoint de la etapa 1 quedó registrado ANTES del fallo de la etapa 2
    codes = _codes(body["progress"])
    assert codes.index("stage.checkpoint") < codes.index("stage.failed")
    assert codes[-1] == "stage.failed"


def test_camino_feliz_sin_reuse_no_cambia(client):
    """La reordenación a pipeline por etapa (D30) no puede cambiar el camino
    feliz — mismo resultado que antes: build_status == built con conexión real."""
    app.dependency_overrides[get_main_llm] = lambda: _fake_llm_ok()

    resp = client.post("/api/v1/etl/generate-async", json=_req_body())
    job_id = resp.json()["job_id"]

    # conn_dwh es metadata inline (InlineConnection), no un connection_id —
    # ver ConnectionsMapRequest en etl_schemas.py. Pasar un string ahí es
    # justo el bug documentado en C.7 (02-decisiones.md), no algo a reproducir acá.
    resp = client.post(
        f"/api/v1/etl/{job_id}/connections",
        json={"conn_dwh": {"db_type": "postgresql", "host": "h", "port": 5432, "database": "d", "username": "u"}},
    )
    assert resp.status_code == 200, resp.text

    asyncio.run(_drain_pending_tasks())

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    body = resp.json()
    assert body["model_status"] == "done"
    assert body["build_status"] == "built"
    assert body["raw_llm_data"]["ktr_1"] is not None
    assert body["raw_llm_data"]["ktr_2"] is not None
    stages = {s["nombre"]: s for s in body["stages"]}
    assert stages["origen_stg"]["status"] == "done"
    assert stages["stg_dwh"]["status"] == "done"


# ─── D31 — reuse_stage_1 saltea la llamada al modelo de la etapa 1 ───────────

def test_reuse_stage_1_skips_first_llm_call(client):
    llm = _fake_llm_counting()
    app.dependency_overrides[get_main_llm] = lambda: llm

    reused_stage_1 = copy.deepcopy(_KTR_JSON)

    resp = client.post(
        "/api/v1/etl/generate-async",
        json=_req_body(reuse_stage_1=reused_stage_1),
    )
    job_id = resp.json()["job_id"]

    resp = client.post(
        f"/api/v1/etl/{job_id}/connections",
        json={"conn_dwh": {"db_type": "postgresql", "host": "h", "port": 5432, "database": "d", "username": "u"}},
    )
    assert resp.status_code == 200, resp.text

    asyncio.run(_drain_pending_tasks())

    # Solo 1 llamada al modelo: la etapa 2. La etapa 1 se reusó, y dim_contracts
    # vacío hace que validate_and_correct_ddl() ni siquiera llame al modelo.
    assert llm._calls["count"] == 1

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    body = resp.json()
    assert body["build_status"] == "built"
    stages = {s["nombre"]: s for s in body["stages"]}
    assert stages["origen_stg"]["status"] == "reused"
    assert stages["stg_dwh"]["status"] == "done"
    assert "stage.reused" in _codes(body["progress"])
