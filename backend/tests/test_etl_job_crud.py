"""
Prueba CRUD de ETLs y Jobs.
Usa TestClient (no requiere servidor externo); dispara el lifespan → create_tables().
Corre con: pytest tests/test_etl_job_crud.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

FORM_DATA = {"tables": [{"name": "clientes", "columns": []}]}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


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

    # delete
    resp = client.delete(f"/api/etls/{etl_id}")
    assert resp.status_code == 204

    # verify gone
    resp = client.get(f"/api/etls/{etl_id}")
    assert resp.status_code == 404


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
