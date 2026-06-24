from typing import Any, Dict

DOCUMENT_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["documentacion"],
    "properties": {
        "documentacion": {"type": "string"},
    },
}
