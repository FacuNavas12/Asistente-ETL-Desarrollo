"""
RF11 — Generación de documentación automática
RF12 — Explicación del flujo en lenguaje natural
RF13 — Estructuración de resultados para persistencia
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models.llm_base import BaseLLM
from app.schemas.etl_schemas import ETLDocumentRequest, ETLDocumentResponse
from app.schemas.llm_output_schemas import DOCUMENT_OUTPUT_SCHEMA

_DOCUMENT_SYSTEM = "system_validator.txt"


def _load_system(filename: str) -> str:
    return (Path(__file__).resolve().parent.parent.parent / "prompts" / filename).read_text(encoding="utf-8")


async def document_etl(req: ETLDocumentRequest, llm: BaseLLM) -> ETLDocumentResponse:
    prompt = f"""Genera documentación técnica en lenguaje natural para el siguiente proceso ETL.

La documentación debe:
1. Describir el flujo completo de forma que un desarrollador nuevo lo entienda
2. Explicar cada step en orden, qué hace y por qué existe
3. Mencionar las reglas de negocio aplicadas
4. Indicar los puntos de control de calidad del proceso

Proceso ETL a documentar:

```json
{json.dumps(req.proceso_etl, ensure_ascii=False, indent=2)}
```
"""
    resp = await llm.complete(prompt, _load_system(_DOCUMENT_SYSTEM), schema=DOCUMENT_OUTPUT_SCHEMA)
    data = resp.json_data

    return ETLDocumentResponse(
        documentacion=data.get("documentacion", ""),
        metadata={
            "modelo_usado": resp.model,
            "tokens_input": resp.input_tokens,
            "tokens_output": resp.output_tokens,
            "region_inferencia": resp.provider,
        },
    )
