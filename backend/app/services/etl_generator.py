"""
RF5 — Interpretar relaciones entre capas (origen → staging → DWH)
RF6 — Generar proceso ETL completo
RF7 — Sugerir steps concretos de Pentaho PDI
RF14 — Sugerir visualizaciones para Apache Superset
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.llm_base import BaseLLM, LLMResponse
from app.schemas.etl_schemas import ETLRequest, ETLFromInferenceRequest, ETLGenerateResponse
from app.services import context_builder
from app.services.ktr_builder import build_ktr
from app.services.lineage_builder import build_lineage


def _load_system(filename: str) -> str:
    return (Path(__file__).resolve().parent.parent.parent / "prompts" / filename).read_text(encoding="utf-8")


def _build_prompt(req: ETLRequest, origen_txt: str) -> str:
    staging_txt = ""
    for t in req.stagingDef:
        origen_ref = f" (origen: {t.origenVinculado})" if t.origenVinculado else ""
        cols = "\n".join(
            (
                f"    - {c.origenColumna} → {c.nombre} ({c.tipo})"
                if c.origenColumna and c.origenColumna != c.nombre
                else f"    - {c.nombre} ({c.tipo})"
            ) + (f" | reglas: {', '.join(c.reglas)}" if c.reglas else "")
            + f" | dato no válido: {c.datoNoValido}"
            for c in t.columns
        )
        staging_txt += f"\n  Tabla: {t.tableName}{origen_ref}\n{cols}\n"

    dwh_txt = ""
    for t in req.dwhModel.tables:
        origen_ref = f" | origen: {t.origenVinculado}" if t.origenVinculado else ""
        cols = "\n".join(
            (
                f"    - {c.origenColumna} → {c.nombre} ({c.tipo}){' [SK]' if c.esSurrogateKey else ''}"
                if c.origenColumna and c.origenColumna != c.nombre
                else f"    - {c.nombre} ({c.tipo}){' [SK]' if c.esSurrogateKey else ''}"
            )
            for c in t.columnas
        )
        dwh_txt += f"\n  Tabla {t.tipo}: {t.nombre}{origen_ref}\n{cols}\n"

    reglas  = req.reglasNegocio.strip() or "No se especificaron reglas de negocio adicionales."
    objetivo = req.descripcionObjetivo.strip() or "No especificado."

    return f"""## OBJETIVO DEL PROCESO ETL
{objetivo}

## ESQUEMA DE ORIGEN (perfilado — sin datos crudos)
{origen_txt}
## ESQUEMA DE STAGING
{staging_txt}
## MODELO DE DWH
{dwh_txt}
## REGLAS DE NEGOCIO

{reglas}

---

Genera el proceso ETL completo respetando estrictamente el objetivo indicado.
El mapeo "origen → nombre" indica que el campo se renombra entre capas; respetá los nombres destino exactos.
Aplica todas las reglas de limpieza definidas en cada columna de staging.
Verifica la consistencia de tipos y nombres entre las tres capas.
"""


def _build_response(resp: LLMResponse) -> ETLGenerateResponse:
    data = json.loads(resp.content)
    process_name = data.get("proceso_etl", {}).get("nombre", "")
    ktr_data = data.get("ktr", {})
    ktr_xml, ktr_filename = build_ktr(ktr_data, process_name)
    return ETLGenerateResponse(
        proceso_etl=data["proceso_etl"],
        validaciones=data.get("validaciones", []),
        documentacion=data.get("documentacion", ""),
        advertencias_buenas_practicas=data.get("advertencias_buenas_practicas", []),
        dwh_sample=data.get("dwh_sample", {}),
        ktr_xml=ktr_xml,
        ktr_filename=ktr_filename,
        lineage=build_lineage(ktr_data),
        metadata={
            "modelo_usado": resp.model,
            "tokens_input": resp.input_tokens,
            "tokens_output": resp.output_tokens,
            "region_inferencia": resp.provider,
        },
    )


async def generate_etl(
    req: ETLRequest,
    llm: BaseLLM,
    db: Optional[Session] = None,
) -> ETLGenerateResponse:
    ctx        = context_builder.build_model_context(req.origenTables, db)
    origen_txt = context_builder.format_model_context_for_prompt(ctx)
    prompt     = _build_prompt(req, origen_txt)
    resp       = await llm.complete(prompt, _load_system("system_etl.txt"))
    return _build_response(resp)


async def generate_etl_from_inference(
    req: ETLFromInferenceRequest,
    llm: BaseLLM,
    db: Optional[Session] = None,
) -> ETLGenerateResponse:
    ctx        = context_builder.build_model_context(req.origenTables, db)
    origen_txt = context_builder.format_model_context_for_prompt(ctx)
    objetivo   = req.descripcionObjetivo.strip() or "No especificado."
    reglas     = req.reglasNegocio.strip() or "No se especificaron reglas de negocio adicionales."

    prompt = f"""## OBJETIVO DEL PROCESO ETL
{objetivo}

## ESQUEMA DE ORIGEN (perfilado — sin datos crudos)
{origen_txt}
## STAGING (inferido y confirmado por el usuario)
{req.stg_definition}

## MODELO DWH (inferido y confirmado por el usuario)
{req.dwh_model}

## REGLAS DE NEGOCIO
{reglas}

---

Genera el proceso ETL completo respetando estrictamente el objetivo indicado.
Las estructuras STG y DWH ya fueron validadas por el usuario — usá exactamente esos nombres de tablas y columnas.
Verifica la consistencia de tipos y nombres entre las tres capas.
"""
    resp = await llm.complete(prompt, _load_system("system_etl.txt"))
    return _build_response(resp)
