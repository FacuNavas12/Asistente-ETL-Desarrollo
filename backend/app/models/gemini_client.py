"""
Adapter de compatibilidad — mantiene la firma pública call_main / call_secondary
delegando al factory de LLM. Los servicios importan desde aquí sin cambio de ruta.
"""
from pathlib import Path

from app.models.llm_base import LLMResponse
from app.models.llm_factory import _build_main, _build_secondary


def _load_prompt(filename: str) -> str:
    path = Path(__file__).resolve().parent.parent.parent / "prompts" / filename
    return path.read_text(encoding="utf-8")


async def call_main(user_message: str, system_prompt_file: str) -> LLMResponse:
    """Llama al LLM principal (generación ETL, inferencia de estructuras)."""
    system = _load_prompt(system_prompt_file)
    return await _build_main().complete(user_message, system)


async def call_secondary(user_message: str, system_prompt_file: str) -> LLMResponse:
    """Llama al LLM secundario (validaciones y documentación — temperatura 0)."""
    system = _load_prompt(system_prompt_file)
    return await _build_secondary().complete(user_message, system)
