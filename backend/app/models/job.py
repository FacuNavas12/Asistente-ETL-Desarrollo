from __future__ import annotations

from app.core.database import Base
from app.models.base import WorkflowItemMixin


class Job(WorkflowItemMixin, Base):
    __tablename__ = "jobs"
