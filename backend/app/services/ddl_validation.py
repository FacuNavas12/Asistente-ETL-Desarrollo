"""
Parte 3 de la serie dim_contracts (ver structure_inferrer.py para la Parte 1 y
etl_generator.py para la Parte 2): tercera linea de defensa, no la primera.

La Parte 1 hizo que dim_contracts sobreviva la serializacion. La Parte 2 hizo
que la fase de generacion de steps lo consuma en vez de deducirlo por parseo
del DDL. Esta parte cubre lo que igual se escape: el DDL no cumple el contrato
que declara (columna faltante, indice parcial donde no debe, fila
"desconocido" con SK distinta a la que el contrato declara). Sin esto, el
step queda apuntando a algo que no existe -- PDI no falla al guardar el .ktr,
falla en runtime.

validate_and_correct_ddl() corre ANTES de que etl_generator arme los prompts
de KTR_2 (STG->DWH) -- el .ktr se construye contra el DDL final que sale de
aca, no contra el DDL crudo de la inferencia.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.models.llm_base import BaseLLM, LLMResponse
from app.schemas.etl_schemas import DdlValidationResponse, DimContract, MetadataResponse, Validacion
from app.schemas.llm_output_schemas import DDL_VALIDATION_OUTPUT_SCHEMA

_log = logging.getLogger(__name__)
_SYSTEM_PROMPT = "prompt_validacion_src.txt"


def _load_system(filename: str) -> str:
    return (Path(__file__).resolve().parent.parent.parent / "prompts" / filename).read_text(encoding="utf-8")


def _format_dim_contracts(dim_contracts: list[DimContract]) -> str:
    lines = []
    for c in dim_contracts:
        lines.append(
            f"- {c.table}: technical_key={c.technical_key}, version_field={c.version_field}, "
            f"date_from={c.date_from}, date_to={c.date_to}, natural_keys={list(c.natural_keys)}, "
            f"unknown_key_value={c.unknown_key_value}, scd_type={c.scd_type}"
        )
    return "\n".join(lines)


def _build_prompt(dwh_ddl: str, dim_contracts: list[DimContract]) -> str:
    return f"""## DDL A REVISAR
{dwh_ddl}

## CONTRATO DE DIMENSIONES (dim_contracts)
{_format_dim_contracts(dim_contracts)}

---
Audita el DDL contra el contrato y las invariantes. Devolve UNICAMENTE el JSON de la seccion SALIDA."""


def _parse_response(resp: LLMResponse) -> DdlValidationResponse:
    data = resp.json_data
    if data is None:
        raise ValueError("LLM returned no structured data — json_data is None")
    if "dwh_ddl" not in data:
        raise ValueError("La respuesta del modelo no contiene dwh_ddl.")

    return DdlValidationResponse(
        dwh_ddl=data["dwh_ddl"],
        sin_cambios=data.get("sin_cambios", False),
        cambios_aplicados=data.get("cambios_aplicados", []),
        conflictos=[Validacion(**c) for c in data.get("conflictos", [])],
        metadata=MetadataResponse(
            modelo_usado=resp.model,
            tokens_input=resp.input_tokens,
            tokens_output=resp.output_tokens,
            region_inferencia=resp.provider,
        ),
    )


async def validate_and_correct_ddl(
    dwh_ddl: str,
    dim_contracts: list[DimContract],
    llm: BaseLLM,
) -> DdlValidationResponse:
    """Sin dimensiones (dim_contracts vacio — modelo normalizado) no hay nada
    que auditar contra un contrato que no existe: devuelve el DDL sin tocar,
    sin gastar una llamada al modelo.

    ACOPLAMIENTO: este short-circuit asume que "dim_contracts vacio" siempre
    significa "modelo normalizado, sin dimensiones" -- nunca "el contrato se
    perdio en el camino". Esa distincion no se verifica aca: la hace
    etl_generator._dim_contracts_anomaly_warning() (compara contra dwh_ddl
    buscando tablas dim_*), en un archivo distinto y sin llamar a esta
    funcion. Si esa advertencia se saca en el futuro, este short-circuit
    queda ciego a un contrato perdido -- no hay redundancia entre las dos."""
    if not dim_contracts:
        return DdlValidationResponse(
            dwh_ddl=dwh_ddl,
            sin_cambios=True,
            cambios_aplicados=[],
            conflictos=[],
            metadata=MetadataResponse(
                modelo_usado="(sin dimensiones — no se llamó al modelo)",
                tokens_input=0, tokens_output=0, region_inferencia="local",
            ),
        )

    prompt = _build_prompt(dwh_ddl, dim_contracts)
    system = _load_system(_SYSTEM_PROMPT)
    resp = await llm.complete(prompt, system, schema=DDL_VALIDATION_OUTPUT_SCHEMA)
    result = _parse_response(resp)

    # R8: instrumentación, no solo red de contención — si esto empieza a
    # aplicar los mismos cambios en cada corrida, la señal es que la
    # inferencia (Parte 1) dejó de emitir el contrato completo.
    if result.sin_cambios:
        _log.info("validate_and_correct_ddl: sin cambios (%d dimension(es) auditadas)", len(dim_contracts))
    else:
        _log.info(
            "validate_and_correct_ddl: %d cambio(s) aplicado(s): %s",
            len(result.cambios_aplicados), result.cambios_aplicados,
        )
    for c in result.conflictos:
        _log.warning("validate_and_correct_ddl conflicto [%s] %s: %s", c.tipo, c.campo, c.mensaje)

    return result
