from typing import Any, Dict

# Contrato de salida de la Parte 3 (auditoria/correccion de dwh_ddl contra
# dim_contracts): reusa el shape de Validacion (tipo/campo/mensaje) ya usado
# en ETL_OUTPUT_SCHEMA para "conflictos" en vez de inventar un shape nuevo —
# la capa de parseo (ddl_validation._parse_response) construye Validacion
# directamente desde estos items. sin_cambios es el unico campo sin
# equivalente previo: es la senal de si esta fase hace trabajo o solo mira.
_DDL_VALIDATION_REQUIRED = ["dwh_ddl", "sin_cambios", "cambios_aplicados", "conflictos"]

DDL_VALIDATION_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": _DDL_VALIDATION_REQUIRED,
    "propertyOrdering": _DDL_VALIDATION_REQUIRED,
    "properties": {
        "dwh_ddl": {
            "type": "string",
            "description": "DDL completo final. Identico al de entrada si sin_cambios=true.",
        },
        "sin_cambios": {
            "type": "boolean",
            "description": "true si el DDL de entrada ya cumplia el contrato e invariantes sin ajustes.",
        },
        "cambios_aplicados": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Un string por cada ajuste aplicado (formato '<tabla>: <que se agrego/corrigio> "
                "— motivo: <por que>'). Vacio si sin_cambios=true. Registrar TODO ajuste, incluso "
                "si parece menor — es la instrumentacion que permite notar si la inferencia dejo "
                "de emitir el contrato completo."
            ),
        },
        "conflictos": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tipo", "campo", "mensaje"],
                "properties": {
                    "tipo": {"type": "string", "enum": ["error", "warning", "info"]},
                    "campo": {"type": "string", "description": "Tabla o invariante (I2-I9) afectada."},
                    "mensaje": {"type": "string"},
                },
            },
            "description": (
                "Casos que NO se corrigieron porque hacerlo violaria una invariante o requeriria "
                "eliminar/renombrar/reducir algo existente. Nunca se auto-resuelven."
            ),
        },
    },
}
