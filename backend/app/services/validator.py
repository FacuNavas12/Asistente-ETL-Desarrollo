"""
RF8 — Verificación de calidad del flujo ETL
RF9 — Detección de malas prácticas ETL
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models.llm_base import BaseLLM
from app.schemas.etl_schemas import ETLValidateRequest, ETLValidateResponse


def _load_system(filename: str) -> str:
    return (Path(__file__).resolve().parent.parent.parent / "prompts" / filename).read_text(encoding="utf-8")


async def validate_etl(req: ETLValidateRequest, llm: BaseLLM) -> ETLValidateResponse:
    prompt = f"""Analiza el siguiente proceso ETL y detecta problemas de calidad y malas prácticas:

```json
{json.dumps(req.proceso_etl, ensure_ascii=False, indent=2)}
```
"""
    resp = await llm.complete(prompt, _load_system("system_validator.txt"))
    data = json.loads(resp.content)

    return ETLValidateResponse(
        validaciones=data.get("validaciones", []),
        advertencias_buenas_practicas=data.get("advertencias_buenas_practicas", []),
        metadata={
            "modelo_usado": resp.model,
            "tokens_input": resp.input_tokens,
            "tokens_output": resp.output_tokens,
            "region_inferencia": resp.provider,
        },
    )
