from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol


class SyncStatus(str, enum.Enum):
    pending = "pending"
    synced = "synced"
    failed = "failed"


@dataclass
class OutboxEntry:
    id: str
    payload: dict[str, Any]
    sync_status: SyncStatus
    attempts: int
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class OutboxPort(Protocol):
    def enqueue(self, entry_id: str, payload: dict[str, Any]) -> None: ...
    def get_pending(self, max_attempts: int) -> list[OutboxEntry]: ...
    def mark_synced(self, entry_id: str) -> None: ...
    def mark_failed(self, entry_id: str, reason: str) -> None: ...
    def increment_attempt(self, entry_id: str, reason: str) -> None: ...
    def get_by_id(self, entry_id: str) -> Optional[OutboxEntry]: ...
    def list_non_synced(self) -> list[OutboxEntry]: ...
