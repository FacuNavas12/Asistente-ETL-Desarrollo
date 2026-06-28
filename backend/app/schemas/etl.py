from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.outbox.port import SyncStatus
from app.schemas.common import CamelModel, WorkflowStatus


class EtlCreate(CamelModel):
    name: str
    form_data: Optional[Any] = None
    result: Optional[Any] = None
    status: WorkflowStatus = WorkflowStatus.draft


class EtlUpdate(CamelModel):
    name: Optional[str] = None
    status: Optional[WorkflowStatus] = None
    form_data: Optional[Any] = None
    result: Optional[Any] = None


class EtlStatusUpdate(CamelModel):
    status: WorkflowStatus


class EtlRead(CamelModel):
    id: str
    name: str
    status: WorkflowStatus
    # Persistence state — independent of generation status.
    # pending: accepted, not yet written to Supabase.
    # synced:  confirmed in Supabase.
    # failed:  permanent error or dead-letter after max retries.
    sync_status: SyncStatus = SyncStatus.pending
    form_data: Optional[Any] = None
    result: Optional[Any] = None
    created_at: datetime
    updated_at: datetime
