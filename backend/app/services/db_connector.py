#services/db_connector.py

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote, urlencode

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.sanitize import sanitize_error
from app.models.connection import Connection, DbType
from app.schemas.connection import ColumnInfo, ConnectionTestResult, TableDataResponse
from app.services.dialect import SampleResult, get_dialect

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
    # Supabase (Postgres gestionado — schemas internos de la plataforma, no de usuario)
    "auth", "storage", "realtime", "vault", "extensions",
    "graphql", "graphql_public", "pgbouncer", "pgsodium", "pgsodium_masks",
    "supabase_functions", "supabase_migrations", "cron", "net",
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


def _split_dotted(s: str) -> list[str]:
    """Split on top-level dots, respecting double-quoted segments (dots inside
    a quoted identifier, e.g. "my.table", are literal and not a separator)."""
    parts: list[str] = []
    buf: list[str] = []
    in_quotes = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '"':
            if in_quotes and i + 1 < len(s) and s[i + 1] == '"':
                buf.append('"')
                i += 2
                continue
            in_quotes = not in_quotes
            buf.append(ch)
            i += 1
            continue
        if ch == "." and not in_quotes:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _unquote_identifier(part: str) -> str:
    if len(part) >= 2 and part[0] == '"' and part[-1] == '"':
        return part[1:-1].replace('""', '"')
    return part


def qualify(tname: str, schema: str = "") -> str:
    """
    Builds 'schema.table' from a table name that may or may not already be
    qualified — single source of truth so callers stop gluing schema +
    tname themselves (that's how 'public.public.ventas' happened).

    Contract: if tname already carries a schema prefix, that prefix wins —
    schema_name is a hint, not a second source of truth. Dots inside a
    double-quoted identifier (e.g. "my.table") are literal, not a separator.

    Case note: unquoted Postgres identifiers are catalog-folded to lowercase;
    this function does not fold — callers must pass names as they appear in
    information_schema, or the catalog lookup simply won't match.
    """
    tname = tname.strip()
    schema = (schema or "").strip()

    if "." in tname:
        parts = _split_dotted(tname)
        if len(parts) >= 2:
            embedded_schema = _unquote_identifier(parts[-2])
            table = _unquote_identifier(parts[-1])
            if schema and schema != embedded_schema:
                logger.warning(
                    "qualify(): tname '%s' ya trae schema embebido '%s', "
                    "distinto de schema_name '%s'; se usa el embebido",
                    tname, embedded_schema, schema,
                )
            return f"{embedded_schema}.{table}"
        # single quoted segment with a literal dot inside, e.g. "my.table"
        table = _unquote_identifier(parts[0])
        return f"{schema}.{table}" if schema else table

    tname = _unquote_identifier(tname)
    return f"{schema}.{tname}" if schema else tname


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


def _build_url(conn: Connection, password: str, *, read_only: bool = False) -> str:
    """Construye la URL de conexión SQLAlchemy. password llega por parámetro
    en cada llamada — el backend no lo persiste (ver decisión de diseño)."""
    safe_user = quote(conn.username, safe="")
    safe_pass = quote(password, safe="")

    if conn.db_type == DbType.postgresql:
        base = (
            f"postgresql+psycopg://{safe_user}:{safe_pass}"
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
            f"mssql+pyodbc://{safe_user}:{safe_pass}"
            f"@{conn.host}:{conn.port}/{conn.database}"
        )
        params = {"driver": settings.mssql_odbc_driver}

        # ssl_mode → Encrypt. SqlServerConnectionCreate ya defaultea a "require"
        # (antes no tenía el campo y esto quedaba siempre en "no" — ver hallazgo
        # de seguridad C). "disable" sigue siendo una elección explícita del
        # usuario para SQL Server local sin TLS; None (filas legacy previas a
        # este fix) ahora también cifra por default en vez de asumir "no".
        if conn.ssl_mode == "disable":
            params["Encrypt"] = "no"
        else:
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


