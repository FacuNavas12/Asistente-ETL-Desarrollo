import asyncio
import time
import logging
from typing import Optional

from google import genai
from google.genai import types
from google.genai.errors import ServerError, APIError

from app.core.config import settings
from app.models.llm_base import BaseLLM, LLMResponse

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BACKOFF_BASE = 2  # segundos: 2, 4, 8, 16


def _is_retryable(exc: APIError) -> bool:
    """503 (alta demanda) y 429 (rate limit) son transitorios."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return isinstance(exc, ServerError) or code in (429, 503)


class GeminiLLM(BaseLLM):
    def __init__(self, model: str, temperature: float, max_tokens: int) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.google_api_key)
        return self._client

    async def complete(self, prompt: str, system: str) -> LLMResponse:
        return await asyncio.to_thread(self._complete_sync, prompt, system)

    def _complete_sync(self, prompt: str, system: str) -> LLMResponse:
        client = self._get_client()
        for attempt in range(_MAX_RETRIES):
            try:
                start = time.monotonic()
                response = client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        temperature=self._temperature,
                        max_output_tokens=self._max_tokens,
                        response_mime_type="application/json",
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                usage = response.usage_metadata
                raw = response.text
                logger.info(
                    "Gemini completado — Modelo: %s | Intento: %d | "
                    "Tokens enviados: %d | Tokens recibidos: %d | Tiempo: %d ms",
                    self._model, attempt + 1,
                    usage.prompt_token_count or 0,
                    usage.candidates_token_count or 0,
                    latency_ms,
                )
                if not raw:
                    logger.error(
                        "[Gemini] Respuesta vacía. finish_reason=%s",
                        response.candidates[0].finish_reason if response.candidates else "unknown",
                    )
                return LLMResponse(
                    content=raw,
                    model=self._model,
                    input_tokens=usage.prompt_token_count or 0,
                    output_tokens=usage.candidates_token_count or 0,
                    provider="gemini",
                )
            except APIError as e:
                if not _is_retryable(e):
                    raise RuntimeError(f"[Gemini] Error no recuperable: {e}") from e
                wait = _BACKOFF_BASE ** attempt
                logger.warning(
                    "[Gemini] Error transitorio (intento %d/%d): %s — reintentando en %ds",
                    attempt + 1, _MAX_RETRIES, e, wait,
                )
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"[Gemini] Máximo de reintentos alcanzado: {e}") from e
