from typing import Any, Dict

INFERENCE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "stg_ddl",
        "dwh_ddl",
        "stg_rationale",
        "dwh_rationale",
        "iteration_count",
    ],
    "properties": {
        "stg_ddl": {"type": "string"},
        "dwh_ddl": {"type": "string"},
        "stg_rationale": {"type": "string"},
        "dwh_rationale": {"type": "string"},
        "iteration_count": {"type": "integer"},
    },
}
