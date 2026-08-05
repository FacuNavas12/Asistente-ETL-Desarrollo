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

from app.domain.scd import ScdVerdict, classify_scd_candidates, detect_history_intent
from app.models.llm_base import BaseLLM, LLMResponse
from app.schemas.canonical import CanonicalSchema, CanonicalType
from app.schemas.etl_schemas import InferRequest, RefineRequest, InferResponse
from app.schemas.llm_output_schemas import INFERENCE_OUTPUT_SCHEMA
from app.services import context_builder

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT   = "system_inference.txt"
_MAX_HISTORY_FULL = 10


def _load_system(filename: str) -> str:
    return (Path(__file__).resolve().parent.parent.parent / "prompts" / filename).read_text(encoding="utf-8")


def _resolve_origin_schemas(source_structure: str, db: Optional[Session] = None) -> Optional[list[CanonicalSchema]]:
    """
    Parsea source_structure (JSON list of TablaOrigen) y resuelve el
    CanonicalSchema de cada tabla vía context_builder.resolve_canonical_schemas()
    — una sola resolución (incluye perfilado contra BD si aplica), compartida
    por _format_source_for_prompt() (texto whitelisteado) y
    _build_scd_precheck_block() (D37): sin esto, el pre-check SCD volvería a
    perfilar la misma tabla contra la BD por segunda vez en el mismo request.

    None si el parseo falla — el llamador cae a un fallback propio (texto
    whitelisteado sin schema, pre-check SCD ausente y declarado como tal).
    """
    from app.schemas.etl_schemas import TablaOrigen

    try:
        raw    = json.loads(source_structure)
        tables = [TablaOrigen.model_validate(t) for t in raw]
        return context_builder.resolve_canonical_schemas(tables, db=db)
    except Exception as exc:
        logger.warning("Could not parse source_structure: %s", exc)
        return None


def _format_source_for_prompt(schemas: Optional[list[CanonicalSchema]], source_structure: str) -> str:
    """Texto whitelisteado de la estructura de origen. Con `schemas` resuelto,
    usa el mismo camino que antes (canonical_to_model_context +
    format_model_context_for_prompt). Sin él, cae al fallback histórico: strip
    de 'data' crudo del JSON, nunca texto sin sanear."""
    if schemas is not None:
        from app.services.adapters.schema_to_context import canonical_to_model_context

        model_tables = []
        for schema in schemas:
            ctx = canonical_to_model_context([schema])
            model_tables.extend(ctx.source_tables)
        from app.schemas.context_schemas import ModelContext
        return context_builder.format_model_context_for_prompt(ModelContext(source_tables=model_tables))

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


# ─── SCD pre-check (D37) ──────────────────────────────────────────────────────
# Proyección CanonicalSchema -> primitivos que domain/scd.py exige (domain no
# puede importar Pydantic, R1). Vive acá, no en domain/, porque ES la traducción
# desde un DTO de transporte concreto — ver "Criterio de capas" en CLAUDE.md.

_CALENDAR_DATE_TYPES = (CanonicalType.DATE, CanonicalType.DATETIME)


_STRUCTURAL_KEY_SOURCES = {"database", "ddl"}


def _key_columns(schema: CanonicalSchema) -> list[str]:
    keys = set(schema.primary_key)
    for f in schema.fields:
        if f.is_primary_key or f.constraints.unique:
            keys.add(f.name)
    return sorted(keys)


def _key_columns_trusted(schema: CanonicalSchema) -> bool:
    """Regla 0 de classify_scd_candidates solo puede leer key_columns=[] como
    "confirmado que no hay clave" cuando el origen realmente resuelve PK/UNIQUE
    (BD vía db_adapter, DDL vía ddl_adapter). Formulario (_schema_from_columnas_
    origen, inferred_by="user") y CSV/Excel (frictionless_adapter, inferred_by=
    "frictionless") NUNCA declaran esos campos — ahí key_columns=[] es "no se
    sabe", no evidencia. Sin esta distinción, la regla 0 dispara sobre casi
    cualquier ETL armado a mano (ver comentario en domain/scd.py)."""
    return bool(schema.fields) and all(f.inferred_by in _STRUCTURAL_KEY_SOURCES for f in schema.fields)


