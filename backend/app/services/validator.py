"""
RF8 — Verificación de calidad del flujo ETL
RF9 — Detección de malas prácticas ETL

Motor: Claude Haiku 3.5
"""
import json

from app.models.gemini_client import call_secondary, get_region_label
from app.schemas.etl_schemas import ETLValidateRequest, ETLValidateResponse
from app.core.config import settings


def validate_etl(req: ETLValidateRequest) -> ETLValidateResponse:
    prompt = f"""Analiza el siguiente proceso ETL y detecta problemas de calidad y malas prácticas:

```json
{json.dumps(req.proceso_etl, ensure_ascii=False, indent=2)}
```
"""
    raw, usage = call_secondary(prompt, "system_validator.txt")

    data = json.loads(raw)

    return ETLValidateResponse(
        validaciones=data.get("validaciones", []),
        advertencias_buenas_practicas=data.get("advertencias_buenas_practicas", []),
        metadata={
            "modelo_usado": settings.google_model_secondary,
            "tokens_input": usage.prompt_token_count or 0,
            "tokens_output": usage.candidates_token_count or 0,
            "region_inferencia": get_region_label(),
        },
    )
