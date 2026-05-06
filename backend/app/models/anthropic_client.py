import time
import logging
from pathlib import Path

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        headers = {}
        if settings.anthropic_inference_geo:
            headers["anthropic-inference-geo"] = settings.anthropic_inference_geo
        _client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            default_headers=headers,
        )
    return _client


def _load_prompt(filename: str) -> str:
    path = Path(__file__).resolve().parent.parent.parent / "prompts" / filename
    return path.read_text(encoding="utf-8")


def call_main(user_message: str, system_prompt_file: str) -> tuple[str, anthropic.types.Usage]:
    """Llama a Claude Sonnet (motor principal) con prompt caching en el system prompt."""
    client = get_client()
    system_text = _load_prompt(system_prompt_file)

    start = time.monotonic()
    response = client.messages.create(
        model=settings.anthropic_model_main,
        max_tokens=settings.main_max_tokens,
        temperature=settings.main_temperature,
        system=[
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},  # prompt caching — reduce costo 40-50%
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    logger.info(
        "ETL call | model=%s | input_tokens=%d | output_tokens=%d | latency_ms=%d",
        settings.anthropic_model_main,
        response.usage.input_tokens,
        response.usage.output_tokens,
        latency_ms,
    )
    return response.content[0].text, response.usage


def call_secondary(user_message: str, system_prompt_file: str) -> tuple[str, anthropic.types.Usage]:
    """Llama a Claude Haiku (motor secundario) para validaciones y documentación."""
    client = get_client()
    system_text = _load_prompt(system_prompt_file)

    start = time.monotonic()
    response = client.messages.create(
        model=settings.anthropic_model_secondary,
        max_tokens=settings.secondary_max_tokens,
        temperature=settings.secondary_temperature,
        system=[
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    logger.info(
        "ETL call | model=%s | input_tokens=%d | output_tokens=%d | latency_ms=%d",
        settings.anthropic_model_secondary,
        response.usage.input_tokens,
        response.usage.output_tokens,
        latency_ms,
    )
    return response.content[0].text, response.usage
