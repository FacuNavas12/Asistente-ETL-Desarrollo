import time
import logging
from pathlib import Path

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

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
    logger.info(
        "ETL call | model=%s | input_tokens=%d | output_tokens=%d | latency_ms=%d",
        settings.google_model_main,
        usage.prompt_token_count or 0,
        usage.candidates_token_count or 0,
        latency_ms,
    )
    return response.text, usage


def call_secondary(user_message: str, system_prompt_file: str) -> tuple[str, object]:
    """Llama al modelo secundario (Gemini 2.5 Flash) para validaciones y documentación."""
    client = get_client()
    system_text = _load_prompt(system_prompt_file)

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
        "ETL call | model=%s | input_tokens=%d | output_tokens=%d | latency_ms=%d",
        settings.google_model_secondary,
        usage.prompt_token_count or 0,
        usage.candidates_token_count or 0,
        latency_ms,
    )
    return response.text, usage
