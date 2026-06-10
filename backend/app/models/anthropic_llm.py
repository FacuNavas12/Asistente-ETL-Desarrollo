import asyncio
import time
import logging
from typing import Optional

import anthropic

from app.core.config import settings
from app.models.llm_base import BaseLLM, LLMResponse

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BACKOFF_BASE = 2  # segundos: 2, 4, 8, 16


class AnthropicLLM(BaseLLM):
    def __init__(self, model: str, temperature: float, max_tokens: int) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client: Optional[anthropic.AsyncAnthropic] = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            # anthropic-geography: controla en qué región procesa Anthropic la inferencia.
            # "ca" → Canadá (PIPEDA / adecuación equivalente Ley 18.331). AGESIC 5.0 — Proteger.
            # Requiere Claude Enterprise o DPA firmado con Anthropic.
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                default_headers={"anthropic-geography": settings.anthropic_inference_region},
            )
            logger.info(
                "Anthropic client — región de inferencia: %s",
                settings.anthropic_inference_region,
            )
        return self._client

    def _region_label(self) -> str:
        return f"anthropic ({settings.anthropic_inference_region})"

    async def complete(self, prompt: str, system: str) -> LLMResponse:
        client = self._get_client()
        for attempt in range(_MAX_RETRIES):
            try:
                start = time.monotonic()
                response = await client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                raw = response.content[0].text
                logger.info(
                    "Anthropic completado — Modelo: %s | Intento: %d | "
                    "Tokens enviados: %d | Tokens recibidos: %d | Tiempo: %d ms",
                    self._model, attempt + 1,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    latency_ms,
                )
                return LLMResponse(
                    content=raw,
                    model=self._model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    provider=self._region_label(),
                )
            except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError) as e:
                wait = _BACKOFF_BASE ** attempt
                logger.warning(
                    "[Anthropic] Error transitorio (intento %d/%d): %s — reintentando en %ds",
                    attempt + 1, _MAX_RETRIES, e, wait,
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(wait)
                else:
                    raise RuntimeError(f"[Anthropic] Máximo de reintentos alcanzado: {e}") from e
            except anthropic.APIError as e:
                raise RuntimeError(f"[Anthropic] Error no recuperable: {e}") from e
