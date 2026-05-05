from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.claude_service import ask_claude

router = APIRouter(prefix="/api/ai", tags=["AI"])

class ChatRequest(BaseModel):
    message: str
    context: str | None = None  # datos adicionales del usuario o sesión

class ChatResponse(BaseModel):
    response: str

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