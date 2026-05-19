"""Tests de integración para /api/connections usando SQLite en memoria."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.crypto import decrypt_password
from app.core.database import Base, get_db
from app.main import app
from app.models.connection import Connection, DbType, TestStatus
from app.schemas.connection import ConnectionTestResult

# ─── Infraestructura de BD de test ───────────────────────────────────────────
# StaticPool asegura que todas las sesiones comparten la misma conexión
# en memoria, por lo que los datos commitidos son visibles entre sesiones.

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(bind=_engine)


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def client():
    def _override_get_db():
        db = _Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _pg_body(**overrides) -> dict:
    base = {
        "db_type": "postgresql",
        "name": "test_conn",
        "host": "localhost",
        "port": 5432,
        "database": "testdb",
        "username": "user",
        "password": "secret",
    }
    base.update(overrides)
    return base


def _create(client, **overrides) -> dict:
    resp = client.post("/api/connections", json=_pg_body(**overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _get_conn_row(conn_id: str) -> Connection:
    db = _Session()
    try:
        row = db.get(Connection, uuid.UUID(conn_id))
        # Accedemos a los campos que necesitamos mientras la sesión está abierta.
        _ = row.encrypted_password, row.last_test_status, row.last_tested_at
        return row
    finally:
        db.close()


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_create_returns_masked_password(client):
    data = _create(client)
    assert data["password"] == "********"
    assert "secret" not in str(data)

    resp = client.get(f"/api/connections/{data['id']}")
    assert resp.status_code == 200
    assert resp.json()["password"] == "********"


def test_update_without_password_does_not_touch_encrypted(client):
    data = _create(client)
    original_enc = _get_conn_row(data["id"]).encrypted_password

    resp = client.put(f"/api/connections/{data['id']}", json={"host": "newhost"})
    assert resp.status_code == 200
    assert resp.json()["host"] == "newhost"

    assert _get_conn_row(data["id"]).encrypted_password == original_enc


def test_update_with_password_reencrypts(client):
    data = _create(client)
    new_pass = "totalmente_nuevo"

    resp = client.put(f"/api/connections/{data['id']}", json={"password": new_pass})
    assert resp.status_code == 200

    new_enc = _get_conn_row(data["id"]).encrypted_password
    assert decrypt_password(new_enc) == new_pass


def test_update_with_null_password_is_ignored(client):
    data = _create(client)
    original_enc = _get_conn_row(data["id"]).encrypted_password

    resp = client.put(
        f"/api/connections/{data['id']}",
        json={"password": None, "host": "changed"},
    )
    assert resp.status_code == 200

    row = _get_conn_row(data["id"])
    assert row.encrypted_password == original_enc
    assert row.host == "changed"


def test_test_endpoint_updates_status(client, monkeypatch):
    data = _create(client)
    conn_id = data["id"]

    # ── éxito
    monkeypatch.setattr(
        "app.routers.connections.svc_test",
        lambda _conn: ConnectionTestResult(success=True, message="OK"),
    )
    resp = client.post(f"/api/connections/{conn_id}/test")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    row = _get_conn_row(conn_id)
    assert row.last_test_status == TestStatus.success
    assert row.last_tested_at is not None

    # ── fallo
    monkeypatch.setattr(
        "app.routers.connections.svc_test",
        lambda _conn: ConnectionTestResult(success=False, message="Timeout"),
    )
    resp = client.post(f"/api/connections/{conn_id}/test")
    assert resp.json()["success"] is False
    assert _get_conn_row(conn_id).last_test_status == TestStatus.failed
