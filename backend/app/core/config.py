from pydantic_settings import BaseSettings
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    google_api_key: str

    # Gemini 2.5 Flash para ambos roles de momento.
    # Cambiar GOOGLE_MODEL_MAIN a gemini-2.5-pro cuando se inicie la comparativa.
    google_model_main: str = "gemini-2.5-flash"
    google_model_secondary: str = "gemini-2.5-flash"

    # Parámetros de generación
    main_temperature: float = 0.1    # RNF10 — reproducibilidad
    main_max_tokens: int = 16384
    secondary_temperature: float = 0.0  # determinismo total para validaciones
    secondary_max_tokens: int = 2048

    class Config:
        env_file = str(ENV_PATH)


settings = Settings()
