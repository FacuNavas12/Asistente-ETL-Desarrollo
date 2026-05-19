"""Tests para schemas Pydantic del módulo de conexiones."""
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.connection import (
    ColumnInfo,
    ConnectionRead,
    ConnectionTestResult,
    ConnectionUpdate,
    PostgresConnectionCreate,
    SqlServerConnectionCreate,
)
from app.models.connection import DbType, TestStatus


# ─── PostgresConnectionCreate ─────────────────────────────────────────────────

class TestPostgresConnectionCreate:
    def _valid(self, **overrides):
        data = dict(
            name="mi_conn",
            host="localhost",
            port=5432,
            database="etl_db",
            username="user",
            password="secret",
        )
        data.update(overrides)
        return PostgresConnectionCreate(**data)

    def test_happy_path(self):
        c = self._valid()
        assert c.db_type == DbType.postgresql
        assert c.ssl_mode is None

    def test_ssl_mode_valid(self):
        c = self._valid(ssl_mode="require")
        assert c.ssl_mode == "require"

    def test_ssl_mode_invalid(self):
        with pytest.raises(ValidationError):
            self._valid(ssl_mode="invalid_mode")

    def test_port_too_low(self):
        with pytest.raises(ValidationError):
            self._valid(port=0)

    def test_port_too_high(self):
        with pytest.raises(ValidationError):
            self._valid(port=65536)

    def test_port_boundaries(self):
        assert self._valid(port=1).port == 1
        assert self._valid(port=65535).port == 65535

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(name="")

    def test_empty_password_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(password="")

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            self._valid(name="x" * 256)


# ─── SqlServerConnectionCreate ────────────────────────────────────────────────

class TestSqlServerConnectionCreate:
    def test_db_type_is_sqlserver(self):
        c = SqlServerConnectionCreate(
            name="ss_conn",
            host="sqlserver.host",
            port=1433,
            database="db",
            username="sa",
            password="pass",
        )
        assert c.db_type == DbType.sqlserver


# ─── ConnectionUpdate ─────────────────────────────────────────────────────────

class TestConnectionUpdate:
    def test_all_optional(self):
        u = ConnectionUpdate()
        assert u.model_dump(exclude_unset=True) == {}

    def test_partial_update(self):
        u = ConnectionUpdate(port=5433, username="new_user")
        data = u.model_dump(exclude_unset=True)
        assert data == {"port": 5433, "username": "new_user"}

    def test_port_validation_on_update(self):
        with pytest.raises(ValidationError):
            ConnectionUpdate(port=0)


# ─── ConnectionRead — password masking ───────────────────────────────────────

class TestConnectionRead:
    def _make_orm_like(self, **overrides):
        """Simula un objeto ORM con from_attributes=True."""
        class FakeConn:
            id = uuid.uuid4()
            name = "test"
            db_type = DbType.postgresql
            host = "localhost"
            port = 5432
            database = "db"
            username = "u"
            encrypted_password = b"anything"
            ssl_mode = None
            extra_options = None
            owner_id = None
            created_at = datetime.now(timezone.utc)
            updated_at = datetime.now(timezone.utc)
            last_tested_at = None
            last_test_status = None

        for k, v in overrides.items():
            setattr(FakeConn, k, v)
        return FakeConn()

    def test_password_always_masked(self):
        read = ConnectionRead.model_validate(self._make_orm_like())
        assert read.password == "********"

    def test_encrypted_password_not_exposed(self):
        read = ConnectionRead.model_validate(self._make_orm_like())
        data = read.model_dump()
        assert "encrypted_password" not in data

    def test_last_test_status_included(self):
        read = ConnectionRead.model_validate(
            self._make_orm_like(last_test_status=TestStatus.success)
        )
        assert read.last_test_status == TestStatus.success


# ─── ConnectionTestResult ─────────────────────────────────────────────────────

class TestConnectionTestResult:
    def test_success(self):
        r = ConnectionTestResult(success=True, message="OK")
        assert r.success is True

    def test_failure(self):
        r = ConnectionTestResult(success=False, message="Timeout")
        assert r.success is False


# ─── ColumnInfo ───────────────────────────────────────────────────────────────

class TestColumnInfo:
    def test_basic(self):
        c = ColumnInfo(name="id", type="INTEGER", nullable=False, primary_key=True)
        assert c.primary_key is True
        assert c.default is None
