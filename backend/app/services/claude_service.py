import anthropic
from app.core.config import settings

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

def ask_claude(user_message: str, system_prompt: str = None) -> str:
    """
    Envía un mensaje a Claude y retorna la respuesta como texto.
    system_prompt: aquí defines cómo debe comportarse tu agente.
    """
    messages = [{"role": "user", "content": user_message}]
    
    kwargs = {
        "model": settings.model,
        "max_tokens": 1024,
        "messages": messages,
    }
    
    if system_prompt:
        kwargs["system"] = system_prompt
    
    response = client.messages.create(**kwargs)
    return response.content[0].text