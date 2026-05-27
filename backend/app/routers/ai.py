import json
import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings

from app.schemas.etl_schemas import (
    ETLRequest,
    ETLGenerateResponse,
    ETLValidateRequest,
    ETLValidateResponse,
    ETLDocumentRequest,
    ETLDocumentResponse,
    InferRequest,
    RefineRequest,
    InferResponse,
    ETLFromInferenceRequest,
)
from app.services.etl_generator import generate_etl, generate_etl_from_inference
from app.services.validator import validate_etl
from app.services.documenter import document_etl
from app.services.structure_inferrer import infer_structures, refine_structures
from app.schemas.job_schemas import (
    JobAnalyzeResponse,
    JobGenerateRequest,
    JobGenerateResponse,
    JobRefineRequest,
)
from app.services import job_analyzer

router = APIRouter(tags=["ETL"])
logger = logging.getLogger(__name__)



async def _handle(fn, *args):
    try:
        return await fn(*args)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except Exception as e:
        logger.error("Service error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


def _validate_etl_request(req: ETLRequest):
    if not req.origenTables:
        raise HTTPException(status_code=422, detail="origenTables no puede estar vacío.")
    if not req.stagingDef:
        raise HTTPException(status_code=422, detail="stagingDef no puede estar vacío.")
    if not req.dwhModel.tables:
        raise HTTPException(status_code=422, detail="dwhModel.tables no puede estar vacío.")


# Endpoint que consume el frontend
@router.post("/api/ai/etl", response_model=ETLGenerateResponse)
async def etl_from_frontend(req: ETLRequest):
    """Recibe el payload del formulario y genera el proceso ETL completo."""
    _validate_etl_request(req)
    return await _handle(generate_etl, req)


# Endpoints REST versionados (para testing directo y futura expansión)
@router.post("/api/v1/etl/generate", response_model=ETLGenerateResponse)
async def generate(req: ETLRequest):
    """RF5, RF6, RF7, RF14 — Genera el proceso ETL completo."""
    _validate_etl_request(req)
    return await _handle(generate_etl, req)


@router.post("/api/v1/etl/validate", response_model=ETLValidateResponse)
async def validate(req: ETLValidateRequest):
    """RF8, RF9 — Valida calidad y malas prácticas."""
    return await _handle(validate_etl, req)


@router.post("/api/v1/etl/document", response_model=ETLDocumentResponse)
async def document(req: ETLDocumentRequest):
    """RF11, RF12, RF13 — Genera documentación en lenguaje natural."""
    return await _handle(document_etl, req)


# ── Flujo de inferencia automática ───────────────────────────────────────────

@router.post("/api/v1/etl/infer-structures", response_model=InferResponse)
async def infer(req: InferRequest):
    """Infiere automáticamente la tabla STG y el modelo DWH a partir de los 3 campos del usuario."""
    return await _handle(infer_structures, req)


@router.post("/api/v1/etl/infer-structures/refine", response_model=InferResponse)
async def refine(req: RefineRequest):
    """Incorpora una corrección en lenguaje natural y regenera las estructuras con contexto acumulado."""
    return await _handle(refine_structures, req)


@router.post("/api/v1/etl/generate-from-inference", response_model=ETLGenerateResponse)
async def generate_from_inference(req: ETLFromInferenceRequest):
    """Genera el proceso ETL completo usando estructuras STG/DWH inferidas por el modelo."""
    return await _handle(generate_etl_from_inference, req)


# ── Flujo de generación de Jobs PDI (.kjb) ────────────────────────────────────

@router.post("/api/v1/job/analyze", response_model=JobAnalyzeResponse)
async def analyze_job(
    ktr_files: List[UploadFile] = File(...),
    job_description: str = Form(...),
    business_rules: Optional[str] = Form(None),
):
    """Parsea N archivos .ktr, infiere el orden lógico y devuelve el plan del job para revisión."""
    try:
        return await job_analyzer.analyze_job(ktr_files, job_description, business_rules)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error en analyze_job: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except Exception as e:
        logger.error("Error en analyze_job: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/job/refine", response_model=JobAnalyzeResponse)
async def refine_job(req: JobRefineRequest):
    """Incorpora una corrección en lenguaje natural y regenera el plan del job con historial acumulado."""
    try:
        return await job_analyzer.refine_job(req)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error en refine_job: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except Exception as e:
        logger.error("Error en refine_job: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/job/generate", response_model=JobGenerateResponse)
async def generate_job(req: JobGenerateRequest):
    """Toma el JobPlan confirmado y genera el XML .kjb final + explicación en lenguaje natural."""
    try:
        return await job_analyzer.generate_job(req.session_id, req.job_plan)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error en generate_job: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except FileNotFoundError as e:
        logger.error("Sesión no encontrada: %s", str(e))
        raise HTTPException(status_code=404, detail="Sesión expirada o no encontrada. Volvé a subir los archivos .ktr.")
    except Exception as e:
        logger.error("Error en generate_job: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    return await _handle(generate_etl_from_inference, req)

#TODO: revisar generate
