"""
Servicio de inferencia automática de estructuras STG y DWH.

Recibe los 3 campos simplificados del usuario y genera:
- Definición DDL de la tabla Staging
- Modelo DDL del Data Warehouse
- Justificación de cada decisión de diseño

Soporta refinamiento iterativo: el usuario puede corregir en lenguaje natural
y el servicio regenera las estructuras manteniendo el historial de correcciones.
"""
import json
import logging

from app.models.gemini_client import call_main, get_region_label
from app.schemas.etl_schemas import InferRequest, RefineRequest, InferResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = "system_inference.txt"
_MAX_HISTORY_FULL = 10


def _sanitize_source(source: str) -> str:
    """Elimina el campo 'data' de cada columna del JSON de origen.
    Impide que valores de filas de producción lleguen al modelo (Ley 18.331)."""
    try:
        tables = json.loads(source)
        for table in tables:
            for col in table.get("columns", []):
                col.pop("data", None)
        return json.dumps(tables, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return source  # si el JSON es inválido, pasa tal cual sin bloquear


def _build_infer_prompt(req: InferRequest) -> str:
    return f"""A partir de la siguiente información, generá la definición de la tabla de Staging (STG) \
y el modelo de Data Warehouse (DWH) destino.

ESTRUCTURA DE ORIGEN:
{_sanitize_source(req.source_structure)}

DESCRIPCIÓN DEL PROCESO / OBJETIVO:
{req.process_description}

REGLAS DE NEGOCIO:
{req.business_rules}

Devuelve ÚNICAMENTE el JSON con la estructura de respuesta indicada. Sin texto adicional."""


def _build_refine_prompt(req: RefineRequest) -> str:
    if len(req.history) > _MAX_HISTORY_FULL:
        history_txt = (
            f"[{len(req.history)} iteraciones previas — resumen: "
            + "; ".join(h["correction"] for h in req.history[-3:])
            + "]"
        )
    else:
        history_txt = json.dumps(req.history, ensure_ascii=False, indent=2) if req.history else "Sin iteraciones previas."

    return f"""El usuario solicitó la siguiente corrección sobre las estructuras generadas:

CORRECCIÓN SOLICITADA:
{req.correction}

ESTRUCTURAS ACTUALES:
STG:
{req.current_stg}

DWH:
{req.current_dwh}

CONTEXTO ORIGINAL:
Estructura de origen: {_sanitize_source(req.source_structure)}
Descripción del proceso: {req.process_description}
Reglas de negocio: {req.business_rules}

HISTORIAL DE CORRECCIONES ANTERIORES:
{history_txt}

Aplicá la corrección solicitada y devolvé el JSON actualizado con las estructuras completas.
Respetá todas las correcciones anteriores del historial.
El campo iteration debe ser {len(req.history) + 2}.
Sin texto adicional."""


def _parse_response(raw: str, usage) -> InferResponse:
    data = json.loads(raw)

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
            "modelo_usado": settings.google_model_main,
            "tokens_input": usage.prompt_token_count or 0,
            "tokens_output": usage.candidates_token_count or 0,
            "region_inferencia": get_region_label(),
        },
    )


def infer_structures(request: InferRequest) -> InferResponse:
    prompt = _build_infer_prompt(request)
    raw, usage = call_main(prompt, _SYSTEM_PROMPT)

    try:
        return _parse_response(raw, usage)
    except (ValueError, KeyError) as e:
        logger.warning("Primer intento de inferencia inválido (%s), reintentando...", e)
        raw, usage = call_main(prompt, _SYSTEM_PROMPT)
        return _parse_response(raw, usage)


def refine_structures(request: RefineRequest) -> InferResponse:
    prompt = _build_refine_prompt(request)
    raw, usage = call_main(prompt, _SYSTEM_PROMPT)

    try:
        return _parse_response(raw, usage)
    except (ValueError, KeyError) as e:
        logger.warning("Primer intento de refinamiento inválido (%s), reintentando...", e)
        raw, usage = call_main(prompt, _SYSTEM_PROMPT)
        return _parse_response(raw, usage)
