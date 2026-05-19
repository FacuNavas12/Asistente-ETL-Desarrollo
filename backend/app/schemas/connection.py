#schemas/connection.py

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.connection import DbType, TestStatus

_SslMode = Optional[Literal["disable", "require", "verify-ca", "verify-full"]]


class ConnectionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    # Variante A: owner_id se acepta en el body del create.
    # TODO (auth): asignarlo desde la sesión autenticada; eliminar del body.
    owner_id: Optional[uuid.UUID] = None


class PostgresConnectionCreate(ConnectionBase):
    db_type: Literal[DbType.postgresql] = DbType.postgresql
    password: str = Field(..., min_length=1)
    ssl_mode: _SslMode = None
    extra_options: Optional[dict] = None


class SqlServerConnectionCreate(ConnectionBase):
    db_type: Literal[DbType.sqlserver] = DbType.sqlserver
    password: str = Field(..., min_length=1)
    extra_options: Optional[dict] = None


# No se usa directamente; el router define _CreateBody con Body(discriminator=...).
# Se conserva como referencia del tipo union para uso externo o documentación.
# ConnectionCreate = Annotated[
#     Union[PostgresConnectionCreate, SqlServerConnectionCreate],
#     Field(discriminator="db_type"),
# ]


class ConnectionUpdate(BaseModel):
    """Todos los campos son opcionales; solo se actualizan los provistos."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    database: Optional[str] = Field(None, min_length=1, max_length=255)
    username: Optional[str] = Field(None, min_length=1, max_length=255)
    password: Optional[str] = Field(None, min_length=1)
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
    owner_id: Optional[uuid.UUID] = None
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
