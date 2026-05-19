import json
import logging

from fastapi import APIRouter, HTTPException

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

router = APIRouter(tags=["ETL"])
logger = logging.getLogger(__name__)


def _handle(fn, *args):
    try:
        return fn(*args)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except Exception as e:
        logger.error("Service error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint que consume el frontend
@router.post("/api/ai/etl", response_model=ETLGenerateResponse)
async def etl_from_frontend(req: ETLRequest):
    """Recibe el payload del formulario y genera el proceso ETL completo."""
    return _handle(generate_etl, req)


# Endpoints REST versionados (para testing directo y futura expansión)
@router.post("/api/v1/etl/generate", response_model=ETLGenerateResponse)
async def generate(req: ETLRequest):
    """RF5, RF6, RF7, RF14 — Genera el proceso ETL completo."""
    return _handle(generate_etl, req)


@router.post("/api/v1/etl/validate", response_model=ETLValidateResponse)
async def validate(req: ETLValidateRequest):
    """RF8, RF9 — Valida calidad y malas prácticas."""
    return _handle(validate_etl, req)


@router.post("/api/v1/etl/document", response_model=ETLDocumentResponse)
async def document(req: ETLDocumentRequest):
    """RF11, RF12, RF13 — Genera documentación en lenguaje natural."""
    return _handle(document_etl, req)


# ── Flujo de inferencia automática ───────────────────────────────────────────

@router.post("/api/v1/etl/infer-structures", response_model=InferResponse)
async def infer(req: InferRequest):
    """Infiere automáticamente la tabla STG y el modelo DWH a partir de los 3 campos del usuario."""
    return _handle(infer_structures, req)


@router.post("/api/v1/etl/infer-structures/refine", response_model=InferResponse)
async def refine(req: RefineRequest):
    """Incorpora una corrección en lenguaje natural y regenera las estructuras con contexto acumulado."""
    return _handle(refine_structures, req)


@router.post("/api/v1/etl/generate-from-inference", response_model=ETLGenerateResponse)
async def generate_from_inference(req: ETLFromInferenceRequest):
    """Genera el proceso ETL completo usando estructuras STG/DWH inferidas por el modelo."""
    return _handle(generate_etl_from_inference, req)
