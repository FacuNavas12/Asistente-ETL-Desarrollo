"""
LLM factory — no module-level singletons, no @lru_cache on the wrapper.
Each call to build_llm() returns a new LLM wrapper (lightweight config holder).
The underlying provider clients are cached inside each LLM module via @lru_cache,
so connection pools are reused across requests without holding state here.
FastAPI dependency injection (core/dependencies.py) is the intended call site.
"""
from __future__ import annotations

from app.core.config import Settings
from app.models.llm_base import BaseLLM


def build_llm(settings: Settings, role: str = "main") -> BaseLLM:
    """
    Create an LLM wrapper from settings.
    role: "main"      — generative (configurable temperature)
          "secondary" — deterministic (temp=0, fewer tokens)
    """
    temperature = settings.main_temperature      if role == "main" else settings.secondary_temperature
    max_tokens  = settings.main_max_tokens       if role == "main" else settings.secondary_max_tokens

    if settings.llm_provider == "anthropic":
        from app.models.anthropic_llm import AnthropicLLM
        return AnthropicLLM(
            model=settings.anthropic_model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=settings.anthropic_api_key,
            region=settings.anthropic_inference_region,
        )

    from app.models.gemini_llm import GeminiLLM
    return GeminiLLM(
        model=settings.gemini_model,
        temperature=temperature,
        max_tokens=max_tokens,
        provider=settings.gemini_provider,
        api_key=settings.google_api_key,
        project_id=settings.gcp_project_id,
        location=settings.gcp_location,
    )
