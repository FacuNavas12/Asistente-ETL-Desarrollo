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
)
from app.services.etl_generator import generate_etl
from app.services.validator import validate_etl
from app.services.documenter import document_etl

router = APIRouter(prefix="/api/v1/etl", tags=["ETL"])
logger = logging.getLogger(__name__)


@router.post("/generate", response_model=ETLGenerateResponse)
async def generate(req: ETLRequest):
    """RF5, RF6, RF7, RF14 — Genera el proceso ETL completo con Claude Sonnet."""
    try:
        return generate_etl(req)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error in /generate: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except Exception as e:
        logger.error("Error in /generate: %s", str(e))
        raise HTTPException(status_code=500, detail="Error al generar el proceso ETL.")


@router.post("/validate", response_model=ETLValidateResponse)
async def validate(req: ETLValidateRequest):
    """RF8, RF9 — Valida calidad y malas prácticas con Claude Haiku."""
    try:
        return validate_etl(req)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error in /validate: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except Exception as e:
        logger.error("Error in /validate: %s", str(e))
        raise HTTPException(status_code=500, detail="Error al validar el proceso ETL.")


@router.post("/document", response_model=ETLDocumentResponse)
async def document(req: ETLDocumentRequest):
    """RF11, RF12, RF13 — Genera documentación en lenguaje natural con Claude Haiku."""
    try:
        return document_etl(req)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error in /document: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except Exception as e:
        logger.error("Error in /document: %s", str(e))
        raise HTTPException(status_code=500, detail="Error al documentar el proceso ETL.")
