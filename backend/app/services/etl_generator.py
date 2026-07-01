"""
RF5 — Interpretar relaciones entre capas (origen → staging → DWH)
RF6 — Generar proceso ETL completo
RF7 — Sugerir steps concretos de Pentaho PDI
RF14 — Sugerir visualizaciones para Apache Superset
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from app.models.llm_base import BaseLLM, LLMResponse
from app.schemas.etl_schemas import ETLRequest, ETLFromInferenceRequest, ETLGenerateResponse
from app.schemas.llm_output_schemas import ETL_OUTPUT_SCHEMA
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

Antes de escribir el objeto `ktr`, determiná en orden:
**Etapa 1 — Diseño del grafo:** listá mentalmente todos los steps necesarios (nombre, tipo) y sus conexiones (hops) para ESTE proceso específico, sin entrar en configs internas. Verificá grafo completo: ningún step aislado.
**Etapa 2 — Configuración interna:** solo después del grafo completo, poblá el `config` de cada step en orden topológico (entrada → salida).
No mezcles las etapas — configura solo cuando el grafo esté cerrado.
"""


def _build_response(resp: LLMResponse) -> ETLGenerateResponse:
    # json_data is always populated when schema= was passed to llm.complete()
    data = resp.json_data
    if data is None:
        _log.error("LLM returned no json_data. raw=%r", (resp.content or "")[:200])
        raise ValueError("LLM returned no structured data — cannot parse ETL response")

    process_name = data.get("proceso_etl", {}).get("nombre", "")
    ktr_data = data.get("ktr", {})

    # Diagnóstico de causa raíz: mostrar los primeros steps del JSON crudo del modelo
    import json as _json
    _log.info("=== KTR JSON CRUDO (primeros 3 steps) ===")
    for s in ktr_data.get("steps", [])[:3]:
        _log.info("STEP_RAW: %s", _json.dumps(s, ensure_ascii=False))

    # Diagnóstico: loggear config de cada step antes de construir el KTR
    import json as _json2
    for s in ktr_data.get("steps", []):
        raw = s.get("config", {})
        if isinstance(raw, str):
            try:
                cfg = _json2.loads(raw) if raw.strip() else {}
            except Exception:
                cfg = {}
        else:
            cfg = raw or {}
        _log.info(
            "KTR_DIAG step='%s' type='%s' cfg_type=%s table=%r returnfield=%r step1=%r step2=%r cfg_keys=%s",
            s.get("name"), s.get("type"), type(raw).__name__,
            cfg.get("table") or cfg.get("target_table") or cfg.get("table_name"),
            cfg.get("returnfield") or cfg.get("return_field"),
            cfg.get("step1") or cfg.get("reference"),
            cfg.get("step2") or cfg.get("compare"),
            list(cfg.keys()),
        )

    ktr_xml, ktr_filename = build_ktr(ktr_data, process_name)
    return ETLGenerateResponse(
        proceso_etl=data["proceso_etl"],
        validaciones=data.get("validaciones", []),
        documentacion=data.get("documentacion", ""),
        advertencias_buenas_practicas=data.get("advertencias_buenas_practicas", []),
        dwh_sample={},
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
    resp       = await llm.complete(prompt, _load_system("system_etl.txt"), schema=ETL_OUTPUT_SCHEMA)
    return _build_response(resp)


async def generate_etl_from_inference(
    req: ETLFromInferenceRequest,
    llm: BaseLLM,
    db: Optional[Session] = None,
    on_llm_done=None,
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

Antes de escribir el objeto `ktr`, determiná en orden:
**Etapa 1 — Diseño del grafo:** listá mentalmente todos los steps necesarios (nombre, tipo) y sus conexiones (hops) para ESTE proceso específico, sin entrar en configs internas. Verificá grafo completo: ningún step aislado.
**Etapa 2 — Configuración interna:** solo después del grafo completo, poblá el `config` de cada step en orden topológico (entrada → salida).
No mezcles las etapas — configura solo cuando el grafo esté cerrado.
"""
    resp = await llm.complete(prompt, _load_system("system_etl.txt"), schema=ETL_OUTPUT_SCHEMA)
    if on_llm_done is not None:
        await on_llm_done()
    return _build_response(resp)
