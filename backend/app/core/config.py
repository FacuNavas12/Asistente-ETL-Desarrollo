import base64

from pathlib import Path
from typing import Annotated, Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.base import NoDecode

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_PATH))

    # ── Proveedor Gemini ─────────────────────────────────────────────────────
    # "google-ai-studio" (default, free, procesa en EE.UU.)
    # "vertex-ai"        (producción, región configurable, requiere GCP project)
    gemini_provider: str = "google-ai-studio"

    # Requerida cuando gemini_provider=google-ai-studio.
    # Cuando gemini_provider=vertex-ai, no se usa (autenticación vía ADC o Service Account).
    google_api_key: str = ""

    # Requeridos cuando gemini_provider=vertex-ai.
    # gcp_location controla en qué región física Google procesa las inferencias.
    # Canada (Ley 18.331): northamerica-northeast1 (Montréal) | northamerica-northeast2 (Toronto)
    # UE (GDPR):           europe-west4 (Países Bajos)
    gcp_project_id: str = ""
    gcp_location: str = "northamerica-northeast1"

    # Cadena de conexión de la base de datos de la aplicación.
    # Requerido solo para el módulo de conexiones (/api/v1/connections).
    # Ejemplo: postgresql+psycopg2://user:pass@localhost:5432/etl_db
    database_url: Optional[str] = None

    # Lista de claves Fernet para cifrado de passwords (soporte de rotación).
    # Requerido solo para el módulo de conexiones (/api/v1/connections).
    # En el .env se escribe como CSV: KEY_ACTIVA,KEY_ANTERIOR,...
    # NoDecode evita que pydantic-settings intente JSON-decodificar el valor antes del validator.
    # Generar una clave con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    credentials_encryption_keys: Annotated[list[str], NoDecode] = []

    # Driver ODBC para SQL Server. Env var: MSSQL_ODBC_DRIVER.
    mssql_odbc_driver: str = "ODBC Driver 18 for SQL Server"

    # Gemini 2.5 Flash para ambos roles de momento.
    # Cambiar GOOGLE_MODEL_MAIN a gemini-2.5-pro cuando se inicie la comparativa.
    google_model_main: str = "gemini-2.5-flash"
    google_model_secondary: str = "gemini-2.5-flash"

    # ── Autenticación de la API (Marco AGESIC 5.0 — función Proteger) ───────────
    # Cuando auth_required=False (default dev) no se valida ningún token.
    # En producción: AUTH_REQUIRED=true + configurar las tres vars siguientes.
    auth_required: bool = False

    # URL del endpoint JWKS del proveedor de identidad.
    # Auth0 (prototipo):  https://<tenant>.auth0.com/.well-known/jwks.json
    # Azure AD / Entra:   https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys
    auth_jwks_url: str = ""

    # Identificador de la API registrado en el proveedor (claim "aud" del JWT).
    auth_audience: str = ""

    # Issuer del token (claim "iss" del JWT).
    # Auth0: https://<tenant>.auth0.com/
    auth_issuer: str = ""

    # Parámetros de generación
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
        """Valida formato de claves Fernet si están configuradas; si no, permite lista vacía."""
        if not v:
            return v  # no configurado — el módulo de conexiones lo rechazará en runtime
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
