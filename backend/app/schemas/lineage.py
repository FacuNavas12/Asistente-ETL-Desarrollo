from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class LineageNode(BaseModel):
    step_name: str
    tipo_step: str
    tabla: Optional[str] = None
    capa: Literal["origen", "staging", "dwh"]


class LineageEdge(BaseModel):
    from_step: str
    to_step: str


class Lineage(BaseModel):
    nodes: list[LineageNode]
    edges: list[LineageEdge]
