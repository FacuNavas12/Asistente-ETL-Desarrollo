"""
Prueba CRUD de ETLs y Jobs.
Usa TestClient (no requiere servidor externo) contra un engine SQLite en memoria
propio — no depende del lifespan de la app ni de settings.database_url.
Corre con: pytest tests/test_etl_job_crud.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database as database
from app.core.database import Base
from app.main import app
from app.models.etl import Etl
from app.outbox import get_outbox
from app.outbox.runner import run_drain_once_sync

FORM_DATA = {"tables": [{"name": "clientes", "columns": []}]}

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(bind=_engine)


@pytest.fixture(autouse=True)
def _clean_db(monkeypatch):
    # Etl/Job usan el patron outbox: el drain task del lifespan llama a
    # _get_session_factory() directo (no via Depends), asi que overridear
    # get_db no alcanza para que rutas y drain vean la misma DB. Apuntamos
    # los singletons globales de app.core.database al engine de test.
    monkeypatch.setattr(database, "_engine", _engine)
    monkeypatch.setattr(database, "_SessionLocal", _Session)
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _force_drain():
    """create/update van al outbox, no directo a la DB; delete_etl() sí lee
    directo de la DB. Esperar al drain task en background (asyncio, con su
    propio backoff de 5s+) es lento e inherentemente no determinístico.
    run_drain_once_sync() es el mismo drain, sincrónico — lo forzamos acá
    en vez de sondear con timeouts."""
    run_drain_once_sync(get_outbox(), database._get_session_factory())


# ── ETL ───────────────────────────────────────────────────────────────────────

def test_etl_create_returns_camel_keys(client):
    resp = client.post("/api/etls/", json={"name": "Test ETL", "formData": FORM_DATA, "status": "pending"})
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert "createdAt" in data
    assert "updatedAt" in data
    assert "formData" in data
    assert data["name"] == "Test ETL"
    assert data["status"] == "pending"
    assert data["result"] is None
    # cleanup
    _force_drain()
    client.delete(f"/api/etls/{data['id']}")


def test_etl_full_lifecycle(client):
    # create
    resp = client.post("/api/etls/", json={"name": "Lifecycle ETL", "status": "pending"})
    assert resp.status_code == 201
    etl_id = resp.json()["id"]

    # list — must include new id
    resp = client.get("/api/etls/")
    assert resp.status_code == 200
    assert any(e["id"] == etl_id for e in resp.json())

    # get by id
    resp = client.get(f"/api/etls/{etl_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == etl_id

    # 404 unknown id
    resp = client.get("/api/etls/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404

    # patch status
    resp = client.patch(f"/api/etls/{etl_id}/status", json={"status": "en_proceso"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "en_proceso"

    # put (partial update)
    resp = client.put(f"/api/etls/{etl_id}", json={"result": {"ktr": "xml..."}, "status": "done"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"

    # delete (forzar drain del ultimo snapshot antes de leer/borrar directo de la DB)
    _force_drain()
    resp = client.delete(f"/api/etls/{etl_id}")
    assert resp.status_code == 204

    # verify gone
    resp = client.get(f"/api/etls/{etl_id}")
    assert resp.status_code == 404


def test_delete_synced_etl_does_not_resurrect(client):
    """Regresion: delete_etl() antes solo borraba de la DB, no del outbox —
    get_etl() volvia a mostrarlo via su fallback de 'outbox synced pero ya
    no esta en la DB'."""
    resp = client.post("/api/etls/", json={"name": "Synced ETL", "status": "pending"})
    etl_id = resp.json()["id"]
    _force_drain()  # ahora esta synced tanto en el outbox como en la DB

    resp = client.delete(f"/api/etls/{etl_id}")
    assert resp.status_code == 204

    resp = client.get(f"/api/etls/{etl_id}")
    assert resp.status_code == 404

    resp = client.get("/api/etls/")
    assert resp.status_code == 200
    assert all(e["id"] != etl_id for e in resp.json())


def test_delete_pending_etl_prevents_supabase_write(client):
    """Regresion: borrar un ETL que todavia no drenó (solo existe en el
    outbox) debe cancelar el enqueue — el drain no debe reinsertarlo."""
    resp = client.post("/api/etls/", json={"name": "Pending ETL", "status": "pending"})
    etl_id = resp.json()["id"]

    # borrar ANTES de que el drain corra — solo esta en el outbox todavia
    resp = client.delete(f"/api/etls/{etl_id}")
    assert resp.status_code == 204

    _force_drain()  # si el bug siguiera vivo, esto lo insertaria en la DB recien ahora

    resp = client.get(f"/api/etls/{etl_id}")
    assert resp.status_code == 404

    db = _Session()
    try:
        assert db.get(Etl, etl_id) is None
    finally:
        db.close()


# ── Job ───────────────────────────────────────────────────────────────────────

def test_job_full_lifecycle(client):
    # create
    resp = client.post("/api/jobs/", json={"name": "Lifecycle Job", "status": "pending"})
    assert resp.status_code == 201
    job_id = resp.json()["id"]
    assert "createdAt" in resp.json()

    # list
    resp = client.get("/api/jobs/")
    assert resp.status_code == 200
    assert any(j["id"] == job_id for j in resp.json())

    # patch status → en_proceso
    resp = client.patch(f"/api/jobs/{job_id}/status", json={"status": "en_proceso"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "en_proceso"

    # patch status → done
    resp = client.patch(f"/api/jobs/{job_id}/status", json={"status": "done"})
    assert resp.status_code == 200

    # delete
    resp = client.delete(f"/api/jobs/{job_id}")
    assert resp.status_code == 204

    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 404
