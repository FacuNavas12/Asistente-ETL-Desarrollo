import base64

from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, AliasChoices, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.base import NoDecode

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_PATH))

    # ── Proveedor LLM ─────────────────────────────────────────────────────────
    # "gemini" | "anthropic" — cambiar solo en .env para switchear proveedor
    llm_provider: str = "gemini"

    # ── Credenciales de proveedores ───────────────────────────────────────────
    google_api_key: str
    # Opcional: solo requerida cuando LLM_PROVIDER=anthropic
    anthropic_api_key: str = ""

    # ── Modelos ───────────────────────────────────────────────────────────────
    # GEMINI_MODEL acepta también GOOGLE_MODEL_MAIN (alias de compatibilidad).
    # Usado para ambos roles (main y secondary); la diferencia es temperatura y tokens.
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias=AliasChoices("gemini_model", "google_model_main"),
    )
    anthropic_model: str = "claude-sonnet-4-20250514"

    # ── Base de datos ─────────────────────────────────────────────────────────
    # Ejemplo: postgresql+psycopg2://user:pass@localhost:5432/etl_db
    database_url: str

    # ── Cifrado de credenciales ───────────────────────────────────────────────
    # CSV de claves Fernet. La primera es la activa; las demás solo desencriptan.
    # NoDecode evita que pydantic-settings JSON-decodifique el valor antes del validator.
    # Generar: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    credentials_encryption_keys: Annotated[list[str], NoDecode]

    # ── Driver ODBC SQL Server ────────────────────────────────────────────────
    mssql_odbc_driver: str = "ODBC Driver 18 for SQL Server"

    # ── Parámetros de generación ──────────────────────────────────────────────
    main_temperature: float = 0.1    # RNF10 — reproducibilidad
    main_max_tokens: int = 32768     # subido desde 16384 — caso 01 (demografía) lo excedía
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
