"""
AnthropicLLM — wraps the Anthropic Messages API.

Design choices:
- output_config dict approach (not messages.parse()) for symmetry with GeminiLLM:
  both providers receive the same JSON Schema dict, enabling a single schema
  definition per output type. messages.parse() would require Pydantic models in
  the LLM layer, which couples it to the schema layer unnecessarily.
- Underlying AsyncAnthropic client is cached via @lru_cache keyed on
  (api_key, region) so the connection pool is reused across requests while
  keeping AnthropicLLM instances lightweight (no shared state other than config).
- Schema sanitization: Anthropic requires additionalProperties: false on EVERY
  nested object node. We apply _sanitize_for_anthropic() before sending to convert
  any open {"type": "object"} to a closed empty object. Free-form config dicts
  (e.g. ktr step configs) will be constrained to {} in the output; Gemini is the
  better provider for schemas with variable-structure nested objects.
"""
import asyncio
import copy
import json
import logging
import time
from functools import lru_cache
from typing import Any, Dict, Optional

import anthropic

from app.models.llm_base import BaseLLM, LLMResponse, extract_first_json

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BACKOFF_BASE = 2  # seconds: 2, 4, 8, 16


def _enforce_adp(node: Any) -> Any:
    """Recursively add additionalProperties: false to all object-typed nodes."""
    if isinstance(node, dict):
        if node.get("type") == "object" and "additionalProperties" not in node:
            node["additionalProperties"] = False
            if "properties" not in node:
                node["properties"] = {}
        for key in list(node.keys()):
            node[key] = _enforce_adp(node[key])
    elif isinstance(node, list):
        return [_enforce_adp(item) for item in node]
    return node


def _sanitize_for_anthropic(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of schema with additionalProperties: false on every object node.

    Anthropic's constrained decoding rejects any schema where an object node lacks
    an explicit additionalProperties declaration. Free-form config dicts become {} in
    the output; the tradeoff is documented in the module docstring.
    """
    return _enforce_adp(copy.deepcopy(schema))


@lru_cache(maxsize=8)
def _cached_client(api_key: str, region: str) -> anthropic.AsyncAnthropic:
    """One AsyncAnthropic per (api_key, region) pair. Reuses the connection pool."""
    headers = {"anthropic-geography": region} if region else {}
    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        default_headers=headers,
    )
    logger.info("Anthropic client created — region: %s", region or "default")
    return client


class AnthropicLLM(BaseLLM):
    def __init__(
        self,
        model: str,
        temperature: float,
        max_tokens: int,
        api_key: str,
        region: str,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._api_key = api_key
        self._region = region

    def _get_client(self) -> anthropic.AsyncAnthropic:
        return _cached_client(self._api_key, self._region)

    def _region_label(self) -> str:
        return f"anthropic ({self._region})"

    async def complete(
        self,
        prompt: str,
        system: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        client = self._get_client()
        for attempt in range(_MAX_RETRIES):
            try:
                return await self._attempt(client, prompt, system, schema, attempt)
            except anthropic.BadRequestError as e:
                if schema is None:
                    raise RuntimeError(f"[Anthropic] BadRequestError: {e}") from e
                # output_config rejected by API — enter text-mode fallback (no retry loop)
                logger.warning(
                    "[Anthropic] BadRequestError with output_config (attempt %d) — "
                    "entering text-mode fallback: %s",
                    attempt + 1, e,
                )
                return await self._fallback(client, prompt, system)
            except (
                anthropic.RateLimitError,
                anthropic.InternalServerError,
                anthropic.APIConnectionError,
            ) as e:
                wait = _BACKOFF_BASE ** attempt
                logger.warning(
                    "[Anthropic] Transient error (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, _MAX_RETRIES, e, wait,
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(wait)
                else:
                    raise RuntimeError(f"[Anthropic] Max retries reached: {e}") from e
            except anthropic.APIError as e:
                raise RuntimeError(f"[Anthropic] Non-recoverable error: {e}") from e
        raise RuntimeError("[Anthropic] Unexpected exit from retry loop")  # unreachable

    async def _attempt(
        self,
        client: anthropic.AsyncAnthropic,
        prompt: str,
        system: str,
        schema: Optional[Dict[str, Any]],
        attempt: int,
    ) -> LLMResponse:
        kwargs: Dict[str, Any] = dict(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        if schema is not None:
            kwargs["tools"] = [
                {
                    "name": "structured_output",
                    "description": "Output the response as a structured JSON object matching the schema.",
                    "input_schema": _sanitize_for_anthropic(schema),
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": "structured_output"}

        start = time.monotonic()
        # Use streaming internally to bypass the non-streaming max_tokens limit.
        # get_final_message() collects the complete response transparently.
        async with client.messages.stream(**kwargs) as stream:
            response = await stream.get_final_message()
        latency_ms = int((time.monotonic() - start) * 1000)

        stop_reason = response.stop_reason or ""
        if stop_reason == "max_tokens":
            raise RuntimeError(
                f"[Anthropic] Response truncated (stop_reason=max_tokens) — "
                f"current max_tokens={self._max_tokens}. Increase or simplify prompt/schema."
            )

        json_data: Optional[Dict[str, Any]] = None
        raw = ""
        if schema is not None:
            for block in response.content:
                if block.type == "tool_use" and block.name == "structured_output":
                    json_data = block.input
                    raw = json.dumps(json_data, ensure_ascii=False)
                    break
            if json_data is None:
                raise RuntimeError("[Anthropic] No tool_use block in response — structured output failed")
        else:
            raw = response.content[0].text if response.content else ""

        logger.info(
            "Anthropic complete — model: %s | attempt: %d | in: %d | out: %d | stop: %s | %dms",
            self._model, attempt + 1,
            response.usage.input_tokens,
            response.usage.output_tokens,
            stop_reason,
            latency_ms,
        )
        return LLMResponse(
            content=raw,
            json_data=json_data,
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            provider=self._region_label(),
            stop_reason=stop_reason,
            truncated=False,
        )

    async def _fallback(
        self,
        client: anthropic.AsyncAnthropic,
        prompt: str,
        system: str,
    ) -> LLMResponse:
        """Text-mode fallback: second call without output_config + explicit JSON instruction."""
        fallback_system = (
            "CRITICAL: Your response must be ONLY a valid JSON object with no surrounding text, "
            "no explanation, and no markdown code fences. "
            "Start your response with '{' and end with '}'.\n\n"
            + system
        )
        start = time.monotonic()
        response = await client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=fallback_system,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        stop_reason = response.stop_reason or ""
        if stop_reason == "max_tokens":
            raise RuntimeError(
                "[Anthropic] Text-mode fallback also truncated (stop_reason=max_tokens)"
            )

        raw = response.content[0].text
        json_data = extract_first_json(raw)

        logger.warning(
            "[Anthropic] Text-mode fallback completed — model: %s | in: %d | out: %d | stop: %s | %dms",
            self._model,
            response.usage.input_tokens,
            response.usage.output_tokens,
            stop_reason,
            latency_ms,
        )
        return LLMResponse(
            content=raw,
            json_data=json_data,
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            provider=self._region_label(),
            stop_reason=stop_reason,
            truncated=False,
        )
