#schemas/connection.py

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.connection import DbType, TestStatus

_SslMode = Optional[Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]]


class ConnectionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    # owner_id ya NO se acepta del body — se deriva del claim "sub" del JWT
    # autenticado (ver get_current_owner en app.core.auth), nunca del cliente.


class PostgresConnectionCreate(ConnectionBase):
    db_type: Literal[DbType.postgresql] = DbType.postgresql
    password: str = Field(..., min_length=1)
    # "require" por default — "prefer" permite degradar a sin cifrar en
    # silencio si el servidor no ofrece SSL. Sigue siendo configurable
    # (incluye "disable") para Postgres locales de dev sin TLS, pero ya
    # no como default silencioso.
    ssl_mode: _SslMode = "require"
    extra_options: Optional[dict] = None


class SqlServerConnectionCreate(ConnectionBase):
    db_type: Literal[DbType.sqlserver] = DbType.sqlserver
    password: str = Field(..., min_length=1)
    # Antes no existía este campo — _build_url defaulteaba Encrypt=no
    # incondicionalmente para SQL Server. Mismo criterio que Postgres:
    # cifrado por default, configurable.
    ssl_mode: _SslMode = "require"
    extra_options: Optional[dict] = None


# No se usa directamente; el router define _CreateBody con Body(discriminator=...).
# Se conserva como referencia del tipo union para uso externo o documentación.
# ConnectionCreate = Annotated[
#     Union[PostgresConnectionCreate, SqlServerConnectionCreate],
#     Field(discriminator="db_type"),
# ]


class ConnectionUpdate(BaseModel):
    """Todos los campos son opcionales; solo se actualizan los provistos.
    Sin password — no hay nada persistido que actualizar; se resuelve
    fresco en cada operación que conecta de verdad (test, exploración)."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    database: Optional[str] = Field(None, min_length=1, max_length=255)
    username: Optional[str] = Field(None, min_length=1, max_length=255)
    ssl_mode: _SslMode = None
    extra_options: Optional[dict] = None


class ConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    db_type: DbType
    host: str
    port: int
    database: str
    username: str
    ssl_mode: Optional[str] = None
    extra_options: Optional[dict] = None
    created_at: datetime
    updated_at: datetime
    last_tested_at: Optional[datetime] = None
    last_test_status: Optional[TestStatus] = None

    @computed_field
    @property
    def password(self) -> str:
        return "********"


class ConnectionTestResult(BaseModel):
    success: bool
    message: str


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    primary_key: bool
    default: Optional[str] = None


class TableDataResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    total_count: int          # -1 cuando las estadísticas no están disponibles
    page: int
    page_size: int
    total_pages: int          # -1 cuando total_count == -1
    count_is_estimate: bool
