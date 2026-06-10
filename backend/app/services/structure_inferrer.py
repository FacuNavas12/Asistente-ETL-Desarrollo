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
    origen_safe = _safe_format_source(req.source_structure, db)
    return f"""A partir de la siguiente información, generá la definición de la tabla de Staging (STG) \
y el modelo de Data Warehouse (DWH) destino.

ESTRUCTURA DE ORIGEN:
{origen_safe}

DESCRIPCIÓN DEL PROCESO / OBJETIVO:
{req.process_description}

REGLAS DE NEGOCIO:
{req.business_rules}

Devuelve ÚNICAMENTE el JSON con la estructura de respuesta indicada. Sin texto adicional."""


def _build_refine_prompt(req: RefineRequest, db: Optional[Session] = None) -> str:
    origen_safe = _safe_format_source(req.source_structure, db)

    if len(req.history) > _MAX_HISTORY_FULL:
        history_txt = (
            f"[{len(req.history)} iteraciones previas — resumen: "
            + "; ".join(h["correction"] for h in req.history[-3:])
            + "]"
        )
    else:
        history_txt = (
            json.dumps(req.history, ensure_ascii=False, indent=2)
            if req.history else "Sin iteraciones previas."
        )

    return f"""El usuario solicitó la siguiente corrección sobre las estructuras generadas:

CORRECCIÓN SOLICITADA:
{req.correction}

ESTRUCTURAS ACTUALES:
STG:
{req.current_stg}

DWH:
{req.current_dwh}

CONTEXTO ORIGINAL:
Estructura de origen: {origen_safe}
Descripción del proceso: {req.process_description}
Reglas de negocio: {req.business_rules}

HISTORIAL DE CORRECCIONES ANTERIORES:
{history_txt}

Aplicá la corrección solicitada y devolvé el JSON actualizado con las estructuras completas.
Respetá todas las correcciones anteriores del historial.
El campo iteration debe ser {len(req.history) + 2}.
Sin texto adicional."""


def _parse_response(resp: LLMResponse) -> InferResponse:
    data = json.loads(resp.content)

    if "stg_definition" not in data or "dwh_model" not in data:
        raise ValueError("La respuesta del modelo no contiene stg_definition o dwh_model.")

    for field in ("stg_definition", "dwh_model"):
        val = data[field]
        if not isinstance(val, str) or "CREATE TABLE" not in val.upper():
            raise ValueError(f"El campo '{field}' no contiene un DDL válido (falta CREATE TABLE).")

    return InferResponse(
        stg_definition=data["stg_definition"],
        dwh_model=data["dwh_model"],
        stg_rationale=data.get("stg_rationale", ""),
        dwh_rationale=data.get("dwh_rationale", ""),
        iteration=data.get("iteration", 1),
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
    resp   = await llm.complete(prompt, system)
    try:
        return _parse_response(resp)
    except (ValueError, KeyError) as e:
        logger.warning("Primer intento de inferencia inválido (%s), reintentando...", e)
        resp = await llm.complete(prompt, system)
        return _parse_response(resp)


async def refine_structures(request: RefineRequest, llm: BaseLLM, db: Optional[Session] = None) -> InferResponse:
    prompt = _build_refine_prompt(request, db)
    system = _load_system(_SYSTEM_PROMPT)
    resp   = await llm.complete(prompt, system)
    try:
        return _parse_response(resp)
    except (ValueError, KeyError) as e:
        logger.warning("Primer intento de refinamiento inválido (%s), reintentando...", e)
        resp = await llm.complete(prompt, system)
        return _parse_response(resp)
