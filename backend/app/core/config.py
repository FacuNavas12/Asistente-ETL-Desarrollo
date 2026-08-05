from pathlib import Path

from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_PATH), extra="ignore")

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
        default="gemini-3.5-flash",
        validation_alias=AliasChoices("gemini_model", "google_model_main"),
    )
    anthropic_model: str = "claude-sonnet-4-6"
    # Residencia geográfica de inferencia (Ley 18.331 / AGESIC 5.0).
    # "ca" → Canadá (adecuación equivalente a Uruguay). Requiere Claude Enterprise o acuerdo de DPA.
    # Referencia: https://docs.anthropic.com/en/api/getting-started#geographic-routing
    anthropic_inference_region: str = "ca"

    # ── Base de datos ─────────────────────────────────────────────────────────
    # Dev local: sqlite:///./app.db (default). Prod: postgresql+psycopg://...
    database_url: str = "sqlite:///./app.db"

    # ── Driver ODBC SQL Server ────────────────────────────────────────────────
    mssql_odbc_driver: str = "ODBC Driver 18 for SQL Server"

    # ── Conexiones del .ktr generado ──────────────────────────────────────────
    # Y (default): la transformación se marca "database transactional" en Spoon
    # (<unique_connections>) — Kettle abre UNA conexión física por nombre de
    # conexión y la comparte entre todos los steps que la referencian, en vez de
    # una conexión por step. Evita agotar el pool de la BD destino sin importar
    # cuántos steps de BD tenga la transformación. Propiedad general del .ktr,
    # no depende del tamaño de pool de ningún proveedor puntual.
    shared_connections: bool = True

    # ── Parámetros de generación ──────────────────────────────────────────────
    main_temperature: float = 0.1    # RNF10 — reproducibilidad
    main_max_tokens: int = 32768     # subido desde 16384 — caso 01 (demografía) lo excedía
    secondary_temperature: float = 0.0  # determinismo total para validaciones
    secondary_max_tokens: int = 8192

    # Timeout por intento de llamada al LLM (segundos). El SDK de Anthropic usa
    # 600s por defecto — combinado con los 4 reintentos del wrapper, un stream
    # que se cuelga (sin datos, sin error) podía bloquear un job hasta ~40 min
    # antes de fallar. Un timeout explícito y más corto convierte un cuelgue en
    # un error claro y rápido en vez de un job trancado en "pending".
    llm_request_timeout_s: float = 240.0

    # ── Proveedor Gemini (compliance) ─────────────────────────────────────────
    # "google-ai-studio" (default, free, procesa en EE.UU.)
    # "vertex-ai"        (producción, región configurable, requiere GCP project)
    gemini_provider: str = "google-ai-studio"

    # Requeridos cuando gemini_provider=vertex-ai.
    # gcp_location controla en qué región física Google procesa las inferencias.
    # Canada (Ley 18.331): northamerica-northeast1 (Montréal) | northamerica-northeast2 (Toronto)
    # UE (GDPR):           europe-west4 (Países Bajos)
    gcp_project_id: str = ""
    gcp_location: str = "northamerica-northeast1"

    # ── Integración Superset ──────────────────────────────────────────────────
    superset_url: str = "http://localhost:8088"
    superset_username: str = "admin"
    superset_password: str = "admin"
    # Driver SQL Server para el sqlalchemy_uri que se registra EN Superset (no
    # el de este backend — Superset corre en su propio entorno/contenedor).
    # pymssql es la convención más común en imágenes de Superset porque no
    # requiere el driver ODBC de sistema que sí necesita pyodbc.
    superset_mssql_driver: str = "pymssql"

    # ── Autenticación de la API (Marco AGESIC 5.0 — función Proteger) ─────────
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

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Orígenes permitidos por el navegador (lista separada por comas). Dev usa
    # el server de Vite; en producción hay que agregar el dominio del frontend
    # deployado (ej. https://mi-app.vercel.app). Sin esto, el navegador bloquea
    # todas las llamadas desde el dominio de Vercel.
    allowed_origins: str = "http://localhost:5173"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
