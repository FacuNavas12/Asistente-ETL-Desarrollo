#routers/connections.py

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional, Union

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_owner, require_auth
from app.core.database import get_db
from app.core.sanitize import sanitize_error
from app.models.connection import Connection, TestStatus
from app.schemas.canonical import CanonicalField, CanonicalSchema, TableProfile
from app.schemas.connection import (
    ConnectionRead,
    ConnectionTestResult,
    ConnectionUpdate,
    PostgresConnectionCreate,
    SqlServerConnectionCreate,
    TableDataResponse,
)
from app.services.adapters import db_adapter
from app.services.db_connector import (
    get_columns,
    get_foreign_keys,
    get_sample_rows,
    get_table_data,
    list_tables,
    test_connection as svc_test,
)
from app.services import profiler as profiler_svc
from app.services import context_builder

router = APIRouter(prefix="/api/connections", tags=["connections"])
logger = logging.getLogger(__name__)

# Tipo discriminado para el body de creación.
_CreateBody = Annotated[
    Union[PostgresConnectionCreate, SqlServerConnectionCreate],
    Body(discriminator="db_type"),
]

# Password de la conexión: nunca se persiste (ver decisión de diseño de
# no-custodia de credenciales) — viaja por header, no por query string
# (evita que termine en logs de acceso), en cada request que realmente
# necesita abrir una conexión (test, exploración de esquema).
_DbPassword = Annotated[
    str,
    Header(alias="X-DB-Password", min_length=1),
]


def _get_owned_or_404(conn_id: uuid.UUID, owner: Optional[str], db: Session) -> Connection:
    """
    Busca la conexión y, si hay ownership activo (owner is not None, es decir
    AUTH_REQUIRED=true), exige que pertenezca al caller. "No existe" y "existe
    pero es de otro" devuelven el mismo 404 — no confirmamos a quien adivina
    un UUID ajeno que el recurso existe.

    owner is None (AUTH_REQUIRED=false, modo desarrollo) salta el filtro,
    igual que require_auth ya salta la validación de token en ese modo.
    """
    conn = db.get(Connection, conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexión no encontrada.")
    if owner is not None and conn.owner_id != owner:
        raise HTTPException(status_code=404, detail="Conexión no encontrada.")
    return conn


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=ConnectionRead, status_code=201)
def create_connection(
    body: _CreateBody,
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    try:
        # body.password se valida (min_length) pero nunca se persiste — el
        # backend ya no custodia contraseñas de conexión.
        conn = Connection(
            name=body.name,
            db_type=body.db_type,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            ssl_mode=getattr(body, "ssl_mode", None),
            extra_options=body.extra_options,
            owner_id=get_current_owner(payload),
        )
        db.add(conn)
        db.commit()
        db.refresh(conn)
        return conn
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe una conexión con ese nombre para este usuario.",
        )
    except Exception as exc:
        db.rollback()
        logger.error("Error creating connection: %s", sanitize_error(str(exc)))
        raise HTTPException(status_code=500, detail="Error al crear la conexión.")


