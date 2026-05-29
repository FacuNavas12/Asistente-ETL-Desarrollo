#services/db_connector.py

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.crypto import decrypt_password
from app.core.sanitize import sanitize_error
from app.models.connection import Connection, DbType
from app.schemas.connection import ColumnInfo, ConnectionTestResult, TableDataResponse

logger = logging.getLogger(__name__)


def _mask_url(url: str) -> str:
    """Reemplaza la contraseña en una URL SQLAlchemy por *** para logs."""
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***\2", url)


# Alias para compatibilidad con tests existentes que importan _sanitize_error.
_sanitize_error = sanitize_error

_TIMEOUT_SECONDS = 5

# Schemas de sistema excluidos en list_tables (PostgreSQL y SQL Server).
_SYSTEM_SCHEMAS: frozenset[str] = frozenset({
    # PostgreSQL
    "information_schema", "pg_catalog", "pg_toast",
    # SQL Server
    "sys", "INFORMATION_SCHEMA", "guest",
    "db_owner", "db_accessadmin", "db_securityadmin", "db_ddladmin",
    "db_backupoperator", "db_datareader", "db_datawriter",
    "db_denydatareader", "db_denydatawriter",
})


# ─── Quoting helpers ──────────────────────────────────────────────────────────

def _quote_pg(identifier: str) -> str:
    """PostgreSQL double-quoted identifier. Inner double-quotes doubled per SQL standard."""
    return '"' + identifier.replace('"', '""') + '"'


def _quote_mssql(identifier: str) -> str:
    """SQL Server bracket-quoted identifier. Inner closing brackets doubled."""
    return '[' + identifier.replace(']', ']]') + ']'


def _quote_identifier(identifier: str, db_type: DbType) -> str:
    return _quote_pg(identifier) if db_type == DbType.postgresql else _quote_mssql(identifier)


# ─── Row serialization ────────────────────────────────────────────────────────

def _serialize_row(row) -> list:
    """Converts a SQLAlchemy row to a JSON-serializable list."""
    return [
        v if isinstance(v, (int, float, bool, str, type(None))) else str(v)
        for v in row
    ]


# ─── Catalog validation ───────────────────────────────────────────────────────

def _validate_table_exists(session, schema: str, table: str) -> None:
    """
    Raises ValueError if schema+table not found in information_schema.tables.
    Fully parameterized — schema and table are values, never SQL identifiers.
    """
    row = session.execute(
        text("""
            SELECT 1
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema = :schema
              AND table_name   = :table
        """),
        {"schema": schema, "table": table},
    ).fetchone()
    if row is None:
        raise ValueError(f"Tabla '{schema}.{table}' no encontrada en el catálogo.")


# ─── Estimated count ──────────────────────────────────────────────────────────

def _estimated_count(session, schema: str, table: str, db_type: DbType) -> int:
    """
    Returns estimated row count without a full table scan.
    PG: pg_class.reltuples (updated by ANALYZE).
    SQL Server: sys.partitions (updated by auto-stats).
    Returns -1 if statistics are not yet available or inaccessible.
    """
    try:
        if db_type == DbType.postgresql:
            row = session.execute(
                text("""
                    SELECT reltuples::bigint
                    FROM pg_class
                    WHERE relname = :table
                      AND relnamespace = (
                          SELECT oid FROM pg_namespace WHERE nspname = :schema
                      )
                """),
                {"schema": schema, "table": table},
            ).fetchone()
            return int(row[0]) if row and row[0] is not None and row[0] >= 0 else -1

        else:  # sqlserver
            # OBJECT_ID receives a plain string value — safe to parameterize.
            row = session.execute(
                text("""
                    SELECT SUM(rows)
                    FROM sys.partitions
                    WHERE object_id = OBJECT_ID(:qualified)
                      AND index_id IN (0, 1)
                """),
                {"qualified": f"{schema}.{table}"},
            ).fetchone()
            return int(row[0]) if row and row[0] is not None else -1

    except Exception:
        return -1


# ─── Connection helpers ───────────────────────────────────────────────────────

def _connect_args(db_type: DbType, *, read_only: bool = False) -> dict[str, Any]:
    if db_type == DbType.postgresql:
        args: dict[str, Any] = {"connect_timeout": _TIMEOUT_SECONDS}
        if read_only:
            # Prevents accidental writes at the transaction level.
            args["options"] = "-c default_transaction_read_only=on"
        return args
    return {"timeout": _TIMEOUT_SECONDS}  # pyodbc


def _build_url(conn: Connection, *, read_only: bool = False) -> str:
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

        # ApplicationIntent=ReadOnly enruta a réplica en AG/Azure SQL.
        # En SQL Server standalone es un no-op; la garantía de solo-lectura
        # la dan los permisos del usuario (rol db_datareader), no este parámetro.
        if read_only:
            params["ApplicationIntent"] = "ReadOnly"

        return base + "?" + urlencode(params)


