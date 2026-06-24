from typing import Any, Dict

INFERENCE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "stg_definition",
        "dwh_model",
        "stg_rationale",
        "dwh_rationale",
        "iteration",
    ],
    "properties": {
        "stg_definition": {"type": "string"},
        "dwh_model": {"type": "string"},
        "stg_rationale": {"type": "string"},
        "dwh_rationale": {"type": "string"},
        "iteration": {"type": "integer"},
    },
}
