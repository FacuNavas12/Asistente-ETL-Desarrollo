#services/db_connector.py

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.crypto import decrypt_password
from app.core.sanitize import sanitize_error
from app.models.connection import Connection, DbType
from app.schemas.connection import ColumnInfo, ConnectionTestResult

logger = logging.getLogger(__name__)

# Alias para compatibilidad con tests existentes que importan _sanitize_error.
_sanitize_error = sanitize_error

_TIMEOUT_SECONDS = 5

# Schemas de sistema excluidos en list_tables.
_SYSTEM_SCHEMAS: frozenset[str] = frozenset({
    # PostgreSQL
    "information_schema", "pg_catalog", "pg_toast",
    # SQL Server
    "sys", "INFORMATION_SCHEMA", "guest",
    "db_owner", "db_accessadmin", "db_securityadmin", "db_ddladmin",
    "db_backupoperator", "db_datareader", "db_datawriter",
    "db_denydatareader", "db_denydatawriter",
})


def _connect_args(db_type: DbType) -> dict[str, Any]:
    if db_type == DbType.postgresql:
        return {"connect_timeout": _TIMEOUT_SECONDS}
    return {"timeout": _TIMEOUT_SECONDS}  # pyodbc


def _build_url(conn: Connection) -> str:
    """Construye la URL de conexión SQLAlchemy. Password se descifra aquí."""
    password = decrypt_password(conn.encrypted_password)

    if conn.db_type == DbType.postgresql:
        base = (
            f"postgresql+psycopg://{conn.username}:{password}"
            f"@{conn.host}:{conn.port}/{conn.database}"
        )
        params: dict[str, str] = {}
        if conn.ssl_mode:
            params["sslmode"] = conn.ssl_mode
        if conn.extra_options:
            for key, value in conn.extra_options.items():
                if isinstance(value, str):
                    params[key] = value
                else:
                    logger.warning(
                        "extra_options key '%s' ignorado (valor no-string)", key
                    )
        return base + ("?" + urlencode(params) if params else "")

    else:  # sqlserver
        base = (
            f"mssql+pyodbc://{conn.username}:{password}"
            f"@{conn.host}:{conn.port}/{conn.database}"
        )
        params = {"driver": settings.mssql_odbc_driver}

        # ssl_mode → Encrypt
        if conn.ssl_mode == "disable":
            params["Encrypt"] = "no"
        elif conn.ssl_mode is not None:
            params["Encrypt"] = "yes"

        # extra_options: trust_server_certificate + pares string
        if conn.extra_options:
            tsc = conn.extra_options.get("trust_server_certificate")
            if tsc is not None:
                params["TrustServerCertificate"] = "yes" if tsc else "no"
            for key, value in conn.extra_options.items():
                if key == "trust_server_certificate":
                    continue  # ya gestionado
                if isinstance(value, str):
                    params[key] = value
                else:
                    logger.warning(
                        "extra_options key '%s' ignorado (valor no-string)", key
                    )

        return base + "?" + urlencode(params)


def build_engine(conn: Connection):
    """Construye un SQLAlchemy Engine para la conexión dada."""
    url = _build_url(conn)
    return create_engine(
        url,
        connect_args=_connect_args(conn.db_type),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )


def test_connection(conn: Connection) -> ConnectionTestResult:
    """Intenta conectar y ejecuta SELECT 1. Devuelve resultado saneado."""
    try:
        engine = build_engine(conn)
        with engine.connect() as session:
            session.execute(text("SELECT 1"))
        engine.dispose()
        return ConnectionTestResult(success=True, message="Conexión exitosa.")
    except OperationalError as exc:
        msg = sanitize_error(str(exc))
        logger.warning("Connection test failed [%s]: %s", conn.id, msg)
        return ConnectionTestResult(success=False, message=msg)
    except Exception as exc:
        msg = sanitize_error(str(exc))
        logger.error("Unexpected error testing connection [%s]: %s", conn.id, msg)
        return ConnectionTestResult(success=False, message=f"Error inesperado: {msg}")


def list_tables(conn: Connection) -> list[str]:
    """
    Devuelve 'schema.tabla' para todos los schemas no-sistema.
    Ordenado alfabéticamente.
    """
    engine = build_engine(conn)
    try:
        inspector = inspect(engine)
        schemas = inspector.get_schema_names()
        result: list[str] = []
        for schema in schemas:
            if schema in _SYSTEM_SCHEMAS:
                continue
            for table in inspector.get_table_names(schema=schema):
                result.append(f"{schema}.{table}")
        return sorted(result)
    finally:
        engine.dispose()


def get_columns(conn: Connection, table_name: str) -> list[ColumnInfo]:
    """
    Devuelve columnas de 'schema.tabla' o 'tabla' (schema default).
    Valida table_name contra el inspector antes de usarlo (previene inyección).
    """
    if "." in table_name:
        schema, table = table_name.split(".", 1)
    else:
        schema, table = None, table_name

    engine = build_engine(conn)
    try:
        inspector = inspect(engine)
        valid_tables = inspector.get_table_names(schema=schema)
        if table not in valid_tables:
            raise ValueError(f"Tabla '{table_name}' no encontrada.")

        pk_columns: set[str] = set(
            inspector.get_pk_constraint(table, schema=schema).get(
                "constrained_columns", []
            )
        )
        return [
            ColumnInfo(
                name=col["name"],
                type=str(col["type"]),
                nullable=bool(col.get("nullable", True)),
                primary_key=col["name"] in pk_columns,
                default=str(col["default"]) if col.get("default") is not None else None,
            )
            for col in inspector.get_columns(table, schema=schema)
        ]
    finally:
        engine.dispose()
