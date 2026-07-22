"""
Unit tests para el mapeo DbType->Kettle y resolve_real_connections() en
ktr_builder.py.

El backend ya no persiste passwords de conexión (ver decisión de diseño) —
resolve_real_connections arma metadata real (host/port/db/user/tipo) pero el
password SIEMPRE es una variable de Kettle (real["password_var"]), nunca un
valor embebido, resuelto o no. build_kettle_properties_template documenta esa
variable con default vacío.
"""
from __future__ import annotations

import base64
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
    conn = _make_connection(db, DbType.postgresql, owner_id="user-a")
    real, warnings = resolve_real_connections({"conn_dwh": str(conn.id)}, db, owner="user-a")

    assert warnings == []
    assert real["conn_dwh"]["host"] == "dbhost.internal"
    assert real["conn_dwh"]["password_var"] == "DWH_DB_PASSWORD"


def test_resolve_owner_none_skips_ownership_check(db):
    # owner=None (AUTH_REQUIRED=false) — comportamiento actual preservado,
    # no rechaza por ownership sin importar de quién sea la conexión.
    conn = _make_connection(db, DbType.postgresql, owner_id="user-a")
    real, warnings = resolve_real_connections({"conn_dwh": str(conn.id)}, db, owner=None)

    assert warnings == []
    assert real["conn_dwh"]["host"] == "dbhost.internal"


# ─── resolve_real_connections ─────────────────────────────────────────────────
# Metadata real (host/port/db/user/tipo) sí se arma — el password NUNCA, ni
# resuelto ni sin resolver: siempre es una variable de Kettle.

def test_resolve_postgres_connection(db):
    conn = _make_connection(db, DbType.postgresql)
    real, warnings = resolve_real_connections({"conn_dwh": str(conn.id)}, db)

    assert warnings == []
    assert real["conn_dwh"]["host"] == "dbhost.internal"
    assert real["conn_dwh"]["port"] == 5432
    assert real["conn_dwh"]["database"] == "mydb"
    assert real["conn_dwh"]["username"] == "myuser"
    assert real["conn_dwh"]["type"] == "POSTGRESQL"
    assert real["conn_dwh"]["access"] == "Native"
    assert real["conn_dwh"]["password_var"] == "DWH_DB_PASSWORD"
    assert "password" not in real["conn_dwh"]


def test_resolve_sqlserver_connection(db):
    conn = _make_connection(db, DbType.sqlserver, port=1433)
    real, warnings = resolve_real_connections({"conn_staging": str(conn.id)}, db)

    assert warnings == []
    assert real["conn_staging"]["type"] == "MSSQLNATIVE"
    assert real["conn_staging"]["port"] == 1433
    assert real["conn_staging"]["password_var"] == "STAGING_DB_PASSWORD"


def test_resolve_unknown_logical_name_gets_generic_password_var(db):
    conn = _make_connection(db, DbType.postgresql)
    real, warnings = resolve_real_connections({"conn_custom": str(conn.id)}, db)

    assert warnings == []
    assert real["conn_custom"]["password_var"] == "CONN_CUSTOM_PASSWORD"


def test_resolve_warns_about_ssl_mode_without_embedding_it(db):
    conn = _make_connection(db, DbType.postgresql, ssl_mode="require")
    real, warnings = resolve_real_connections({"conn_dwh": str(conn.id)}, db)

    assert "conn_dwh" in warnings[0]
    assert "require" in warnings[0]
    assert "password" not in real["conn_dwh"]


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

def test_build_connection_with_real_data_writes_resolved_fields_password_as_variable():
    trans = Element("transformation")
    real = {
        "host": "prodhost", "port": 5432, "database": "proddb",
        "username": "produser", "password_var": "DWH_DB_PASSWORD",
        "type": "POSTGRESQL", "access": "Native",
    }
    undeclared = _build_connection(trans, {"name": "conn_dwh"}, real=real)
    xml = tostring(trans, encoding="unicode")

    assert "<name>conn_dwh</name>" in xml
    assert "<server>prodhost</server>" in xml
    assert "<database>proddb</database>" in xml
    assert "<username>produser</username>" in xml
    assert "<password>${DWH_DB_PASSWORD}</password>" in xml
    assert "PLACEHOLDER" not in xml
    assert undeclared == [("DWH_DB_PASSWORD", "")]


