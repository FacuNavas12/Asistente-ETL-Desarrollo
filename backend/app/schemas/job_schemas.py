from typing import Any, Dict, List, Literal, Optional
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
    # Nombre a mostrar en el canvas del .kjb — a pesar del nombre del campo
    # (histórico, previo a F2.5/H7), vale para ambos entry_type: es el
    # nombre de la transformación O del job hijo que esta entry invoca.
    transformation_name: str
    # Archivo que la entry ejecuta: un .ktr (entry_type="trans") o un .kjb
    # (entry_type="job", ver H7 en 01-hallazgos.md/kettle-jobentryjob-xml-spec.md).
    filename: str
    rationale: str
    # "trans" (default, comportamiento histórico) = JobEntryTrans, invoca un
    # .ktr. "job" = JobEntryJob, invoca otro .kjb — necesario para la
    # jerarquía de 3 niveles (job_master -> job_origen_stg/job_stg_dwh -> ktrs).
    entry_type: Literal["trans", "job"] = "trans"


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
