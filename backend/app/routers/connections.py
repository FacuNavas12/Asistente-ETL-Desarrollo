#routers/connections.py

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_password
from app.core.database import get_db
from app.core.sanitize import sanitize_error
from app.models.connection import Connection, TestStatus
from app.schemas.connection import (
    ColumnInfo,
    ConnectionRead,
    ConnectionTestResult,
    ConnectionUpdate,
    PostgresConnectionCreate,
    SqlServerConnectionCreate,
)
from app.services.db_connector import (
    get_columns,
    list_tables,
    test_connection as svc_test,
)

router = APIRouter(prefix="/api/connections", tags=["connections"])
logger = logging.getLogger(__name__)

# Tipo discriminado para el body de creación.
_CreateBody = Annotated[
    Union[PostgresConnectionCreate, SqlServerConnectionCreate],
    Body(discriminator="db_type"),
]


def _get_or_404(conn_id: uuid.UUID, db: Session) -> Connection:
    conn = db.get(Connection, conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexión no encontrada.")
    return conn


# ─── CRUD ─────────────────────────────────────────────────────────────────────

# TODO (auth): owner_id se asignará desde la sesión autenticada — por ahora
#              se acepta del body como campo opcional (Variante A).
@router.post("", response_model=ConnectionRead, status_code=201)
def create_connection(body: _CreateBody, db: Session = Depends(get_db)):
    try:
        conn = Connection(
            name=body.name,
            db_type=body.db_type,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            encrypted_password=encrypt_password(body.password),
            ssl_mode=getattr(body, "ssl_mode", None),
            extra_options=body.extra_options,
            owner_id=body.owner_id,
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
    owner_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Connection)
    if owner_id:
        q = q.filter(Connection.owner_id == owner_id)
    return q.all()


@router.get("/{conn_id}", response_model=ConnectionRead)
def get_connection(conn_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_or_404(conn_id, db)


@router.put("/{conn_id}", response_model=ConnectionRead)
def update_connection(
    conn_id: uuid.UUID,
    body: ConnectionUpdate,
    db: Session = Depends(get_db),
):
    conn = _get_or_404(conn_id, db)
    try:
        update_data = body.model_dump(exclude_unset=True)
        # Extraemos password antes de iterar para no llamar encrypt_password(None).
        new_password = update_data.pop("password", None)
        if new_password is not None:
            conn.encrypted_password = encrypt_password(new_password)
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
def delete_connection(conn_id: uuid.UUID, db: Session = Depends(get_db)):
    conn = _get_or_404(conn_id, db)
    db.delete(conn)
    db.commit()


# ─── TEST ─────────────────────────────────────────────────────────────────────

@router.post("/{conn_id}/test", response_model=ConnectionTestResult)
def test_connection(conn_id: uuid.UUID, db: Session = Depends(get_db)):
    conn = _get_or_404(conn_id, db)
    result = svc_test(conn)
    try:
        conn.last_test_status = TestStatus.success if result.success else TestStatus.failed
        conn.last_tested_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
    return result


# ─── SCHEMA EXPLORER ──────────────────────────────────────────────────────────

@router.get("/{conn_id}/schema/tables", response_model=list[str])
def schema_list_tables(conn_id: uuid.UUID, db: Session = Depends(get_db)):
    """Devuelve 'schema.tabla' para todas las tablas no-sistema."""
    conn = _get_or_404(conn_id, db)
    try:
        return list_tables(conn)
    except Exception as exc:
        logger.error("Error listing tables for connection %s: %s", conn_id, exc)
        raise HTTPException(
            status_code=502, detail="No se pudo obtener el esquema de la base de datos."
        )


@router.get(
    "/{conn_id}/schema/tables/{table_name}/columns",
    response_model=list[ColumnInfo],
)
def schema_get_columns(
    conn_id: uuid.UUID,
    table_name: str,
    db: Session = Depends(get_db),
):
    """Devuelve columnas de una tabla. Acepta formato 'schema.tabla' o 'tabla'."""
    conn = _get_or_404(conn_id, db)
    try:
        return get_columns(conn, table_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(
            "Error getting columns for %s/%s: %s", conn_id, table_name, exc
        )
        raise HTTPException(
            status_code=502, detail="No se pudo obtener las columnas de la tabla."
        )
