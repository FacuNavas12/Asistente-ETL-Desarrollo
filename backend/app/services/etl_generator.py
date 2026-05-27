"""
RF5 — Interpretar relaciones entre capas (origen → staging → DWH)
RF6 — Generar proceso ETL completo
RF7 — Sugerir steps concretos de Pentaho PDI
RF14 — Sugerir visualizaciones para Apache Superset
"""
import json

from app.models.gemini_client import call_main
from app.models.llm_base import LLMResponse
from app.schemas.etl_schemas import ETLRequest, ETLFromInferenceRequest, ETLGenerateResponse
from app.services.ktr_builder import build_ktr


def _build_prompt(req: ETLRequest) -> str:

    # Origen
    origen_txt = ""
    for t in req.origenTables:
        cols = "\n".join(
            f"    - {c.name} | tipo: {c.dataType}"
            + (f" | formato: {c.dataFormat}" if c.dataFormat else "")
            + f" | rol: {c.role}"
            + (f" | datos ejemplo: {', '.join(c.data[:5])}" if c.data else "")
            for c in t.columns
        )
        origen_txt += f"\n  Tabla: {t.tableName}\n{cols}\n"

    # Staging
    staging_txt = ""
    for t in req.stagingDef:
        origen_ref = f" (origen: {t.origenVinculado})" if t.origenVinculado else ""
        cols = "\n".join(
            (
                f"    - {c.origenColumna} → {c.nombre} ({c.tipo})"
                if c.origenColumna and c.origenColumna != c.nombre
                else f"    - {c.nombre} ({c.tipo})"
            ) + (
                f" | reglas: {', '.join(c.reglas)}" if c.reglas else ""
            ) + f" | dato no válido: {c.datoNoValido}"
            for c in t.columns
        )
        staging_txt += f"\n  Tabla: {t.tableName}{origen_ref}\n{cols}\n"

    # DWH
    dwh_txt = ""
    for t in req.dwhModel.tables:
        origen_ref = f" | origen: {t.origenVinculado}" if t.origenVinculado else ""
        cols = "\n".join(
            f"    - {c.origenColumna} → {c.nombre} ({c.tipo}){' [SK]' if c.esSurrogateKey else ''}"
            if c.origenColumna and c.origenColumna != c.nombre
            else f"    - {c.nombre} ({c.tipo}){' [SK]' if c.esSurrogateKey else ''}"
            for c in t.columnas
        )
        dwh_txt += f"\n  Tabla {t.tipo}: {t.nombre}{origen_ref}\n{cols}\n"

    reglas = req.reglasNegocio.strip() or "No se especificaron reglas de negocio adicionales."
    objetivo = req.descripcionObjetivo.strip() or "No especificado."

    return f"""## OBJETIVO DEL PROCESO ETL
{objetivo}

## ESQUEMA DE ORIGEN
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
    ktr_xml, ktr_filename = build_ktr(data.get("ktr", {}), process_name)
    return ETLGenerateResponse(
        proceso_etl=data["proceso_etl"],
        validaciones=data.get("validaciones", []),
        documentacion=data.get("documentacion", ""),
        advertencias_buenas_practicas=data.get("advertencias_buenas_practicas", []),
        dwh_sample=data.get("dwh_sample", {}),
        ktr_xml=ktr_xml,
        ktr_filename=ktr_filename,
        metadata={
            "modelo_usado": resp.model,
            "tokens_input": resp.input_tokens,
            "tokens_output": resp.output_tokens,
            "region_inferencia": resp.provider,
        },
    )


async def generate_etl(req: ETLRequest) -> ETLGenerateResponse:
    prompt = _build_prompt(req)
    resp = await call_main(prompt, "system_etl.txt")
    return _build_response(resp)


async def generate_etl_from_inference(req: ETLFromInferenceRequest) -> ETLGenerateResponse:
    """
    Genera el ETL completo a partir de estructuras STG y DWH ya inferidas por el modelo.
    El STG y DWH llegan como DDL SQL confirmado por el usuario en la pantalla de revisión.
    """
    origen_txt = ""
    for t in req.origenTables:
        cols = "\n".join(
            f"    - {c.name} | tipo: {c.dataType}"
            + (f" | formato: {c.dataFormat}" if c.dataFormat else "")
            + f" | rol: {c.role}"
            + (f" | datos ejemplo: {', '.join(c.data[:5])}" if c.data else "")
            for c in t.columns
        )
        origen_txt += f"\n  Tabla: {t.tableName}\n{cols}\n"

    objetivo = req.descripcionObjetivo.strip() or "No especificado."
    reglas = req.reglasNegocio.strip() or "No se especificaron reglas de negocio adicionales."

    prompt = f"""## OBJETIVO DEL PROCESO ETL
{objetivo}

## ESQUEMA DE ORIGEN
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
    resp = await call_main(prompt, "system_etl.txt")
    return _build_response(resp)
