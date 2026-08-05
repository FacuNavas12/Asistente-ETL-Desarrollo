from typing import Any, Dict

VALIDATOR_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["validaciones", "advertencias_buenas_practicas"],
    "properties": {
        "validaciones": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tipo", "campo", "mensaje"],
                "properties": {
                    "tipo": {"type": "string", "enum": ["error", "warning", "info"]},
                    "campo": {"type": "string"},
                    "mensaje": {"type": "string"},
                },
            },
        },
        "advertencias_buenas_practicas": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}
