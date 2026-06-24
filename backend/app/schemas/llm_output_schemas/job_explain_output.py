from typing import Any, Dict

JOB_EXPLAIN_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["explanation"],
    "properties": {
        "explanation": {"type": "string"},
    },
}
