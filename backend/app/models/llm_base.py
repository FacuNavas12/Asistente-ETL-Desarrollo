from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import re
from typing import Any, Dict, Optional


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    provider: str
    json_data: Optional[Dict[str, Any]] = field(default=None)
    stop_reason: str = field(default="")
    truncated: bool = field(default=False)


def extract_first_json(raw: str) -> Dict[str, Any]:
    """Last-resort JSON extractor. Only enters when schema mode failed (BadRequestError fallback).
    Never called in the happy path."""
    match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', raw)
    if not match:
        raise ValueError("No JSON object or array found in LLM response")
    return json.loads(match.group(1))


class BaseLLM(ABC):
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """Complete a prompt.

        schema=None  → free-text mode; json_data will be None in the response.
        schema=dict  → structured mode; provider uses native constrained decoding
                       (output_config.format for Anthropic, response_json_schema for Gemini).
                       json_data is always populated on return.
                       Raises RuntimeError on stop_reason==max_tokens (truncation).
                       On BadRequestError/4xx from schema param, falls back to text mode
                       + explicit JSON instruction + extract_first_json.
        """
        ...
