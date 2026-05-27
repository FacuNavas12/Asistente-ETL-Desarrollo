"""
RF11 — Generación de documentación automática
RF12 — Explicación del flujo en lenguaje natural
RF13 — Estructuración de resultados para persistencia
"""
import json

from app.models.gemini_client import call_secondary
from app.schemas.etl_schemas import ETLDocumentRequest, ETLDocumentResponse

_DOCUMENT_SYSTEM = "system_validator.txt"


async def document_etl(req: ETLDocumentRequest) -> ETLDocumentResponse:
    prompt = f"""Genera documentación técnica en lenguaje natural para el siguiente proceso ETL.

La documentación debe:
1. Describir el flujo completo de forma que un desarrollador nuevo lo entienda
2. Explicar cada step en orden, qué hace y por qué existe
3. Mencionar las reglas de negocio aplicadas
4. Indicar los puntos de control de calidad del proceso

Responde con un objeto JSON con la siguiente estructura:
{{
  "documentacion": "string — documentación completa en lenguaje natural"
}}

Proceso ETL a documentar:

```json
{json.dumps(req.proceso_etl, ensure_ascii=False, indent=2)}
```
"""
    resp = await call_secondary(prompt, _DOCUMENT_SYSTEM)

    data = json.loads(resp.content)

    return ETLDocumentResponse(
        documentacion=data.get("documentacion", ""),
        metadata={
            "modelo_usado": resp.model,
            "tokens_input": resp.input_tokens,
            "tokens_output": resp.output_tokens,
            "region_inferencia": resp.provider,
        },
    )