@router.get("", response_model=list[ConnectionRead])
def list_connections(
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    owner = get_current_owner(payload)
    q = db.query(Connection)
    if owner is not None:
        q = q.filter(Connection.owner_id == owner)
    return q.all()


@router.get("/{conn_id}", response_model=ConnectionRead)
def get_connection(
    conn_id: uuid.UUID,
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    return _get_owned_or_404(conn_id, get_current_owner(payload), db)


@router.put("/{conn_id}", response_model=ConnectionRead)
def update_connection(
    conn_id: uuid.UUID,
    body: ConnectionUpdate,
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    conn = _get_owned_or_404(conn_id, get_current_owner(payload), db)
    try:
        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(conn, field, value)
        db.commit()
        db.refresh(conn)
        return conn
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe una conexión con ese nombre para este usuario.",
        )
    except Exception as exc:
        db.rollback()
        logger.error("Error updating connection %s: %s", conn_id, sanitize_error(str(exc)))
        raise HTTPException(status_code=500, detail="Error al actualizar la conexión.")


@router.delete("/{conn_id}", status_code=204)
def delete_connection(
    conn_id: uuid.UUID,
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    conn = _get_owned_or_404(conn_id, get_current_owner(payload), db)
    db.delete(conn)
    db.commit()


# ─── TEST ─────────────────────────────────────────────────────────────────────

@router.post("/{conn_id}/test", response_model=ConnectionTestResult)
def test_connection(
    conn_id: uuid.UUID,
    password: _DbPassword,
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    conn = _get_owned_or_404(conn_id, get_current_owner(payload), db)
    result = svc_test(conn, password)
    try:
        conn.last_test_status = TestStatus.success if result.success else TestStatus.failed
        conn.last_tested_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
    return result


# ─── SCHEMA EXPLORER ──────────────────────────────────────────────────────────

@router.get("/{conn_id}/schema/tables", response_model=list[str])
def schema_list_tables(
    conn_id: uuid.UUID,
    password: _DbPassword,
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    """Devuelve 'schema.tabla' para todas las tablas no-sistema."""
    conn = _get_owned_or_404(conn_id, get_current_owner(payload), db)
    try:
        return list_tables(conn, password)
    except Exception as exc:
        logger.error("Error listing tables for connection %s: %s", conn_id, exc)
        raise HTTPException(
            status_code=502, detail="No se pudo obtener el esquema de la base de datos."
        )


@router.get(
    "/{conn_id}/schema/tables/{table_name}/columns",
    response_model=list[CanonicalField],
)
def schema_get_columns(
    conn_id: uuid.UUID,
    table_name: str,
    password: _DbPassword,
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    """
    Devuelve las columnas de una tabla como CanonicalField[].
    Acepta formato 'schema.tabla' o 'tabla'.
    No incluye perfil estadístico — usar /profile para eso.
    """
    conn = _get_owned_or_404(conn_id, get_current_owner(payload), db)
    try:
        col_infos = get_columns(conn, table_name, password)
        schema = db_adapter.build(col_infos, table_name)
        return schema.fields
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(
            "Error getting columns for %s/%s: %s", conn_id, table_name, exc
        )
        raise HTTPException(
            status_code=502, detail="No se pudo obtener las columnas de la tabla."
        )


@router.get(
    "/{conn_id}/schema/tables/{table_name}/profile",
    response_model=CanonicalSchema,
)
def schema_profile_table(
    conn_id: uuid.UUID,
    table_name: str,
    password: _DbPassword,
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    """
    Returns a CanonicalSchema for the requested table.

    Structural layer: column types, nullable, PK and FK relationships
    from INFORMATION_SCHEMA (authoritative, no row access).

    Statistical layer: null_pct, distinct_count, format_hint, masked examples
    from a single SQL aggregate pass + ≤20 random sample rows (no raw values
    leave the backend — all embedded in schema.profile.column_profiles).
    """
    conn = _get_owned_or_404(conn_id, get_current_owner(payload), db)

    if "." in table_name:
        schema, _, table = table_name.partition(".")
    else:
        schema, table = "", table_name

    try:
        col_infos = get_columns(conn, table_name, password)

        # Resolve schema for profiler calls (needs schema and table separately).
        from app.services.db_connector import build_engine, _resolve_schema
        engine = build_engine(conn, password, read_only=True)
        try:
            with engine.connect() as c:
                if not schema or schema == table:
                    schema = _resolve_schema(c, table)
        finally:
            engine.dispose()

        qualified = f"{schema}.{table}"

        fk_map  = get_foreign_keys(conn, [qualified], password)
        fk_refs = fk_map.get(qualified, [])

        col_names     = [c.name for c in col_infos]
        stats         = profiler_svc.fetch_db_column_stats(conn, schema, table, col_names, password)
        sample_result = get_sample_rows(conn, schema, table, password, limit=20)
        logger.debug("sample bias for %s: %s", qualified, sample_result.bias)
        profiles = profiler_svc.profile_columns(col_names, stats, sample_result.rows)

        return db_adapter.build(
            col_infos,
            qualified,
            fk_refs=fk_refs,
            profile=TableProfile(column_profiles=profiles),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Error profiling %s/%s: %s", conn_id, table_name, exc)
        raise HTTPException(
            status_code=502, detail="No se pudo perfilar la tabla."
        )


@router.get("/{conn_id}/schema/table-data", response_model=TableDataResponse)
def schema_get_table_data(
    conn_id: uuid.UUID,
    password: _DbPassword,
    schema: str = Query(..., min_length=1),
    table: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    exact_count: bool = Query(False),
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    """
    Devuelve filas paginadas de una tabla.
    schema y table se pasan por separado y se validan contra information_schema.
    Paginación obligatoria: máximo 500 filas por request.
    """
    conn = _get_owned_or_404(conn_id, get_current_owner(payload), db)
    try:
        return get_table_data(conn, schema, table, page, page_size, password, exact_count)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(
            "Error fetching data for %s/%s.%s: %s",
            conn_id, schema, table, sanitize_error(str(exc)),
        )
        raise HTTPException(
            status_code=502, detail="No se pudo obtener los datos de la tabla."
        )
