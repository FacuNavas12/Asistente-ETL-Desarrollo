"""
GeminiLLM — wraps the Google GenAI (google-genai) SDK.

Client is cached at module level via @lru_cache, so the underlying HTTP connection
pool is reused across requests.  GeminiLLM instances are lightweight config holders.

response_json_schema (JSON Schema dict) is used for structured output, matching
the same dict format used by AnthropicLLM's output_config. Both providers receive
identical schemas from llm_output_schemas/.

Gemini's generate_content() is synchronous; we wrap it in asyncio.to_thread so
the FastAPI event loop is not blocked.
"""
import asyncio
import json
import logging
import time
from functools import lru_cache
from typing import Any, Dict, Optional

from google import genai
from google.genai import types
from google.genai.errors import ServerError, APIError

from app.models.llm_base import BaseLLM, LLMResponse, extract_first_json

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BACKOFF_BASE = 2  # seconds: 2, 4, 8, 16


def _is_retryable(exc: APIError) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return isinstance(exc, ServerError) or code in (429, 503)


def _is_schema_rejection(exc: APIError) -> bool:
    """True when the error is likely due to the response_json_schema param."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code == 400


@lru_cache(maxsize=4)
def _cached_client(provider: str, api_key: str, project_id: str, location: str) -> genai.Client:
    """One genai.Client per (provider, credentials, region). Reuses the connection pool."""
    if provider == "vertex-ai":
        if not project_id:
            raise RuntimeError(
                "GCP_PROJECT_ID required when GEMINI_PROVIDER=vertex-ai. Add to .env and restart."
            )
        client = genai.Client(vertexai=True, project=project_id, location=location)
        logger.info("Gemini client created — Vertex AI | project: %s | region: %s", project_id, location)
    else:
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY required when GEMINI_PROVIDER=google-ai-studio. Add to .env and restart."
            )
        client = genai.Client(api_key=api_key)
        logger.info("Gemini client created — Google AI Studio")
    return client


def _normalize_finish_reason(finish_reason: Any) -> str:
    """Map Gemini FinishReason enum to normalized string matching Anthropic conventions."""
    name = finish_reason.name if hasattr(finish_reason, "name") else str(finish_reason)
    if name == "STOP":
        return "end_turn"
    if name == "MAX_TOKENS":
        return "max_tokens"
    return name.lower()


class GeminiLLM(BaseLLM):
    def __init__(
        self,
        model: str,
        temperature: float,
        max_tokens: int,
        provider: str,
        api_key: str,
        project_id: str,
        location: str,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._provider = provider
        self._api_key = api_key
        self._project_id = project_id
        self._location = location

    def _get_client(self) -> genai.Client:
        return _cached_client(self._provider, self._api_key, self._project_id, self._location)

    def _region_label(self) -> str:
        if self._provider == "vertex-ai":
            return self._location
        return "us (Google AI Studio)"

    async def complete(
        self,
        prompt: str,
        system: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        return await asyncio.to_thread(self._complete_sync, prompt, system, schema)

    def _complete_sync(
        self,
        prompt: str,
        system: str,
        schema: Optional[Dict[str, Any]],
    ) -> LLMResponse:
        client = self._get_client()
        for attempt in range(_MAX_RETRIES):
            try:
                return self._attempt_sync(client, prompt, system, schema, attempt)
            except APIError as e:
                if schema is not None and _is_schema_rejection(e):
                    logger.warning(
                        "[Gemini] 400 error with response_json_schema (attempt %d) — "
                        "entering text-mode fallback: %s",
                        attempt + 1, e,
                    )
                    return self._fallback_sync(client, prompt, system)
                if not _is_retryable(e):
                    raise RuntimeError(f"[Gemini] Non-recoverable error: {e}") from e
                wait = _BACKOFF_BASE ** attempt
                logger.warning(
                    "[Gemini] Transient error (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, _MAX_RETRIES, e, wait,
                )
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"[Gemini] Max retries reached: {e}") from e
        raise RuntimeError("[Gemini] Unexpected exit from retry loop")  # unreachable

    def _attempt_sync(
        self,
        client: genai.Client,
        prompt: str,
        system: str,
        schema: Optional[Dict[str, Any]],
        attempt: int,
    ) -> LLMResponse:
        config_kwargs: Dict[str, Any] = dict(
            system_instruction=system,
            temperature=self._temperature,
            max_output_tokens=self._max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        if schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = schema
        # No mime type when free-text — Gemini defaults to text/plain

        start = time.monotonic()
        response = client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        finish_reason = (
            response.candidates[0].finish_reason
            if response.candidates
            else None
        )
        stop_reason = _normalize_finish_reason(finish_reason) if finish_reason is not None else ""

        if stop_reason == "max_tokens":
            raise RuntimeError(
                f"[Gemini] Response truncated (finish_reason=MAX_TOKENS) — "
                f"current max_output_tokens={self._max_tokens}. Increase or simplify prompt/schema."
            )

        raw = response.text or ""
        if not raw:
            logger.error("[Gemini] Empty response. finish_reason=%s", finish_reason)

        json_data: Optional[Dict[str, Any]] = None
        if schema is not None:
            json_data = json.loads(raw)

        usage = response.usage_metadata
        logger.info(
            "Gemini complete — model: %s | attempt: %d | in: %d | out: %d | stop: %s | %dms",
            self._model, attempt + 1,
            usage.prompt_token_count or 0,
            usage.candidates_token_count or 0,
            stop_reason,
            latency_ms,
        )
        return LLMResponse(
            content=raw,
            json_data=json_data,
            model=self._model,
            input_tokens=usage.prompt_token_count or 0,
            output_tokens=usage.candidates_token_count or 0,
            provider=self._region_label(),
            stop_reason=stop_reason,
            truncated=False,
        )

    def _fallback_sync(
        self,
        client: genai.Client,
        prompt: str,
        system: str,
    ) -> LLMResponse:
        """Text-mode fallback: retry without response_json_schema + JSON instruction."""
        fallback_system = (
            "CRITICAL: Your response must be ONLY a valid JSON object with no surrounding text, "
            "no explanation, and no markdown code fences. "
            "Start your response with '{' and end with '}'.\n\n"
            + system
        )
        start = time.monotonic()
        response = client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=fallback_system,
                temperature=self._temperature,
                max_output_tokens=self._max_tokens,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        finish_reason = (
            response.candidates[0].finish_reason if response.candidates else None
        )
        stop_reason = _normalize_finish_reason(finish_reason) if finish_reason is not None else ""

        if stop_reason == "max_tokens":
            raise RuntimeError("[Gemini] Text-mode fallback also truncated (finish_reason=MAX_TOKENS)")

        raw = response.text or ""
        json_data = extract_first_json(raw)

        usage = response.usage_metadata
        logger.warning(
            "[Gemini] Text-mode fallback completed — model: %s | in: %d | out: %d | stop: %s | %dms",
            self._model,
            usage.prompt_token_count or 0,
            usage.candidates_token_count or 0,
            stop_reason,
            latency_ms,
        )
        return LLMResponse(
            content=raw,
            json_data=json_data,
            model=self._model,
            input_tokens=usage.prompt_token_count or 0,
            output_tokens=usage.candidates_token_count or 0,
            provider=self._region_label(),
            stop_reason=stop_reason,
            truncated=False,
        )
