import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from app.services.claude_service import ask_claude

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/ai", tags=["AI"])

class ChatRequest(BaseModel):
    message: str
    context: str | None = None

class ChatResponse(BaseModel):
    response: str

class EtlCreateRequest(BaseModel):
    origenTables: list[Any]
    stagingDef: Any
    dwhModel: dict[str, Any]
    reglasNegocio: str | None = None

class EtlCreateResponse(BaseModel):
    status: str
    message: str
    received: EtlCreateRequest

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        system = "Eres un asistente útil. Responde siempre en español."
        if request.context:
            system += f"\n\nContexto adicional: {request.context}"

        reply = ask_claude(request.message, system_prompt=system)
        return ChatResponse(response=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/etl", response_model=EtlCreateResponse)
async def create_etl(request: EtlCreateRequest):
    try:
        logger.info("ETL recibido:\n%s", json.dumps(request.model_dump(), indent=2, ensure_ascii=False))
        return EtlCreateResponse(status="ok", message="ETL recibido correctamente", received=request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))