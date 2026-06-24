"""
JSON Schema for the full ETL generation response.

Fields proceso_etl.steps[*].configuracion and ktr.steps[*].config are left
as {"type": "object"} without additionalProperties: false because their internal
structure varies by Pentaho step type — enforcing additionalProperties on them
would either require a massive oneOf discriminator or would reject valid configs.

dwh_sample maps table names (unknown at schema-definition time) to lists of row
dicts, so its keys cannot be enumerated — it also stays as {"type": "object"}.

All other objects have additionalProperties: false.
"""
from typing import Dict, Any

ETL_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "proceso_etl",
        "validaciones",
        "documentacion",
        "advertencias_buenas_practicas",
        "dwh_sample",
        "ktr",
    ],
    "properties": {
        "proceso_etl": {
            "type": "object",
            "additionalProperties": False,
            "required": ["nombre", "descripcion", "steps"],
            "properties": {
                "nombre": {"type": "string"},
                "descripcion": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "orden",
                            "tipo_step_pdi",
                            "nombre",
                            "descripcion",
                            "configuracion",
                            "justificacion",
                        ],
                        "properties": {
                            "orden": {"type": "integer"},
                            "tipo_step_pdi": {"type": "string"},
                            "nombre": {"type": "string"},
                            "descripcion": {"type": "string"},
                            # Free-form: varies by step type. No additionalProperties constraint.
                            "configuracion": {"type": "object"},
                            "justificacion": {"type": "string"},
                        },
                    },
                },
            },
        },
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
        "documentacion": {"type": "string"},
        "advertencias_buenas_practicas": {
            "type": "array",
            "items": {"type": "string"},
        },
        # Dynamic keys (table names) → cannot enumerate → no additionalProperties constraint.
        "dwh_sample": {"type": "object"},
        "ktr": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "description", "connections", "steps", "hops"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "connections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "host", "type", "database", "port", "username"],
                        "properties": {
                            "name": {"type": "string"},
                            "host": {"type": "string"},
                            "type": {"type": "string"},
                            "database": {"type": "string"},
                            "port": {"type": "integer"},
                            "username": {"type": "string"},
                        },
                    },
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "type", "config"],
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            # Free-form: varies by Pentaho step type.
                            "config": {"type": "object"},
                        },
                    },
                },
                "hops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["from", "to", "enabled"],
                        "properties": {
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "enabled": {"type": "boolean"},
                        },
                    },
                },
            },
        },
    },
}
