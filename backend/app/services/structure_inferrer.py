"""
Servicio de inferencia automática de estructuras STG y DWH.

Recibe los 3 campos simplificados del usuario y genera:
- Definición DDL de la tabla Staging
- Modelo DDL del Data Warehouse
- Justificación de cada decisión de diseño

Soporta refinamiento iterativo: el usuario puede corregir en lenguaje natural
y el servicio regenera las estructuras manteniendo el historial de correcciones.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.llm_base import BaseLLM, LLMResponse
from app.schemas.etl_schemas import InferRequest, RefineRequest, InferResponse
from app.schemas.llm_output_schemas import INFERENCE_OUTPUT_SCHEMA
from app.services import context_builder

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT   = "system_inference.txt"
_MAX_HISTORY_FULL = 10


def _load_system(filename: str) -> str:
    return (Path(__file__).resolve().parent.parent.parent / "prompts" / filename).read_text(encoding="utf-8")


def _safe_format_source(source_structure: str, db: Optional[Session] = None) -> str:
    """
    Parse source_structure (JSON list of TablaOrigen) and return its
    format_model_context_for_prompt() representation.

    If parsing fails, strip all 'data' fields from the raw JSON to prevent
    raw values from reaching the prompt, then include the schema-only JSON.
    """
    from app.schemas.etl_schemas import TablaOrigen

    try:
        raw    = json.loads(source_structure)
        tables = [TablaOrigen.model_validate(t) for t in raw]
        ctx    = context_builder.build_model_context(tables, db=db)
        return context_builder.format_model_context_for_prompt(ctx)
    except Exception as exc:
        logger.warning("Could not parse source_structure for whitelisting: %s", exc)

    # Fallback: strip raw data values from the JSON, keep schema metadata only.
    try:
        parsed = json.loads(source_structure)
        if isinstance(parsed, list):
            for tabla in parsed:
                if not isinstance(tabla, dict):
                    continue
                for col in tabla.get("columns", []):
                    if isinstance(col, dict):
                        col.pop("data", None)
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception:
        return "[estructura de origen no disponible]"


def _build_infer_prompt(req: InferRequest, db: Optional[Session] = None) -> str:
    origen_safe = _safe_format_source(req.source_schema_json, db)
    return f"""A partir de la siguiente información, generá la definición de la tabla de Staging (STG) \
y el modelo de Data Warehouse (DWH) destino.

ESTRUCTURA DE ORIGEN:
{origen_safe}

DESCRIPCIÓN DEL PROCESO / OBJETIVO:
{req.process_goal}

REGLAS DE NEGOCIO:
{req.business_rules}

Devuelve ÚNICAMENTE el JSON con la estructura de respuesta indicada. Sin texto adicional."""


def _format_previous_dim_contracts(dim_contracts: list) -> str:
    """Parte 4 (bloque B): el contrato previo se muestra para que la
    inferencia lo preserve por default — no para que lo derive de nuevo."""
    if not dim_contracts:
        return "(sin dimensiones en la iteración anterior)"
    lines = []
    for c in dim_contracts:
        lines.append(
            f"- {c.table}: scd_type={c.scd_type}, technical_key={c.technical_key}, "
            f"version_field={c.version_field}, date_from={c.date_from}, date_to={c.date_to}, "
            f"natural_keys={list(c.natural_keys)}, unknown_key_value={c.unknown_key_value}"
        )
    return "\n".join(lines)


def _build_refine_prompt(req: RefineRequest, db: Optional[Session] = None) -> str:
    origen_safe = _safe_format_source(req.source_schema_json, db)

    if len(req.correction_history) > _MAX_HISTORY_FULL:
        history_txt = (
            f"[{len(req.correction_history)} iteraciones previas — resumen: "
            + "; ".join(h["correction"] for h in req.correction_history[-3:])
            + "]"
        )
    else:
        history_txt = (
            json.dumps(req.correction_history, ensure_ascii=False, indent=2)
            if req.correction_history else "Sin iteraciones previas."
        )

    return f"""El usuario solicitó la siguiente corrección sobre las estructuras generadas:

CORRECCIÓN SOLICITADA:
{req.correction}

ESTRUCTURAS ACTUALES:
STG:
{req.previous_stg}

DWH:
{req.previous_dwh}

CONTRATO DE DIMENSIONES ANTERIOR (dim_contracts — preservalo tal cual salvo que esta corrección
cuestione específicamente esa dimensión; preservar es el default, no el resultado de una decisión):
{_format_previous_dim_contracts(req.previous_dim_contracts)}

CONTEXTO ORIGINAL:
Estructura de origen: {origen_safe}
Descripción del proceso: {req.process_goal}
Reglas de negocio: {req.business_rules}

HISTORIAL DE CORRECCIONES ANTERIORES:
{history_txt}

Aplicá la corrección solicitada y devolvé el JSON actualizado con las estructuras completas.
Respetá todas las correcciones anteriores del historial.
Si esta corrección cambia scd_type, technical_key, version_field, date_from, date_to, natural_keys
o unknown_key_value de una dimensión que ya existía en el contrato anterior, es un cambio rompiente:
declaralo en assumptions con el prefijo "CONTRATO MODIFICADO: <tabla> — <qué cambió>". Sin esa marca,
el cambio es indistinguible de una preservación normal y los steps armados contra el contrato viejo
no se regeneran cuando deberían.
El campo iteration_count debe ser {len(req.correction_history) + 2}.
Sin texto adicional."""


def _parse_response(resp: LLMResponse) -> InferResponse:
    data = resp.json_data
    if data is None:
        raise ValueError("LLM returned no structured data — json_data is None")

    if "stg_ddl" not in data or "dwh_ddl" not in data:
        raise ValueError("La respuesta del modelo no contiene stg_ddl o dwh_ddl.")

    for field in ("stg_ddl", "dwh_ddl"):
        val = data[field]
        if not isinstance(val, str) or "CREATE TABLE" not in val.upper():
            raise ValueError(f"El campo '{field}' no contiene un DDL válido (falta CREATE TABLE).")

    return InferResponse(
        stg_ddl=data["stg_ddl"],
        dwh_ddl=data["dwh_ddl"],
        dim_contracts=data.get("dim_contracts", []),
        assumptions=data.get("assumptions", []),
        stg_rationale=data.get("stg_rationale", ""),
        dwh_rationale=data.get("dwh_rationale", ""),
        iteration_count=data.get("iteration_count", 1),
        metadata={
            "modelo_usado": resp.model,
            "tokens_input": resp.input_tokens,
            "tokens_output": resp.output_tokens,
            "region_inferencia": resp.provider,
        },
    )


async def infer_structures(request: InferRequest, llm: BaseLLM, db: Optional[Session] = None) -> InferResponse:
    prompt = _build_infer_prompt(request, db)
    system = _load_system(_SYSTEM_PROMPT)
    resp   = await llm.complete(prompt, system, schema=INFERENCE_OUTPUT_SCHEMA)
    return _parse_response(resp)


async def refine_structures(request: RefineRequest, llm: BaseLLM, db: Optional[Session] = None) -> InferResponse:
    prompt = _build_refine_prompt(request, db)
    system = _load_system(_SYSTEM_PROMPT)
    resp   = await llm.complete(prompt, system, schema=INFERENCE_OUTPUT_SCHEMA)
    return _parse_response(resp)
