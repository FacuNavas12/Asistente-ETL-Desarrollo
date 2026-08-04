"""Tests de integración para /api/connections usando SQLite en memoria."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import require_auth
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
    app.dependency_overrides.pop(require_auth, None)


def _login_as(sub: str) -> None:
    """Simula un caller autenticado con ese claim 'sub', sin pasar por JWKS real."""
    app.dependency_overrides[require_auth] = lambda: {"sub": sub}


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
        _ = row.last_test_status, row.last_tested_at
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


def test_connection_has_no_password_column(client):
    # El backend ya no custodia contraseñas de conexión (ver decisión de
    # diseño) — no queda ninguna columna donde persistirlo.
    data = _create(client)
    assert not hasattr(_get_conn_row(data["id"]), "encrypted_password")


def test_update_ignores_password_field_it_no_longer_persists(client):
    # ConnectionUpdate ya no declara "password" — un cliente que lo siga
    # mandando (por costumbre, o un frontend viejo) no debe romper nada ni
    # hacer que el valor aparezca en ningún lado de la respuesta.
    data = _create(client)

    resp = client.put(
        f"/api/connections/{data['id']}",
        json={"password": "algo_que_nunca_deberia_persistir", "host": "changed"},
    )
    assert resp.status_code == 200
    assert resp.json()["host"] == "changed"
    assert "algo_que_nunca_deberia_persistir" not in resp.text
    assert resp.json()["password"] == "********"


def test_test_endpoint_requires_password_header(client):
    data = _create(client)
    resp = client.post(f"/api/connections/{data['id']}/test")
    assert resp.status_code == 422  # falta el header X-DB-Password


def test_test_endpoint_updates_status(client, monkeypatch):
    data = _create(client)
    conn_id = data["id"]
    headers = {"X-DB-Password": "s3cr3t"}

    # ── éxito
    monkeypatch.setattr(
        "app.routers.connections.svc_test",
        lambda _conn, _password: ConnectionTestResult(success=True, message="OK"),
    )
    resp = client.post(f"/api/connections/{conn_id}/test", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    row = _get_conn_row(conn_id)
    assert row.last_test_status == TestStatus.success
    assert row.last_tested_at is not None

    # ── fallo
    monkeypatch.setattr(
        "app.routers.connections.svc_test",
        lambda _conn, _password: ConnectionTestResult(success=False, message="Timeout"),
    )
    resp = client.post(f"/api/connections/{conn_id}/test", headers=headers)
    assert resp.json()["success"] is False
    assert _get_conn_row(conn_id).last_test_status == TestStatus.failed


# ─── Ownership (hallazgo B) ───────────────────────────────────────────────────

def test_create_assigns_owner_from_auth_sub_not_from_body(client):
    _login_as("user-a")
    data = _create(client, owner_id=str(uuid.uuid4()))  # ya no existe el campo, se ignora
    assert _get_conn_row(data["id"]).owner_id == "user-a"


def test_cross_owner_access_returns_404_on_every_verb(client):
    _login_as("user-a")
    conn_id = _create(client)["id"]
    headers = {"X-DB-Password": "whatever"}  # el 404 de ownership gana antes de intentar conectar

    _login_as("user-b")
    assert client.get(f"/api/connections/{conn_id}").status_code == 404
    assert client.put(f"/api/connections/{conn_id}", json={"host": "x"}).status_code == 404
    assert client.post(f"/api/connections/{conn_id}/test", headers=headers).status_code == 404
    assert client.get(f"/api/connections/{conn_id}/schema/tables", headers=headers).status_code == 404
    assert client.get(f"/api/connections/{conn_id}/schema/tables/foo/columns", headers=headers).status_code == 404
    assert client.get(f"/api/connections/{conn_id}/schema/tables/foo/profile", headers=headers).status_code == 404
    assert client.get(
        f"/api/connections/{conn_id}/schema/table-data?schema=public&table=foo", headers=headers
    ).status_code == 404
    assert client.delete(f"/api/connections/{conn_id}").status_code == 404

    # el dueño real sigue teniendo acceso — la fila no se borró en el intento de arriba.
    _login_as("user-a")
    assert client.get(f"/api/connections/{conn_id}").status_code == 200


def test_list_connections_never_returns_other_owner_rows(client):
    _login_as("user-a")
    _create(client, name="conn_a")

    _login_as("user-b")
    _create(client, name="conn_b")
    names = [c["name"] for c in client.get("/api/connections").json()]
    assert names == ["conn_b"]


def test_dev_mode_without_auth_override_skips_ownership(client):
    # Sin _login_as: require_auth real corre con AUTH_REQUIRED=false → payload
    # None → owner None → ningún filtro de ownership se aplica (comportamiento
    # actual preservado para desarrollo local).
    data = _create(client)
    assert _get_conn_row(data["id"]).owner_id is None
    assert client.get(f"/api/connections/{data['id']}").status_code == 200
