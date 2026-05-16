import base64

from pathlib import Path
from typing import Annotated, Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.base import NoDecode

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_PATH))

    google_api_key: str

    # Cadena de conexión de la base de datos de la aplicación.
    # Ejemplo: postgresql+psycopg2://user:pass@localhost:5432/etl_db
    database_url: str

    # Lista de claves Fernet para cifrado de passwords (soporte de rotación).
    # En el .env se escribe como CSV: KEY_ACTIVA,KEY_ANTERIOR,...
    # La primera clave es la activa para encriptar; las siguientes solo descifran durante rotación.
    # NoDecode evita que pydantic-settings intente JSON-decodificar el valor antes del validator.
    # Generar una clave con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    credentials_encryption_keys: Annotated[list[str], NoDecode]

    # Driver ODBC para SQL Server. Env var: MSSQL_ODBC_DRIVER.
    mssql_odbc_driver: str = "ODBC Driver 18 for SQL Server"

    # Gemini 2.5 Flash para ambos roles de momento.
    # Cambiar GOOGLE_MODEL_MAIN a gemini-2.5-pro cuando se inicie la comparativa.
    google_model_main: str = "gemini-2.5-flash"
    google_model_secondary: str = "gemini-2.5-flash"

    # Parámetros de generación
    main_temperature: float = 0.1    # RNF10 — reproducibilidad
    main_max_tokens: int = 4096
    secondary_temperature: float = 0.0  # determinismo total para validaciones
    secondary_max_tokens: int = 2048

    @field_validator("credentials_encryption_keys", mode="before")
    @classmethod
    def _parse_keys(cls, v: Any) -> list[str]:
        """Acepta CSV desde env var o lista directa (útil en tests)."""
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        if isinstance(v, list):
            return [str(k).strip() for k in v if str(k).strip()]
        return v

    @field_validator("credentials_encryption_keys", mode="after")
    @classmethod
    def _validate_keys(cls, v: list[str]) -> list[str]:
        """Valida que haya al menos una clave y que cada una decodifique a 32 bytes exactos."""
        if not v:
            raise ValueError("CREDENTIALS_ENCRYPTION_KEYS no puede estar vacía")
        for i, k in enumerate(v):
            try:
                key_bytes = base64.urlsafe_b64decode(k)
            except Exception:
                raise ValueError(
                    f"La clave en posición {i} no es base64 URL-safe válido"
                )
            if len(key_bytes) != 32:
                raise ValueError(
                    f"La clave en posición {i} debe decodificar a exactamente 32 bytes "
                    f"(obtenido: {len(key_bytes)})"
                )
        return v


settings = Settings()
