from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import DataError, IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.outbox.port import OutboxEntry, OutboxPort, SyncStatus

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# PostgreSQL error codes that are unambiguously transient.
# https://www.postgresql.org/docs/current/errcodes-appendix.html
_TRANSIENT_PG_CODES: frozenset[str] = frozenset(
    {
        "08000",  # connection_exception
        "08003",  # connection_does_not_exist
        "08006",  # connection_failure
        "08001",  # sqlclient_unable_to_establish_sqlconnection
        "08004",  # sqlserver_rejected_establishment_of_sqlconnection
        "40001",  # serialization_failure (deadlock)
        "53300",  # too_many_connections
        "57P03",  # cannot_connect_now (recovery mode)
    }
)


def _is_transient(exc: Exception) -> bool:
    """Return True when the error is likely transient (retry-able)."""
    if isinstance(exc, OperationalError):
        # OperationalError covers: connection refused, timeout, pool exhausted,
        # server gone. Always transient.
        return True

    if isinstance(exc, (IntegrityError, DataError, ProgrammingError)):
        # Constraint violation, bad data, bad SQL — permanent regardless of pgcode.
        return False

    # Generic DatabaseError: inspect pgcode if available.
    pgcode: str | None = getattr(getattr(exc, "orig", None), "pgcode", None)
    if pgcode:
        return pgcode in _TRANSIENT_PG_CODES

    # Unknown — conservative: treat as transient to avoid data loss.
    return True


_DATETIME_FIELDS = frozenset({"created_at", "updated_at"})


def _coerce_payload(payload: dict) -> dict:
    """Convert ISO string datetimes back to datetime objects for the ORM."""
    result = {}
    for k, v in payload.items():
        if k in _DATETIME_FIELDS and isinstance(v, str):
            result[k] = datetime.fromisoformat(v)
        else:
            result[k] = v
    return result


def _upsert_to_supabase(db: Session, entry: OutboxEntry) -> None:
    """Write one outbox entry to Supabase (main DB) via SQLAlchemy upsert."""
    from app.models.etl import Etl

    payload = _coerce_payload(entry.payload)
    # sync_status is an outbox concern — not a column in the Supabase table.
    payload.pop("sync_status", None)

    existing = db.get(Etl, entry.id)
    if existing:
        for k, v in payload.items():
            if hasattr(existing, k):
                setattr(existing, k, v)
    else:
        obj = Etl(**{k: v for k, v in payload.items() if hasattr(Etl, k)})
        db.add(obj)
    db.commit()


async def drain(
    outbox: OutboxPort,
    session_factory: Callable[[], Session],
    max_attempts: int = 5,
) -> int:
    """
    Drain pending outbox entries to Supabase.

    Pure function — knows nothing about who calls it or how often.
    Returns the number of entries processed (success + failure, not skipped).
    """
    pending = outbox.get_pending(max_attempts=max_attempts)
    processed = 0

    for entry in pending:
        try:
            db = session_factory()
            try:
                _upsert_to_supabase(db, entry)
            finally:
                db.close()
            outbox.mark_synced(entry.id)
            processed += 1
        except Exception as exc:
            processed += 1
            reason = f"{type(exc).__name__}: {exc}"
            if _is_transient(exc):
                outbox.increment_attempt(entry.id, reason)
                logger.warning("outbox.transient id=%s attempt=%d: %s", entry.id, entry.attempts + 1, reason)
            else:
                outbox.mark_failed(entry.id, reason)
                logger.error("outbox.permanent id=%s: %s", entry.id, reason)

    return processed
