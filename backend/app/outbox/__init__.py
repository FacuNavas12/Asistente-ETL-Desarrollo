from __future__ import annotations

"""
Outbox package — store-and-forward persistence for ETL cards.

Public surface:
  get_outbox()  — returns the process-singleton SqliteOutbox.
  SyncStatus    — enum: pending | synced | failed.
  OutboxEntry   — dataclass returned by the port.
"""

from pathlib import Path

from app.outbox.port import OutboxEntry, OutboxPort, SyncStatus
from app.outbox.sqlite_outbox import SqliteOutbox

_outbox: SqliteOutbox | None = None


def get_outbox(db_path: str | Path | None = None) -> SqliteOutbox:
    """Return the process-singleton SqliteOutbox, initializing it on first call."""
    global _outbox
    if _outbox is None:
        if db_path is None:
            from app.core.config import settings as _settings
            # Place outbox.db next to app.db (or in CWD for postgres prod).
            base = Path(_settings.database_url.removeprefix("sqlite:///")) if _settings.database_url.startswith("sqlite") else Path(".")
            db_path = base.parent / "outbox.db" if base.suffix == ".db" else Path("outbox.db")
        _outbox = SqliteOutbox(db_path=db_path)
    return _outbox


__all__ = ["get_outbox", "SyncStatus", "OutboxEntry", "OutboxPort", "SqliteOutbox"]
