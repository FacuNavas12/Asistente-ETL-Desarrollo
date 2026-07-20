"""
Unit tests para el mapeo DbType->Kettle y resolve_real_connections() en
ktr_builder.py.

El backend ya no persiste passwords de conexión (ver decisión de diseño) —
resolve_real_connections ya no arma un dict "real" con credenciales, solo
valida existencia + ownership y reporta warning en todos los casos. El
próximo cambio reintroduce metadata real (host/port/db/user) en el .ktr,
dejando el password como variable de Kettle — ver test_ktr_connection_golden.py
para la cobertura de ese comportamiento final.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.connection import Connection, DbType
from app.services.ktr_builder import (
    _DB_TYPE_TO_KETTLE,
    _build_connection,
    build_ktr,
    resolve_real_connections,
)
from xml.etree.ElementTree import Element, tostring

_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
_Session = sessionmaker(bind=_engine)


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def db():
    session = _Session()
    try:
        yield session
    finally:
        session.close()


def _make_connection(db, db_type: DbType, **overrides) -> Connection:
    base = dict(
        name="test_conn",
        db_type=db_type,
        host="dbhost.internal",
        port=5432 if db_type == DbType.postgresql else 1433,
        database="mydb",
        username="myuser",
    )
    base.update(overrides)
    conn = Connection(**base)
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


# ─── ownership (hallazgo B) ────────────────────────────────────────────────────
# Sin este chequeo, un connections_map armado a mano con el UUID de la conexión
# de otro usuario dejaba desofuscar y embeber su password en el .ktr resultante.

def test_resolve_rejects_connection_of_a_different_owner(db):
    conn = _make_connection(db, DbType.postgresql, owner_id="user-a")
    real, warnings = resolve_real_connections({"conn_dwh": str(conn.id)}, db, owner="user-b")

    assert real == {}
    assert "conn_dwh" in warnings[0]


def test_resolve_allows_connection_of_the_same_owner(db):
    # "Allows" hoy significa "no lo rechaza por ownership" — no arma
    # credenciales reales (ver módulo docstring, pendiente del próximo cambio).
    conn = _make_connection(db, DbType.postgresql, owner_id="user-a")
    real, warnings = resolve_real_connections({"conn_dwh": str(conn.id)}, db, owner="user-a")

    assert real == {}
    assert "conn_dwh" in warnings[0]


def test_resolve_owner_none_skips_ownership_check(db):
    # owner=None (AUTH_REQUIRED=false) — comportamiento actual preservado,
    # no rechaza por ownership sin importar de quién sea la conexión.
    conn = _make_connection(db, DbType.postgresql, owner_id="user-a")
    real, warnings = resolve_real_connections({"conn_dwh": str(conn.id)}, db, owner=None)

    assert real == {}
    assert "conn_dwh" in warnings[0]


# ─── resolve_real_connections ─────────────────────────────────────────────────
# El backend ya no arma un dict "real" con credenciales (ver decisión de
# diseño) — toda conexión encontrada y con ownership válido igual cae en el
# mismo warning informativo que antes usaban solo las no encontradas.

def test_resolve_found_connection_still_produces_no_credentials(db):
    conn = _make_connection(db, DbType.postgresql)
    real, warnings = resolve_real_connections({"conn_dwh": str(conn.id)}, db)

    assert real == {}
    assert len(warnings) == 1
    assert "conn_dwh" in warnings[0]


def test_resolve_sqlserver_connection_also_produces_no_credentials(db):
    conn = _make_connection(db, DbType.sqlserver, port=1433)
    real, warnings = resolve_real_connections({"conn_staging": str(conn.id)}, db)

    assert real == {}
    assert "conn_staging" in warnings[0]


def test_resolve_missing_connection_id_produces_warning(db):
    fake_id = str(uuid.uuid4())
    real, warnings = resolve_real_connections({"conn_dwh": fake_id}, db)

    assert real == {}
    assert len(warnings) == 1
    assert "conn_dwh" in warnings[0]


def test_resolve_invalid_uuid_produces_warning(db):
    real, warnings = resolve_real_connections({"conn_dwh": "not-a-uuid"}, db)

    assert real == {}
    assert "conn_dwh" in warnings[0]


def test_resolve_empty_map_returns_nothing(db):
    real, warnings = resolve_real_connections({}, db)
    assert real == {}
    assert warnings == []

    real, warnings = resolve_real_connections(None, db)
    assert real == {}
    assert warnings == []


def test_resolve_skips_none_values(db):
    real, warnings = resolve_real_connections({"conn_origen": None}, db)
    assert real == {}
    assert warnings == []


# ─── _DB_TYPE_TO_KETTLE mapping ────────────────────────────────────────────────

def test_engine_mapping_covers_both_db_types():
    assert _DB_TYPE_TO_KETTLE["postgresql"]["type"] == "POSTGRESQL"
    assert _DB_TYPE_TO_KETTLE["sqlserver"]["type"] == "MSSQLNATIVE"


# ─── _build_connection XML output ─────────────────────────────────────────────

def test_build_connection_with_real_data_writes_resolved_fields():
    trans = Element("transformation")
    real = {
        "host": "prodhost", "port": 5432, "database": "proddb",
        "username": "produser", "password": "Encrypted abc123", "type": "POSTGRESQL", "access": "Native",
    }
    _build_connection(trans, {"name": "conn_dwh"}, real=real)
    xml = tostring(trans, encoding="unicode")

    assert "<name>conn_dwh</name>" in xml
    assert "<server>prodhost</server>" in xml
    assert "<database>proddb</database>" in xml
    assert "<username>produser</username>" in xml
    assert "<password>Encrypted abc123</password>" in xml
    assert "PLACEHOLDER" not in xml


def test_build_connection_without_real_data_falls_back_to_placeholder_empty_password():
    trans = Element("transformation")
    _build_connection(trans, {"name": "conn_origen"})
    xml = tostring(trans, encoding="unicode")

    assert "PLACEHOLDER_HOST" in xml
    assert "<password></password>" in xml or "<password />" in xml


# ─── build_ktr integración: conexión real inyectada + warnings ────────────────

def test_build_ktr_injects_real_connection_and_reports_no_warnings(db):
    conn = _make_connection(db, DbType.postgresql, name="dwh_conn")
    real, resolve_warnings = resolve_real_connections({"conn_dwh": str(conn.id)}, db)

    ktr_data = {
        "name": "test_proc",
        "description": "",
        "connections": [{"name": "conn_dwh", "type": "GENERIC", "host": "PLACEHOLDER_HOST", "database": "PLACEHOLDER_DATABASE", "port": 0, "username": "PLACEHOLDER_USER"}],
        "steps": [
            {"name": "Leer", "type": "TableInput", "config": {"connection": "conn_dwh", "sql": "SELECT 1"}},
            {"name": "Escribir", "type": "TableOutput", "config": {"connection": "conn_dwh", "table": "dim_x"}},
        ],
        "hops": [{"from": "Leer", "to": "Escribir", "enabled": True}],
    }

    xml, filename, warnings = build_ktr(ktr_data, "test_proc", real_connections=real)

    assert "<server>dbhost.internal</server>" in xml
    assert "<type>POSTGRESQL</type>" in xml
    assert filename.startswith("test_proc_")
    assert warnings == []  # sin referencias huérfanas ni conexiones sin resolver


def test_build_ktr_warns_on_orphan_connection_reference():
    ktr_data = {
        "name": "test_proc",
        "description": "",
        "connections": [{"name": "conn_dwh", "type": "GENERIC", "host": "h", "database": "d", "port": 0, "username": "u"}],
        "steps": [
            {"name": "Escribir", "type": "TableOutput", "config": {"connection": "conn_inexistente", "table": "dim_x"}},
        ],
        "hops": [],
    }
    xml, filename, warnings = build_ktr(ktr_data, "test_proc")
    assert any("conn_inexistente" in w for w in warnings)