def build_engine(conn: Connection, *, read_only: bool = False):
    """Construye un SQLAlchemy Engine para la conexión dada."""
    logger.debug(
        "build_engine: db_type=%s host=%s port=%s user=%s db=%s read_only=%s",
        conn.db_type, conn.host, conn.port, conn.username, conn.database, read_only,
    )
    url = _build_url(conn, read_only=read_only)
    logger.debug("SQLAlchemy URL (masked): %s", _mask_url(url))
    return create_engine(
        url,
        connect_args=_connect_args(conn.db_type, read_only=read_only),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def test_connection(conn: Connection) -> ConnectionTestResult:
    """Intenta conectar y ejecuta SELECT 1. Devuelve resultado saneado."""
    try:
        engine = build_engine(conn, read_only=True)
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
    Usa information_schema.tables (ANSI SQL, compatible con PG y SQL Server).
    Ordenado alfabéticamente.
    """
    engine = build_engine(conn, read_only=True)
    try:
        with engine.connect() as c:
            rows = c.execute(
                text("""
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_type = 'BASE TABLE'
                    ORDER BY table_schema, table_name
                """)
            ).fetchall()
        return [
            f"{row[0]}.{row[1]}"
            for row in rows
            if row[0] not in _SYSTEM_SCHEMAS
        ]
    finally:
        engine.dispose()


def _resolve_schema(session, table: str) -> str:
    """Si llega 'tabla' sin schema, resuelve a qué schema no-sistema pertenece."""
    rows = session.execute(
        text("""
            SELECT table_schema FROM information_schema.tables
            WHERE table_type = 'BASE TABLE' AND table_name = :table
        """),
        {"table": table},
    ).fetchall()
    candidates = [s for (s,) in rows if s not in _SYSTEM_SCHEMAS]
    if not candidates:
        raise ValueError(f"Tabla '{table}' no encontrada.")
    if len(candidates) > 1:
        raise ValueError(f"Tabla '{table}' existe en varios schemas {candidates}; usá 'schema.tabla'.")
    return candidates[0]


def _primary_key_columns(session, schema: str, table: str) -> set[str]:
    """PK vía information_schema (ANSI, PG + SQL Server). Best-effort: set vacío si falla."""
    try:
        rows = session.execute(
            text("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON  tc.constraint_name   = kcu.constraint_name
                  AND tc.constraint_schema = kcu.constraint_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = :schema
                  AND tc.table_name   = :table
            """),
            {"schema": schema, "table": table},
        ).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _format_type(r) -> str:
    """Tipo legible desde information_schema.columns (incluye longitud/precisión)."""
    t = r.data_type
    if r.character_maximum_length:
        return f"{t}({r.character_maximum_length})"
    if t in ("numeric", "decimal") and r.numeric_precision is not None:
        return f"{t}({r.numeric_precision},{r.numeric_scale})"
    return t


def get_columns(conn: Connection, table_name: str) -> list[ColumnInfo]:
    """
    Columnas de 'schema.tabla' (o 'tabla', resolviendo el schema).
    Usa information_schema.columns — NO reflexión — para no tocar catálogos
    internos (pg_collation) que fallan con usuarios restringidos.
    """
    if "." in table_name:
        schema, table = table_name.split(".", 1)
    else:
        schema, table = None, table_name

    engine = build_engine(conn, read_only=True)
    try:
        with engine.connect() as c:
            if schema is None:
                schema = _resolve_schema(c, table)
            _validate_table_exists(c, schema, table)
            pk_cols = _primary_key_columns(c, schema, table)

            rows = c.execute(
                text("""
                    SELECT column_name, data_type, is_nullable, column_default,
                           character_maximum_length, numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_schema = :schema AND table_name = :table
                    ORDER BY ordinal_position
                """),
                {"schema": schema, "table": table},
            ).fetchall()

        return [
            ColumnInfo(
                name=r.column_name,
                type=_format_type(r),
                nullable=(r.is_nullable == "YES"),
                primary_key=r.column_name in pk_cols,
                default=r.column_default,
            )
            for r in rows
        ]
    finally:
        engine.dispose()



def get_table_data(
    conn: Connection,
    schema: str,
    table: str,
    page: int,
    page_size: int,
    exact_count: bool = False,
) -> TableDataResponse:
    """
    Devuelve filas de una tabla con paginación obligatoria.
    - Valida schema+table contra information_schema (parámetros, nunca identificadores).
    - Cita los identificadores con escape de comilla interior (defensa en profundidad).
    - Conteo estimado por defecto; exacto solo si exact_count=True.
    """
    offset = (page - 1) * page_size
    engine = build_engine(conn, read_only=True)
    try:
        with engine.connect() as c:
            _validate_table_exists(c, schema, table)

            q_schema = _quote_identifier(schema, conn.db_type)
            q_table  = _quote_identifier(table, conn.db_type)
            qualified = f"{q_schema}.{q_table}"

            if exact_count:
                total = int(c.execute(text(f"SELECT COUNT(*) FROM {qualified}")).scalar() or 0)
                is_estimate = False
            else:
                total = _estimated_count(c, schema, table, conn.db_type)
                is_estimate = True

            if conn.db_type == DbType.postgresql:
                sql = text(f"SELECT * FROM {qualified} LIMIT :lim OFFSET :off")
            else:
                sql = text(
                    f"SELECT * FROM {qualified}"
                    f" ORDER BY (SELECT NULL)"
                    f" OFFSET :off ROWS FETCH NEXT :lim ROWS ONLY"
                )

            result  = c.execute(sql, {"lim": page_size, "off": offset})
            columns = list(result.keys())
            rows    = [_serialize_row(row) for row in result.fetchall()]

        total_pages = max(1, -(total // -page_size)) if total > 0 else -1
        return TableDataResponse(
            columns=columns,
            rows=rows,
            total_count=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            count_is_estimate=is_estimate,
        )
    finally:
        engine.dispose()
