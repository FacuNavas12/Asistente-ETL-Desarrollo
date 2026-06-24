from typing import Any, Dict

JOB_PLAN_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "job_name",
        "description",
        "execution_order",
        "variables",
        "checkpoints",
        "notifications",
        "loops",
        "error_handling",
        "overall_rationale",
    ],
    "properties": {
        "job_name": {"type": "string"},
        "description": {"type": "string"},
        "execution_order": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["order", "transformation_name", "filename", "rationale"],
                "properties": {
                    "order": {"type": "integer"},
                    "transformation_name": {"type": "string"},
                    "filename": {"type": "string"},
                    "rationale": {"type": "string"},
                },
            },
        },
        "variables": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "value", "scope", "description"],
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "scope": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "checkpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["after_transformation", "type", "description"],
                "properties": {
                    "after_transformation": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "notifications": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["trigger", "type", "message"],
                "properties": {
                    "trigger": {"type": "string"},
                    "type": {"type": "string"},
                    "message": {"type": "string"},
                },
            },
        },
        "loops": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["transformation_name", "condition", "max_iterations"],
                "properties": {
                    "transformation_name": {"type": "string"},
                    "condition": {"type": "string"},
                    "max_iterations": {"type": "integer"},
                },
            },
        },
        "error_handling": {"type": "string"},
        "overall_rationale": {"type": "string"},
    },
}
