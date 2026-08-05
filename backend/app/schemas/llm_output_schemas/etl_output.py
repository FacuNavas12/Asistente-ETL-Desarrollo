"""
JSON Schema for the full ETL generation response.

ktr.steps[*].config is left as {"type": "string"} (a JSON string the builder
parses with json.loads()) instead of {"type": "object"} because its internal
structure varies by Pentaho step type — enforcing additionalProperties on an
object would either require a massive oneOf discriminator or would reject
valid configs. See D18 in docs/refactor/02-decisiones.md for why the object
form was proposed and shelved.

dwh_sample maps table names (unknown at schema-definition time) to lists of row
dicts, so its keys cannot be enumerated — it stays as {"type": "object"}.

All other objects have additionalProperties: false.
"""
from typing import Dict, Any

ETL_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "proceso_etl",
        "validaciones",
        "advertencias_buenas_practicas",
        "ktr",
        "dwh_sample",
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
                        "required": ["orden", "tipo_step_pdi", "nombre", "descripcion"],
                        "properties": {
                            "orden": {"type": "integer"},
                            "tipo_step_pdi": {"type": "string"},
                            "nombre": {"type": "string"},
                            "descripcion": {"type": "string"},
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
        "advertencias_buenas_practicas": {
            "type": "array",
            "items": {"type": "string"},
        },
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
                            # String so Gemini structured-output can populate it freely.
                            # The builder parses it with json.loads().
                            "config": {
                                "type": "string",
                                "description": (
                                    "JSON string with the fields specific to THIS step's type — "
                                    "never reuse the same shape across different step types. "
                                    "See the 'Configuraciones válidas por tipo de step' section in the "
                                    "system prompt for the exact required keys per type (e.g. TableInput "
                                    "needs 'sql'+'connection'; WriteToLog needs 'message'; GroupBy needs "
                                    "'group_fields'+'aggregates'; MergeJoin needs "
                                    "'step1'+'step2'+'keys1'+'keys2'; Constant needs 'fields' with "
                                    "'value'). NEVER return '{}', and NEVER default to "
                                    "{'connection','table','fields'} regardless of type."
                                ),
                            },
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
        "dwh_sample": {
            "type": "object",
            "description": (
                "Una fila de ejemplo por cada tabla del DWH (dim_* y fact_*). "
                "Clave = nombre exacto de la tabla en minúsculas. "
                "Valor = array con UN objeto: claves = nombres de columna en minúsculas, "
                "valores = ejemplos del tipo correcto "
                "(string para VARCHAR, número para INTEGER/NUMERIC, "
                "true/false para BOOLEAN, '2024-01-15' para DATE). "
                "NO incluir tablas staging (stg_*)."
            ),
            "additionalProperties": {
                "type": "array",
                "items": {"type": "object"},
            },
        },
    },
}
