"""
Compatibility adapter — keeps the call_main / call_secondary public interface
so that job_analyzer (out-of-scope for this sprint) continues to work unchanged.

New service code should accept BaseLLM via dependency injection instead of
importing from this module.
"""
from __future__ import annotations

from pathlib import Path

from app.models.llm_base import LLMResponse


def _load_prompt(filename: str) -> str:
    path = Path(__file__).resolve().parent.parent.parent / "prompts" / filename
    return path.read_text(encoding="utf-8")


async def call_main(user_message: str, system_prompt_file: str) -> LLMResponse:
    """Builds a main LLM client per call (no singleton). Use DI in new code."""
    from app.models.llm_factory import get_llm
    system = _load_prompt(system_prompt_file)
    return await get_llm().complete(user_message, system)


async def call_secondary(user_message: str, system_prompt_file: str) -> LLMResponse:
    """Builds a secondary LLM client per call (no singleton). Use DI in new code."""
    from app.core.config import settings as _settings
    from app.models.llm_factory import build_llm
    llm    = build_llm(_settings, role="secondary")
    system = _load_prompt(system_prompt_file)
    return await llm.complete(user_message, system)
