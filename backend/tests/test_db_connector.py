"""Tests para funciones utilitarias de db_connector (sin conexión real a BD)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models.connection import DbType
from app.services.db_connector import (
    _build_url,
    _sanitize_error,
    list_tables,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

class _FakeConn:
    username = "user"
    encrypted_password = b"dummy"
    host = "localhost"
    port = 5432
    database = "testdb"
    ssl_mode = None
    extra_options = None
    db_type = DbType.postgresql


def _make(db_type=DbType.postgresql, ssl_mode=None, extra_options=None, port=5432) -> _FakeConn:
    c = _FakeConn()
    c.db_type = db_type
    c.ssl_mode = ssl_mode
    c.extra_options = extra_options
    c.port = port
    return c


# ─── _sanitize_error (alias de sanitize_error) ────────────────────────────────

class TestSanitizeError:
    def test_removes_password_param(self):
        msg = "could not connect: password=supersecret host=localhost"
        result = _sanitize_error(msg)
        assert "supersecret" not in result
        assert "password=***" in result

    def test_removes_url_password(self):
        msg = "Error: postgresql+psycopg://user:mysecretpass@localhost:5432/db"
        result = _sanitize_error(msg)
        assert "mysecretpass" not in result

    def test_removes_pwd_param(self):
        msg = "Connection string: Server=host;PWD=s3cr3t;Database=db"
        result = _sanitize_error(msg)
        assert "s3cr3t" not in result
        assert "PWD=***" in result

    def test_truncates_long_messages(self):
        long_msg = "x" * 1000
        result = _sanitize_error(long_msg)
        assert len(result) <= 500

    def test_short_message_unchanged_length(self):
        msg = "Connection refused"
        result = _sanitize_error(msg)
        assert result == msg

    def test_no_sensitive_data_passes_through(self):
        msg = "host unreachable"
        assert _sanitize_error(msg) == msg


# ─── _build_url ───────────────────────────────────────────────────────────────

class TestBuildUrl:
    def test_build_url_postgres_with_extra_options(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.db_connector.decrypt_password", lambda _: "secret"
        )
        conn = _make(extra_options={"application_name": "etl"})
        url = _build_url(conn)
        assert "application_name=etl" in url

    def test_build_url_mssql_with_trust_server_certificate(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.db_connector.decrypt_password", lambda _: "secret"
        )
        conn = _make(
            db_type=DbType.sqlserver,
            extra_options={"trust_server_certificate": True},
            port=1433,
        )
        url = _build_url(conn)
        assert "TrustServerCertificate=yes" in url

    def test_build_url_mssql_ssl_disable_sets_encrypt_no(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.db_connector.decrypt_password", lambda _: "secret"
        )
        conn = _make(db_type=DbType.sqlserver, ssl_mode="disable", port=1433)
        url = _build_url(conn)
        assert "Encrypt=no" in url

    def test_build_url_mssql_ssl_require_sets_encrypt_yes(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.db_connector.decrypt_password", lambda _: "secret"
        )
        conn = _make(db_type=DbType.sqlserver, ssl_mode="require", port=1433)
        url = _build_url(conn)
        assert "Encrypt=yes" in url

    def test_build_url_mssql_uses_configurable_driver(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.db_connector.decrypt_password", lambda _: "secret"
        )
        monkeypatch.setattr(
            "app.services.db_connector.settings",
            MagicMock(mssql_odbc_driver="My Custom Driver"),
        )
        conn = _make(db_type=DbType.sqlserver, port=1433)
        url = _build_url(conn)
        assert "My+Custom+Driver" in url or "My Custom Driver" in url


# ─── list_tables multi-schema ─────────────────────────────────────────────────

class TestListTablesMultiSchema:
    def test_excludes_system_schemas_and_returns_schema_dot_table(self, monkeypatch):
        def _get_table_names(schema=None):
            return {
                "public": ["orders", "customers"],
                "staging": ["raw_orders"],
                "information_schema": ["columns"],   # sistema → excluir
                "pg_catalog": ["pg_class"],           # sistema → excluir
            }.get(schema, [])

        mock_inspector = MagicMock()
        mock_inspector.get_schema_names.return_value = [
            "public", "staging", "information_schema", "pg_catalog"
        ]
        mock_inspector.get_table_names.side_effect = _get_table_names
        mock_engine = MagicMock()

        monkeypatch.setattr(
            "app.services.db_connector.build_engine", lambda _conn: mock_engine
        )
        monkeypatch.setattr(
            "app.services.db_connector.inspect", lambda _engine: mock_inspector
        )

        result = list_tables(_make())

        assert "public.orders" in result
        assert "public.customers" in result
        assert "staging.raw_orders" in result
        assert not any("information_schema" in t for t in result)
        assert not any("pg_catalog" in t for t in result)
        assert result == sorted(result)
