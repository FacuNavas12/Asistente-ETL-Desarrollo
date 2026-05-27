from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    provider: str  # "gemini" | "anthropic"


class BaseLLM(ABC):
    @abstractmethod
    async def complete(self, prompt: str, system: str) -> LLMResponse: ...