def test_build_connection_without_real_data_falls_back_to_placeholder_empty_password():
    trans = Element("transformation")
    _build_connection(trans, {"name": "conn_origen"})
    xml = tostring(trans, encoding="unicode")

    assert "PLACEHOLDER_HOST" in xml
    assert "<password></password>" in xml or "<password />" in xml


def test_password_never_appears_in_ktr_in_any_form_even_if_present_in_real_dict():
    """
    Defensa en profundidad: aunque un caller futuro le agregue por error una
    clave "password" con un valor real al dict `real` (_build_connection hoy
    solo lee real["password_var"], nunca "password"), el valor no debe
    terminar en el XML bajo ninguna representación — ni en claro, ni ofuscado
    en formato Kettle, ni en base64.

    El valor ofuscado esperado está hardcodeado (no vía kettle_crypto, que ya
    no forma parte del backend): la ofuscación de Kettle es determinística —
    XOR contra un seed fijo — así que el string no cambia.
    """
    known_password = "sup3r_s3cr3t_p4ssw0rd!"
    known_password_kettle_obfuscated = "Encrypted 73757033725dcdabccba59d3ad94ff0abd678e80ab9b"
    trans = Element("transformation")
    real = {
        "host": "prodhost", "port": 5432, "database": "proddb",
        "username": "produser", "type": "POSTGRESQL", "access": "Native",
        "password_var": "DWH_DB_PASSWORD",
        "password": known_password,  # clave que _build_connection no debe leer
    }
    _build_connection(trans, {"name": "conn_dwh"}, real=real)
    xml = tostring(trans, encoding="unicode")

    # Pin: known_password_kettle_obfuscated solo es válido para ESTE
    # known_password exacto — si alguien cambia el de arriba sin regenerar
    # el de abajo, el assert de ofuscación de más abajo sigue "pasando" pero
    # deja de probar lo que dice probar (compara contra un string que ya no
    # es la ofuscación real de nada). Este assert lo revienta ruidoso en vez
    # de dejarlo vacuously true.
    assert known_password == "sup3r_s3cr3t_p4ssw0rd!", (
        "known_password cambió sin regenerar known_password_kettle_obfuscated — "
        "recalcular con el algoritmo XOR/seed fijo de Kettle (ver git log de "
        "app/core/kettle_crypto.py, removido de prod pero el algoritmo vive ahí) "
        "antes de tocar este test"
    )
    assert known_password not in xml
    assert known_password_kettle_obfuscated not in xml
    assert base64.b64encode(known_password.encode()).decode() not in xml
    assert "${DWH_DB_PASSWORD}" in xml


# ─── build_ktr integración: conexión real inyectada + warnings ────────────────

def test_build_ktr_injects_real_connection_metadata_password_stays_variable(db):
    conn = _make_connection(db, DbType.postgresql, name="dwh_conn")
    real, resolve_warnings = resolve_real_connections({"conn_dwh": str(conn.id)}, db)
    assert resolve_warnings == []

    ktr_data = {
        "name": "test_proc",
        "description": "",
        "connections": [{"name": "conn_dwh", "type": "GENERIC", "host": "PLACEHOLDER_HOST", "database": "PLACEHOLDER_DATABASE", "port": 0, "username": "PLACEHOLDER_USER"}],
        "steps": [
            {"name": "Leer", "type": "TableInput", "config": {"connection": "conn_dwh", "sql": "SELECT id FROM origen"}},
            {"name": "Escribir", "type": "TableOutput", "config": {"connection": "conn_dwh", "table": "dim_x"}},
        ],
        "hops": [{"from": "Leer", "to": "Escribir", "enabled": True}],
    }

    xml, filename, warnings = build_ktr(ktr_data, "test_proc", real_connections=real)

    assert "<server>dbhost.internal</server>" in xml
    assert "<type>POSTGRESQL</type>" in xml
    assert "<username>myuser</username>" in xml
    assert "<password>${DWH_DB_PASSWORD}</password>" in xml
    assert "DWH_DB_PASSWORD" in xml  # declarado en <parameters>
    assert filename.startswith("test_proc_")
    # avisos siempre presentes: completar password + no compartir el archivo
    assert any("password" in w.lower() for w in warnings)
    assert any("no lo subas" in w.lower() or "no compartas" in w.lower() or "fuera del equipo" in w.lower() for w in warnings)
    # el comentario de seguridad va en el propio .ktr, no solo en la respuesta
    assert "no lo subas a repositorios" in xml.lower()


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
