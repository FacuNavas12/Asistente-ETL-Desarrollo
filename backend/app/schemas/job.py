from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.schemas.common import CamelModel, WorkflowStatus


class JobCreate(CamelModel):
    name: str
    form_data: Optional[Any] = None
    result: Optional[Any] = None
    status: WorkflowStatus = WorkflowStatus.draft


class JobUpdate(CamelModel):
    name: Optional[str] = None
    status: Optional[WorkflowStatus] = None
    form_data: Optional[Any] = None
    result: Optional[Any] = None


class JobStatusUpdate(CamelModel):
    status: WorkflowStatus


class JobRead(CamelModel):
    id: str
    name: str
    status: WorkflowStatus
    form_data: Optional[Any] = None
    result: Optional[Any] = None
    created_at: datetime
    updated_at: datetime
