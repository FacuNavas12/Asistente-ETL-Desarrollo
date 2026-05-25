from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class KTRMetadata(BaseModel):
    filename: str
    transformation_name: str
    description: str
    step_types: List[str]
    input_connections: List[str]
    output_connections: List[str]
    has_staging: bool
    has_dwh: bool
    raw_content: str


class JobVariable(BaseModel):
    name: str
    value: str
    scope: str
    description: str


class JobCheckpoint(BaseModel):
    after_transformation: str
    type: str
    description: str


class JobNotification(BaseModel):
    trigger: str
    type: str
    message: str


class JobLoop(BaseModel):
    transformation_name: str
    condition: str
    max_iterations: int = 10


class JobEntry(BaseModel):
    order: int
    transformation_name: str
    filename: str
    rationale: str


class JobPlan(BaseModel):
    job_name: str
    description: str
    execution_order: List[JobEntry]
    variables: List[JobVariable] = []
    checkpoints: List[JobCheckpoint] = []
    notifications: List[JobNotification] = []
    loops: List[JobLoop] = []
    error_handling: str = ""
    overall_rationale: str


class JobAnalyzeResponse(BaseModel):
    job_plan: JobPlan
    iteration: int = 1
    warnings: List[str] = []
    session_id: str


class JobRefineRequest(BaseModel):
    session_id: str
    job_description: str
    business_rules: Optional[str] = None
    current_job_plan: JobPlan
    correction: str
    history: List[Dict[str, Any]] = []


class JobGenerateRequest(BaseModel):
    session_id: str
    job_plan: JobPlan


class JobGenerateResponse(BaseModel):
    job_plan: JobPlan
    kjb_xml: str
    kjb_filename: str
    explanation: str
