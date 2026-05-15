from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Integer,
    JSON,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DbType(str, enum.Enum):
    postgresql = "postgresql"
    sqlserver = "sqlserver"


class TestStatus(str, enum.Enum):
    success = "success"
    failed = "failed"
    never = "never"


class Connection(Base):
    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_connections_owner_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255))
    db_type: Mapped[DbType] = mapped_column(SAEnum(DbType, name="db_type_enum"))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    database: Mapped[str] = mapped_column(String(255))
    username: Mapped[str] = mapped_column(String(255))
    encrypted_password: Mapped[bytes] = mapped_column(LargeBinary)
    ssl_mode: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    extra_options: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_test_status: Mapped[Optional[TestStatus]] = mapped_column(
        SAEnum(TestStatus, name="test_status_enum"), nullable=True
    )
