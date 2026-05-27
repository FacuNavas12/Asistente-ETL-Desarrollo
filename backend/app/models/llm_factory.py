from functools import lru_cache

from app.core.config import settings
from app.models.llm_base import BaseLLM


@lru_cache(maxsize=1)
def _build_main() -> BaseLLM:
    if settings.llm_provider == "anthropic":
        from app.models.anthropic_llm import AnthropicLLM
        return AnthropicLLM(
            model=settings.anthropic_model,
            temperature=settings.main_temperature,
            max_tokens=settings.main_max_tokens,
        )
    from app.models.gemini_llm import GeminiLLM
    return GeminiLLM(
        model=settings.gemini_model,
        temperature=settings.main_temperature,
        max_tokens=settings.main_max_tokens,
    )


@lru_cache(maxsize=1)
def _build_secondary() -> BaseLLM:
    if settings.llm_provider == "anthropic":
        from app.models.anthropic_llm import AnthropicLLM
        return AnthropicLLM(
            model=settings.anthropic_model,
            temperature=settings.secondary_temperature,
            max_tokens=settings.secondary_max_tokens,
        )
    from app.models.gemini_llm import GeminiLLM
    return GeminiLLM(
        model=settings.gemini_model,
        temperature=settings.secondary_temperature,
        max_tokens=settings.secondary_max_tokens,
    )


def get_llm() -> BaseLLM:
    """FastAPI Depends-compatible factory. Retorna la instancia LLM principal."""
    return _build_main()
