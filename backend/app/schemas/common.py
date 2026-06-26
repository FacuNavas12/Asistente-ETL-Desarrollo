from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class WorkflowStatus(str, enum.Enum):
    draft = "draft"
    pending = "pending"
    en_proceso = "en_proceso"
    done = "done"
    error = "error"


class CamelModel(BaseModel):
    """Base model: camelCase aliases (in + out), ORM-compatible."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
