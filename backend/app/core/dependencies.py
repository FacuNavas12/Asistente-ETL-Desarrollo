"""
FastAPI dependency providers.

Settings are read once (lru_cache). LLM clients are created per-request via
build_llm() — no module-level singleton, fully testable via override.
DB sessions come from database.get_db (already a proper generator dependency).
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from app.core.config import Settings
from app.models.llm_base import BaseLLM


@lru_cache
def get_settings() -> Settings:
    """Read environment variables once. Cached for the process lifetime."""
    return Settings()


def get_main_llm(settings: Settings = Depends(get_settings)) -> BaseLLM:
    """Main LLM: generative temperature, higher token budget."""
    from app.models.llm_factory import build_llm
    return build_llm(settings, role="main")


def get_secondary_llm(settings: Settings = Depends(get_settings)) -> BaseLLM:
    """Secondary LLM: temperature=0, lower token budget (validation / docs)."""
    from app.models.llm_factory import build_llm
    return build_llm(settings, role="secondary")