def _build_scd_precheck_block(
    schemas: Optional[list[CanonicalSchema]],
    business_rules: str,
    process_goal: str,
) -> str:
    """Bloque determinista que entra al prompt de inferencia — ver
    system_inference.txt sección "SCD: CUANDO 1 Y CUANDO 2". `verdict=
    NO_HISTORY_POSSIBLE` es vinculante; la señal de proyecto (business_rules +
    process_goal) NO decide por sí sola qué dimensión versiona — eso queda
    como residuo de juicio del modelo (ver nota de alcance en domain/scd.py)."""
    if not schemas:
        return "(no disponible — no se pudo resolver el schema de origen; aplicar el criterio de ## SCD sin pre-check.)"

    lines: list[str] = []
    signal = detect_history_intent(f"{business_rules}\n{process_goal}")
    if signal.matched:
        compliance_note = (
            " — vocabulario de CUMPLIMIENTO NORMATIVO detectado: en ese caso SCD1 "
            "no es una preferencia, está prohibido; la dimensión que corresponda "
            "debe ir en SCD2 sin excepción."
            if signal.compliance else ""
        )
        lines.append(
            "SEÑAL DE PROYECTO: historial mencionado en reglas de negocio/objetivo — "
            f"frases detectadas: {', '.join(signal.matched_phrases)}.{compliance_note}\n"
            "  ALCANCE: aplica SOLO a las dimensiones que ese texto menciona, no a todas. "
            "Determiná cuáles. Una mención de \"carga histórica\" o \"datos históricos\" es "
            "volumen o alcance temporal del HECHO, no versionado de un atributo de dimensión."
        )

    for schema in schemas:
        key_cols = _key_columns(schema)
        col_names = [f.name for f in schema.fields]
        date_cols = [f.name for f in schema.fields if f.type in _CALENDAR_DATE_TYPES]
        distinct_counts = None
        row_count = None
        if schema.profile and schema.profile.column_profiles:
            distinct_counts = {p.name: p.distinct_count for p in schema.profile.column_profiles}
            row_count = schema.profile.row_count_estimate
        declared_intent = None
        if schema.semantics and schema.semantics.dwh_intent:
            declared_intent = schema.semantics.dwh_intent.scd_type

        precheck = classify_scd_candidates(
            table_name=schema.source_name,
            column_names=col_names,
            key_columns=key_cols,
            key_columns_trusted=_key_columns_trusted(schema),
            date_type_columns=date_cols,
            distinct_counts=distinct_counts,
            row_count_estimate=row_count,
            declared_intent=declared_intent,
        )

        if precheck.verdict == ScdVerdict.NO_HISTORY_POSSIBLE:
            lines.append(
                f"- {precheck.table}: verdict=NO_HISTORY_POSSIBLE, scd_type_forzado={precheck.forced_scd_type}, "
                f"razon={precheck.reason}"
            )
        elif precheck.verdict == ScdVerdict.HISTORY_DECLARED:
            lines.append(
                f"- {precheck.table}: verdict=HISTORY_DECLARED, evidencia={list(precheck.evidence)}, "
                f"candidatos_scd2={list(precheck.scd2_candidates)}, razon={precheck.reason}"
            )
        else:
            lines.append(
                f"- {precheck.table}: verdict=UNDECIDED, atributos_mutables={list(precheck.mutable_attributes)}, "
                f"candidatos_scd2={list(precheck.scd2_candidates)}, razon={precheck.reason}"
            )

    return "\n".join(lines)


def _build_infer_prompt(req: InferRequest, db: Optional[Session] = None) -> str:
    schemas = _resolve_origin_schemas(req.source_schema_json, db)
    origen_safe = _format_source_for_prompt(schemas, req.source_schema_json)
    scd_precheck = _build_scd_precheck_block(schemas, req.business_rules, req.process_goal)
    return f"""A partir de la siguiente información, generá la definición de la tabla de Staging (STG) \
y el modelo de Data Warehouse (DWH) destino.

ESTRUCTURA DE ORIGEN:
{origen_safe}

DESCRIPCIÓN DEL PROCESO / OBJETIVO:
{req.process_goal}

REGLAS DE NEGOCIO:
{req.business_rules}

## PRE-CHECK SCD (determinista, calculado por el backend)
VINCULANTE donde una línea diga verdict=NO_HISTORY_POSSIBLE — no podés emitir scd_type=2 ahí, ni con justificación.
{scd_precheck}

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
            f"natural_keys={list(c.natural_keys)}, unknown_key_value={c.unknown_key_value}, "
            f"scd_rationale={c.scd_rationale!r}"
        )
    return "\n".join(lines)


def _build_refine_prompt(req: RefineRequest, db: Optional[Session] = None) -> str:
    schemas = _resolve_origin_schemas(req.source_schema_json, db)
    origen_safe = _format_source_for_prompt(schemas, req.source_schema_json)
    scd_precheck = _build_scd_precheck_block(schemas, req.business_rules, req.process_goal)

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

## PRE-CHECK SCD (determinista, calculado por el backend)
VINCULANTE donde una línea diga verdict=NO_HISTORY_POSSIBLE — no podés emitir scd_type=2 ahí, ni con justificación.
Si el pre-check contradice un scd_type ya preservado del contrato anterior, es un cambio rompiente:
declaralo en assumptions con el prefijo "CONTRATO MODIFICADO", igual que cualquier otro cambio de contrato.
{scd_precheck}

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
