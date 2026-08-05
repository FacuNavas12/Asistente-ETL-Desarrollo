from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.outbox.port import OutboxEntry, SyncStatus

logger = logging.getLogger(__name__)


class _OutboxBase(DeclarativeBase):
    pass


class _OutboxRow(_OutboxBase):
    __tablename__ = "outbox"

    id = Column(String(36), primary_key=True)
    payload = Column(Text, nullable=False)
    sync_status = Column(String(20), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def _row_to_entry(row: _OutboxRow) -> OutboxEntry:
    return OutboxEntry(
        id=row.id,
        payload=json.loads(row.payload),
        sync_status=SyncStatus(row.sync_status),
        attempts=row.attempts,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqliteOutbox:
    """Durable outbox backed by a local SQLite file (separate from the main app DB)."""

    def __init__(self, db_path: str | Path = "outbox.db") -> None:
        url = f"sqlite:///{db_path}"
        self._engine = create_engine(url, connect_args={"check_same_thread": False})
        _OutboxBase.metadata.create_all(bind=self._engine)
        self._session_factory = sessionmaker(bind=self._engine, autoflush=False, autocommit=False)

    def _session(self) -> Session:
        return self._session_factory()

    def enqueue(self, entry_id: str, payload: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        row = _OutboxRow(
            id=entry_id,
            payload=json.dumps(payload),
            sync_status=SyncStatus.pending.value,
            attempts=0,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        with self._session() as db:
            db.merge(row)  # idempotent: re-enqueue same UUID is a no-op update
            db.commit()
        logger.debug("outbox.enqueue id=%s", entry_id)

    def get_pending(self, max_attempts: int) -> list[OutboxEntry]:
        with self._session() as db:
            rows = (
                db.query(_OutboxRow)
                .filter(
                    _OutboxRow.sync_status == SyncStatus.pending.value,
                    _OutboxRow.attempts < max_attempts,
                )
                .order_by(_OutboxRow.created_at.asc())
                .all()
            )
            return [_row_to_entry(r) for r in rows]

    def mark_synced(self, entry_id: str) -> None:
        self._update(entry_id, {"sync_status": SyncStatus.synced.value})
        logger.info("outbox.synced id=%s", entry_id)

    def mark_failed(self, entry_id: str, reason: str) -> None:
        self._update(entry_id, {"sync_status": SyncStatus.failed.value, "last_error": reason[:2000]})
        logger.warning("outbox.failed id=%s reason=%s", entry_id, reason[:200])

    def increment_attempt(self, entry_id: str, reason: str) -> None:
        with self._session() as db:
            row = db.get(_OutboxRow, entry_id)
            if row:
                row.attempts = (row.attempts or 0) + 1
                row.last_error = reason[:2000]
                row.updated_at = datetime.now(timezone.utc)
                db.commit()
        logger.debug("outbox.attempt id=%s attempts=%s", entry_id, reason[:100])

    def get_by_id(self, entry_id: str) -> Optional[OutboxEntry]:
        with self._session() as db:
            row = db.get(_OutboxRow, entry_id)
            return _row_to_entry(row) if row else None

    def delete(self, entry_id: str) -> None:
        with self._session() as db:
            row = db.get(_OutboxRow, entry_id)
            if row:
                db.delete(row)
                db.commit()
        logger.info("outbox.deleted id=%s", entry_id)

    def list_non_synced(self) -> list[OutboxEntry]:
        with self._session() as db:
            rows = (
                db.query(_OutboxRow)
                .filter(_OutboxRow.sync_status != SyncStatus.synced.value)
                .order_by(_OutboxRow.created_at.desc())
                .all()
            )
            return [_row_to_entry(r) for r in rows]

    def _update(self, entry_id: str, data: dict[str, Any]) -> None:
        with self._session() as db:
            row = db.get(_OutboxRow, entry_id)
            if row:
                for k, v in data.items():
                    setattr(row, k, v)
                row.updated_at = datetime.now(timezone.utc)
                db.commit()
