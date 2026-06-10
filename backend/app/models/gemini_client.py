import time
import logging
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
from google.genai.errors import ServerError, APIError

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BACKOFF_BASE = 2   # segundos: 2, 4, 8, 16


def _is_retryable(exc: APIError) -> bool:
    """503 (alta demanda) y 429 (rate limit) son transitorios y vale la pena reintentar."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return isinstance(exc, ServerError) or code in (429, 503)


_client: Optional[genai.Client] = None


def get_client() -> genai.Client:
    """
    Retorna un cliente Gemini singleton configurado según GEMINI_PROVIDER.

    google-ai-studio (default / desarrollo):
        Usa GOOGLE_API_KEY. Procesa en EE.UU. No tiene control de región.

    vertex-ai (producción):
        Usa Application Default Credentials o Service Account de GCP.
        Procesa en GCP_LOCATION — por defecto northamerica-northeast1 (Canadá),
        jurisdicción con adecuación GDPR equivalente a Uruguay (PIPEDA).
        Requiere GCP_PROJECT_ID y que la cuenta tenga el rol Vertex AI User.
        Setup: https://cloud.google.com/vertex-ai/docs/authentication
    """
    global _client
    if _client is not None:
        return _client

    if settings.gemini_provider == "vertex-ai":
        if not settings.gcp_project_id:
            raise ValueError(
                "GCP_PROJECT_ID es requerido cuando GEMINI_PROVIDER=vertex-ai. "
                "Agregar al .env y reiniciar."
            )
        _client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )
        logger.info(
            "Gemini client — proveedor: Vertex AI | proyecto: %s | región: %s",
            settings.gcp_project_id,
            settings.gcp_location,
        )
    else:
        if not settings.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY es requerido cuando GEMINI_PROVIDER=google-ai-studio. "
                "Agregar al .env y reiniciar."
            )
        _client = genai.Client(api_key=settings.google_api_key)
        logger.info("Gemini client — proveedor: Google AI Studio (EE.UU.)")

    return _client


def get_region_label() -> str:
    """Etiqueta de región real para incluir en MetadataResponse."""
    if settings.gemini_provider == "vertex-ai":
        return settings.gcp_location
    return "us (Google AI Studio)"


def _load_prompt(filename: str) -> str:
    path = Path(__file__).resolve().parent.parent.parent / "prompts" / filename
    return path.read_text(encoding="utf-8")


def call_main(user_message: str, system_prompt_file: str) -> tuple[str, object]:
    """Llama al modelo principal (Gemini 2.5 Flash/Pro) para generación ETL."""
    client = get_client()
    system_text = _load_prompt(system_prompt_file)

    for attempt in range(_MAX_RETRIES):
        try:
            start = time.monotonic()
            response = client.models.generate_content(
                model=settings.google_model_main,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_text,
                    temperature=settings.main_temperature,
                    max_output_tokens=settings.main_max_tokens,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            usage = response.usage_metadata
            raw = response.text
            logger.info(
                "🚀 Generación completada — Modelo: %s | Intento: %d | "
                "Tokens enviados: %d | Tokens recibidos: %d | Tiempo de respuesta: %d ms",
                settings.google_model_main, attempt + 1,
                usage.prompt_token_count or 0,
                usage.candidates_token_count or 0,
                latency_ms,
            )
            if not raw:
                logger.error("Gemini (main) returned empty response. finish_reason=%s",
                             response.candidates[0].finish_reason if response.candidates else "unknown")
            return raw, usage
        except APIError as e:
            if not _is_retryable(e):
                raise
            wait = _BACKOFF_BASE ** attempt
            logger.warning("Gemini (main) transient error (attempt %d/%d): %s — retrying in %ds",
                           attempt + 1, _MAX_RETRIES, e, wait)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(wait)
            else:
                raise


def call_secondary(user_message: str, system_prompt_file: str) -> tuple[str, object]:
    """Llama al modelo secundario (Gemini 2.5 Flash) para validaciones y documentación."""
    client = get_client()
    system_text = _load_prompt(system_prompt_file)

    for attempt in range(_MAX_RETRIES):
        try:
            start = time.monotonic()
            response = client.models.generate_content(
                model=settings.google_model_secondary,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_text,
                    temperature=settings.secondary_temperature,
                    max_output_tokens=settings.secondary_max_tokens,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            usage = response.usage_metadata
            logger.info(
                "🚀 Generación completada — Modelo: %s | Intento: %d | "
                "Tokens enviados: %d | Tokens recibidos: %d | Tiempo de respuesta: %d ms",
                settings.google_model_secondary, attempt + 1,
                usage.prompt_token_count or 0,
                usage.candidates_token_count or 0,
                latency_ms,
            )
            return response.text, usage
        except APIError as e:
            if not _is_retryable(e):
                raise
            wait = _BACKOFF_BASE ** attempt
            logger.warning("Gemini (secondary) transient error (attempt %d/%d): %s — retrying in %ds",
                           attempt + 1, _MAX_RETRIES, e, wait)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(wait)
            else:
                raise
