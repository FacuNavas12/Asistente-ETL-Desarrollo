"""
RF8 — Verificación de calidad del flujo ETL
RF9 — Detección de malas prácticas ETL
"""
import json

from app.models.gemini_client import call_secondary
from app.schemas.etl_schemas import ETLValidateRequest, ETLValidateResponse


async def validate_etl(req: ETLValidateRequest) -> ETLValidateResponse:
    prompt = f"""Analiza el siguiente proceso ETL y detecta problemas de calidad y malas prácticas:

```json
{json.dumps(req.proceso_etl, ensure_ascii=False, indent=2)}
```
"""
    resp = await call_secondary(prompt, "system_validator.txt")

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
