from pydantic_settings import BaseSettings
from pathlib import Path

# Sube dos niveles desde app/core/ hasta backend/
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

class Settings(BaseSettings):
    anthropic_api_key: str
    model: str = "claude-haiku-4-5-20251001"

    class Config:
        env_file = str(ENV_PATH)

settings = Settings()