from typing import Any, Dict

# dim_contracts reemplaza el parseo de SQL en la fase de generación de steps:
# cada elemento nombra explícitamente qué columna del DDL cumple cada rol del
# contrato "Dimension lookup/update" de Pentaho (technical_key, version_field,
# date_from, date_to, natural_keys, unknown_key_value). Sin esto, esa fase
# tendría que adivinar por convención de nombres — el bug original que esto
# reemplaza.
_DIM_CONTRACT_REQUIRED = [
    "table",
    "scd_type",
    "technical_key",
    "version_field",
    "date_from",
    "date_to",
    "natural_keys",
    "unknown_key_value",
    "attributes_scd1",
    "attributes_scd2",
]

_DIM_CONTRACT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": _DIM_CONTRACT_REQUIRED,
    # Orden estable de generación (extensión Gemini; ignorada por Anthropic).
    "propertyOrdering": _DIM_CONTRACT_REQUIRED,
    "properties": {
        "table": {"type": "string"},
        "scd_type": {
            "type": "integer",
            "description": (
                "0 = dimensión sin historial (junk/degenerada, SCD0), "
                "1 = SCD1 (sobreescribe sin versionar), "
                "2 = SCD2 (versiona con version_field/date_from/date_to). "
                "Únicos valores válidos: 0, 1 o 2."
            ),
        },
        "technical_key": {"type": "string", "description": "Columna surrogate key, ej. sk_cliente."},
        "version_field": {"type": "string", "description": "Columna 'version' del contrato Dimension lookup/update."},
        "date_from": {"type": "string", "description": "Columna 'fecha_inicio' del contrato."},
        "date_to": {"type": "string", "description": "Columna 'fecha_fin' del contrato."},
        "natural_keys": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Clave(s) natural(es) de origen usadas por el lookup (compuesta si el grano lo exige).",
        },
        "unknown_key_value": {
            "type": "integer",
            "description": (
                "Valor de technical_key sembrado para la fila 'desconocido' de esta dimensión. "
                "El step Dimension lookup/update de PDI usa 0 por defecto — si el DDL siembra "
                "otro valor, este campo debe coincidir exactamente o el generador de steps configura "
                "un default de FK que no encuentra ninguna fila."
            ),
        },
        "attributes_scd1": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Atributos que se sobreescriben sin versionar. Vacío si no aplica.",
        },
        "attributes_scd2": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Atributos versionados por SCD2. Vacío si no aplica o si scd_type != 2.",
        },
    },
}

_INFERENCE_REQUIRED = [
    "stg_ddl",
    "dwh_ddl",
    "dim_contracts",
    "assumptions",
    "stg_rationale",
    "dwh_rationale",
    "iteration_count",
]

INFERENCE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": _INFERENCE_REQUIRED,
    # Orden estable de generación (extensión Gemini; ignorada por Anthropic).
    "propertyOrdering": _INFERENCE_REQUIRED,
    "properties": {
        "stg_ddl": {"type": "string"},
        "dwh_ddl": {"type": "string"},
        "dim_contracts": {
            "type": "array",
            "items": _DIM_CONTRACT_SCHEMA,
            "description": (
                "Un contrato por cada dimensión del DWH — consumido por la fase de generación de "
                "steps, no lo omitas ni lo dejes vacío si el modelo tiene dimensiones. Array vacío "
                "solo si el modelo es normalizado (no hay dimensiones)."
            ),
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Suposiciones tomadas ante entrada ambigua o incompleta. Vacío si no hubo ninguna.",
        },
        "stg_rationale": {"type": "string"},
        "dwh_rationale": {"type": "string"},
        "iteration_count": {"type": "integer"},
    },
}
