from __future__ import annotations

from app.core.database import Base
from app.models.base import WorkflowItemMixin


class Etl(WorkflowItemMixin, Base):
    __tablename__ = "etls"
