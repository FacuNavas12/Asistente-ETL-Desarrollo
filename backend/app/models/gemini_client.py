import time
import logging
from pathlib import Path

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

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.google_api_key)
    return _client


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
                "ETL call | model=%s | attempt=%d | input_tokens=%d | output_tokens=%d | latency_ms=%d",
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
                "ETL call | model=%s | attempt=%d | input_tokens=%d | output_tokens=%d | latency_ms=%d",
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