def build_engine(conn: Connection, password: str, *, read_only: bool = False):
    """Construye un SQLAlchemy Engine para la conexión dada. password nunca
    viene de un campo persistido — la pasa el caller en cada request."""
    logger.debug(
        "build_engine: db_type=%s host=%s port=%s user=%s db=%s read_only=%s",
        conn.db_type, conn.host, conn.port, conn.username, conn.database, read_only,
    )
    url = _build_url(conn, password, read_only=read_only)
    logger.debug("SQLAlchemy URL (masked): %s", _mask_url(url))
    return create_engine(
        url,
        connect_args=_connect_args(conn.db_type, read_only=read_only),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def test_connection(conn: Connection, password: str) -> ConnectionTestResult:
    """Intenta conectar y ejecuta SELECT 1. Devuelve resultado saneado."""
    try:
        engine = build_engine(conn, password, read_only=True)
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


def list_tables(conn: Connection, password: str) -> list[str]:
    """
    Devuelve 'schema.tabla' para todos los schemas no-sistema.
    Usa information_schema.tables (ANSI SQL, compatible con PG y SQL Server).
    Ordenado alfabéticamente.
    """
    engine = build_engine(conn, password, read_only=True)
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


def get_columns(conn: Connection, table_name: str, password: str) -> list[ColumnInfo]:
    """
    Columnas de 'schema.tabla' (o 'tabla', resolviendo el schema).
    Usa information_schema.columns — NO reflexión — para no tocar catálogos
    internos (pg_collation) que fallan con usuarios restringidos.
    """
    if "." in table_name:
        schema, table = table_name.split(".", 1)
    else:
        schema, table = None, table_name

    engine = build_engine(conn, password, read_only=True)
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



def get_foreign_keys(
    conn: Connection,
    tables: list[str],
    password: str,
) -> dict[str, list]:
    """
    Retrieves FK relationships for the given tables.

    Args:
        tables: list of "schema.table" strings (format returned by list_tables).

    Returns:
        dict keyed by "schema.table" → list[ForeignKeyRef].
        Tables with no FKs map to an empty list.

    Query is scoped to the provided tables only — no full-schema scan.
    Uses information_schema.referential_constraints (ANSI; compatible with PG and SQL Server).
    """
    from app.schemas.canonical import ForeignKeyRef

    result: dict[str, list] = {t: [] for t in tables}
    if not tables:
        return result

    engine = build_engine(conn, password, read_only=True)
    try:
        with engine.connect() as c:
            for qualified_name in tables:
                if "." in qualified_name:
                    schema, table = qualified_name.split(".", 1)
                else:
                    schema = _resolve_schema(c, qualified_name)
                    table  = qualified_name

                rows = c.execute(
                    text("""
                        SELECT
                            tc.constraint_name              AS fk_name,
                            kcu_fk.column_name              AS fk_column,
                            kcu_pk.table_schema             AS ref_schema,
                            kcu_pk.table_name               AS ref_table,
                            kcu_pk.column_name              AS ref_column
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu_fk
                          ON  tc.constraint_name   = kcu_fk.constraint_name
                          AND tc.constraint_schema = kcu_fk.constraint_schema
                        JOIN information_schema.referential_constraints rc
                          ON  tc.constraint_name   = rc.constraint_name
                          AND tc.constraint_schema = rc.constraint_schema
                        JOIN information_schema.key_column_usage kcu_pk
                          ON  rc.unique_constraint_name   = kcu_pk.constraint_name
                          AND rc.unique_constraint_schema = kcu_pk.constraint_schema
                          AND kcu_fk.ordinal_position     = kcu_pk.ordinal_position
                        WHERE tc.constraint_type = 'FOREIGN KEY'
                          AND tc.table_schema    = :schema
                          AND tc.table_name      = :table
                        ORDER BY tc.constraint_name, kcu_fk.ordinal_position
                    """),
                    {"schema": schema, "table": table},
                ).fetchall()

                # Group rows by constraint_name (a composite FK spans multiple rows).
                fk_groups: dict[str, dict] = {}
                for row in rows:
                    fk_name, fk_col, ref_schema, ref_table, ref_col = (
                        row[0], row[1], row[2], row[3], row[4]
                    )
                    if fk_name not in fk_groups:
                        fk_groups[fk_name] = {
                            "fields":         [],
                            "reference_resource": f"{ref_schema}.{ref_table}",
                            "reference_fields": [],
                        }
                    fk_groups[fk_name]["fields"].append(fk_col)
                    fk_groups[fk_name]["reference_fields"].append(ref_col)

                result[qualified_name] = [
                    ForeignKeyRef(
                        fields=g["fields"],
                        reference_resource=g["reference_resource"],
                        reference_fields=g["reference_fields"],
                    )
                    for g in fk_groups.values()
                ]
    finally:
        engine.dispose()

    return result


def get_sample_rows(
    conn: Connection,
    schema: str,
    table: str,
    password: str,
    limit: int = 20,
) -> SampleResult:
    """
    Returns a SampleResult(col_names, rows, bias) with a random sample of ≤limit rows.

    Uses the dialect's primary_sample strategy (TABLESAMPLE-based) for speed on large
    tables, then falls back to fallback_sample when primary returns nothing (small tables).
    SampleResult.bias declares the sampling granularity so callers can log it.

    Raw rows are returned to the profiler only. They must not leave the backend.
    """
    dialect   = get_dialect(conn.db_type)
    engine    = build_engine(conn, password, read_only=True)
    qualified = f"{_quote_identifier(schema, conn.db_type)}.{_quote_identifier(table, conn.db_type)}"

    primary  = dialect.primary_sample(qualified, limit)
    fallback = dialect.fallback_sample(qualified, limit)

    try:
        with engine.connect() as c:
            _validate_table_exists(c, schema, table)

            result  = c.execute(text(primary.sql))
            columns = list(result.keys())
            rows    = [_serialize_row(r) for r in result.fetchall()]
            bias    = primary.bias

            if not rows:
                result  = c.execute(text(fallback.sql))
                columns = list(result.keys())
                rows    = [_serialize_row(r) for r in result.fetchall()]
                bias    = fallback.bias

        return SampleResult(col_names=columns, rows=rows, bias=bias)
    finally:
        engine.dispose()


def get_table_data(
    conn: Connection,
    schema: str,
    table: str,
    page: int,
    page_size: int,
    password: str,
    exact_count: bool = False,
) -> TableDataResponse:
    """
    Devuelve filas de una tabla con paginación obligatoria.
    - Valida schema+table contra information_schema (parámetros, nunca identificadores).
    - Cita los identificadores con escape de comilla interior (defensa en profundidad).
    - Conteo estimado por defecto; exacto solo si exact_count=True.
    """
    offset = (page - 1) * page_size
    engine = build_engine(conn, password, read_only=True)
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
