"""
Tests de Fase 1: endpoint /profile devuelve CanonicalSchema,
y context_builder._profile_from_db() produce CanonicalSchema via db_adapter.

Todos los tests usan mocks — no requieren conexión real a BD.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.connection import Connection, DbType
from app.schemas.canonical import CanonicalSchema, CanonicalType, ForeignKeyRef
from app.schemas.connection import ColumnInfo
from app.schemas.context_schemas import ColumnProfile


# ── Test DB infrastructure (SQLite in-memory, same as test_connections_api) ──

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


# ── Shared fixtures ───────────────────────────────────────────────────────────

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


def _create_conn(client, **overrides) -> str:
    resp = client.post("/api/connections", json=_pg_body(**overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


_COL_INFOS = [
    ColumnInfo(name="id",          type="integer",       nullable=False, primary_key=True),
    ColumnInfo(name="customer_id", type="integer",       nullable=False, primary_key=False),
    ColumnInfo(name="amount",      type="numeric(10,2)", nullable=True,  primary_key=False),
    ColumnInfo(name="status",      type="varchar(20)",   nullable=True,  primary_key=False),
]

_PROFILES = [
    ColumnProfile(
        name=ci.name,
        inferred_type="int" if ci.type == "integer" else "string",
        null_pct=0.0,
        distinct_count=10,
        leading_trailing_spaces_pct=0.0,
        casing_distribution={},
    )
    for ci in _COL_INFOS
]


# ── Profile endpoint tests ────────────────────────────────────────────────────

class TestProfileEndpointReturnsCanonicalSchema:
    """
    The /profile endpoint must return a CanonicalSchema (not list[ColumnProfile]).
    All DB calls are mocked so no real PostgreSQL is needed.
    """

    def _setup_mocks(self, monkeypatch):
        monkeypatch.setattr("app.routers.connections.get_columns",       lambda *a, **k: _COL_INFOS)
        monkeypatch.setattr("app.routers.connections.get_foreign_keys",  lambda *a, **k: {"public.orders": []})
        monkeypatch.setattr("app.services.profiler.fetch_db_column_stats",  lambda *a, **k: {})
        monkeypatch.setattr("app.routers.connections.get_sample_rows",   lambda *a, **k: MagicMock(rows=[], bias="row_level"))
        monkeypatch.setattr("app.services.profiler.profile_columns",     lambda *a, **k: _PROFILES)

        # build_engine + _resolve_schema used for schema resolution inside the endpoint
        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: mock_session
        mock_session.__exit__  = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_session
        monkeypatch.setattr("app.services.db_connector.build_engine",    lambda *a, **k: mock_engine)
        monkeypatch.setattr("app.services.db_connector._resolve_schema", lambda *a, **k: "public")

    def test_response_is_canonical_schema_shape(self, client, monkeypatch):
        self._setup_mocks(monkeypatch)
        conn_id = _create_conn(client)
        resp = client.get(f"/api/connections/{conn_id}/schema/tables/public.orders/profile")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "schema_version" in body
        assert body["schema_version"] == "1.0"
        assert "fields" in body
        assert "source_type" in body
        assert body["source_type"] == "database"

    def test_schema_version_is_1_0(self, client, monkeypatch):
        self._setup_mocks(monkeypatch)
        conn_id = _create_conn(client)
        resp = client.get(f"/api/connections/{conn_id}/schema/tables/public.orders/profile")
        assert resp.json()["schema_version"] == "1.0"

    def test_fields_contain_all_columns(self, client, monkeypatch):
        self._setup_mocks(monkeypatch)
        conn_id = _create_conn(client)
        resp = client.get(f"/api/connections/{conn_id}/schema/tables/public.orders/profile")
        fields = resp.json()["fields"]
        assert len(fields) == len(_COL_INFOS)
        assert [f["name"] for f in fields] == [ci.name for ci in _COL_INFOS]

    def test_primary_key_detected(self, client, monkeypatch):
        self._setup_mocks(monkeypatch)
        conn_id = _create_conn(client)
        resp = client.get(f"/api/connections/{conn_id}/schema/tables/public.orders/profile")
        body = resp.json()
        id_field = next(f for f in body["fields"] if f["name"] == "id")
        assert id_field["is_primary_key"] is True
        assert "id" in body["primary_key"]

    def test_non_pk_not_marked(self, client, monkeypatch):
        self._setup_mocks(monkeypatch)
        conn_id = _create_conn(client)
        resp = client.get(f"/api/connections/{conn_id}/schema/tables/public.orders/profile")
        amount_field = next(f for f in resp.json()["fields"] if f["name"] == "amount")
        assert amount_field["is_primary_key"] is False

    def test_canonical_type_integer(self, client, monkeypatch):
        self._setup_mocks(monkeypatch)
        conn_id = _create_conn(client)
        resp = client.get(f"/api/connections/{conn_id}/schema/tables/public.orders/profile")
        id_field = next(f for f in resp.json()["fields"] if f["name"] == "id")
        assert id_field["type"] == "integer"

    def test_canonical_type_number_with_precision_scale(self, client, monkeypatch):
        self._setup_mocks(monkeypatch)
        conn_id = _create_conn(client)
        resp = client.get(f"/api/connections/{conn_id}/schema/tables/public.orders/profile")
        amount = next(f for f in resp.json()["fields"] if f["name"] == "amount")
        assert amount["type"] == "number"
        assert amount["precision"] == 10
        assert amount["scale"] == 2

    def test_profile_embedded_in_response(self, client, monkeypatch):
        self._setup_mocks(monkeypatch)
        conn_id = _create_conn(client)
        resp = client.get(f"/api/connections/{conn_id}/schema/tables/public.orders/profile")
        body = resp.json()
        assert "profile" in body
        assert body["profile"] is not None
        assert "column_profiles" in body["profile"]
        assert len(body["profile"]["column_profiles"]) == len(_COL_INFOS)

    def test_inferred_by_database(self, client, monkeypatch):
        self._setup_mocks(monkeypatch)
        conn_id = _create_conn(client)
        resp = client.get(f"/api/connections/{conn_id}/schema/tables/public.orders/profile")
        for field in resp.json()["fields"]:
            assert field["inferred_by"] == "database"

    def test_404_when_connection_not_found(self, client, monkeypatch):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/connections/{fake_id}/schema/tables/orders/profile")
        assert resp.status_code == 404

    def test_foreign_keys_embedded(self, client, monkeypatch):
        fk_data = {
            "public.orders": [
                ForeignKeyRef(
                    fields=["customer_id"],
                    reference_resource="public.customers",
                    reference_fields=["id"],
                )
            ]
        }
        monkeypatch.setattr("app.routers.connections.get_columns",      lambda *a, **k: _COL_INFOS)
        monkeypatch.setattr("app.routers.connections.get_foreign_keys", lambda *a, **k: fk_data)
        monkeypatch.setattr("app.services.profiler.fetch_db_column_stats", lambda *a, **k: {})
        monkeypatch.setattr("app.routers.connections.get_sample_rows",  lambda *a, **k: MagicMock(rows=[], bias="row_level"))
        monkeypatch.setattr("app.services.profiler.profile_columns",    lambda *a, **k: _PROFILES)
        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: mock_session
        mock_session.__exit__  = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_session
        monkeypatch.setattr("app.services.db_connector.build_engine",    lambda *a, **k: mock_engine)
        monkeypatch.setattr("app.services.db_connector._resolve_schema", lambda *a, **k: "public")

        conn_id = _create_conn(client)
        resp = client.get(f"/api/connections/{conn_id}/schema/tables/public.orders/profile")
        body = resp.json()
        assert len(body["foreign_keys"]) == 1
        assert body["foreign_keys"][0]["reference_resource"] == "public.customers"
        fk_col = next(f for f in body["fields"] if f["name"] == "customer_id")
        assert fk_col["is_foreign_key"] is True


# ── context_builder tests ─────────────────────────────────────────────────────

class TestContextBuilderDbPath:
    """
    build_model_context() with a DB source must route through _profile_from_db()
    and produce a correct ModelContext using canonical_to_model_context().
    """

    def _make_table(self, conn_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            tableName="public.orders",
            connection_id=conn_id,
            schema_name="public",
            columns=[
                SimpleNamespace(name="id",     dataType="int",    data=[]),
                SimpleNamespace(name="amount", dataType="float",  data=[]),
            ],
        )

    def _make_db_session(self, conn_id: str) -> MagicMock:
        fake_conn = MagicMock(spec=Connection)
        fake_conn.db_type = DbType.postgresql
        fake_conn.schema_name = "public"

        db = MagicMock()
        db.get.return_value = fake_conn
        return db

    def test_db_path_returns_model_context(self, monkeypatch):
        from app.services.context_builder import build_model_context

        conn_id = str(uuid.uuid4())
        table   = self._make_table(conn_id)
        db      = self._make_db_session(conn_id)

        mock_schema = CanonicalSchema(
            source_name="public.orders",
            source_type="database",
            fields=[],
        )
        monkeypatch.setattr(
            "app.services.context_builder._profile_from_db",
            lambda t, s: mock_schema,
        )

        ctx = build_model_context([table], db)
        assert len(ctx.source_tables) == 1
        assert ctx.source_tables[0].table_name == "public.orders"

    def test_memory_path_unchanged(self, monkeypatch):
        from app.services.context_builder import build_model_context

        table = SimpleNamespace(
            tableName="csv_table",
            connection_id=None,
            columns=[
                SimpleNamespace(name="col1", dataType="string", data=["a", "b"]),
            ],
        )

        ctx = build_model_context([table], db=None)
        assert len(ctx.source_tables) == 1
        assert ctx.source_tables[0].table_name == "csv_table"

    def test_fallback_schema_used_when_db_fails(self, monkeypatch):
        from app.services.context_builder import build_model_context

        conn_id = str(uuid.uuid4())
        table   = SimpleNamespace(
            tableName="public.orders",
            connection_id=conn_id,
            schema_name="public",
            columns=[
                SimpleNamespace(name="id", dataType="int", data=[]),
            ],
        )
        db = MagicMock()
        db.get.return_value = None  # connection not found → triggers fallback

        ctx = build_model_context([table], db)
        assert len(ctx.source_tables) == 1
        # Fallback produces context with the column from ColumnaOrigen
        assert ctx.source_tables[0].columns[0].name == "id"

    def test_schema_from_columnas_origen_unknown_type(self):
        from app.services.context_builder import _schema_from_columnas_origen

        table = SimpleNamespace(
            tableName="t",
            columns=[
                SimpleNamespace(name="x", dataType="exotic_type", data=[]),
            ],
        )
        schema = _schema_from_columnas_origen(table)
        assert schema.source_type == "database"
        assert schema.fields[0].type == CanonicalType.UNKNOWN

    def test_schema_from_columnas_origen_known_types(self):
        from app.services.context_builder import _schema_from_columnas_origen

        table = SimpleNamespace(
            tableName="t",
            columns=[
                SimpleNamespace(name="a", dataType="int",    data=[]),
                SimpleNamespace(name="b", dataType="float",  data=[]),
                SimpleNamespace(name="c", dataType="bool",   data=[]),
                SimpleNamespace(name="d", dataType="date",   data=[]),
                SimpleNamespace(name="e", dataType="string", data=[]),
            ],
        )
        schema = _schema_from_columnas_origen(table)
        types = {f.name: f.type for f in schema.fields}
        assert types["a"] == CanonicalType.INTEGER
        assert types["b"] == CanonicalType.NUMBER
        assert types["c"] == CanonicalType.BOOLEAN
        assert types["d"] == CanonicalType.DATE
        assert types["e"] == CanonicalType.STRING
