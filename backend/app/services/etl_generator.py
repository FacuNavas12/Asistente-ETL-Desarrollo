"""
RF5 — Interpretar relaciones entre capas (origen → staging → DWH)
RF6 — Generar proceso ETL completo
RF7 — Sugerir steps concretos de Pentaho PDI
RF14 — Sugerir visualizaciones para Apache Superset

Motor: Claude Sonnet 4.6
"""
import json

from app.models.gemini_client import call_main
from app.schemas.etl_schemas import ETLRequest, ETLGenerateResponse
from app.core.config import settings


def _build_prompt(req: ETLRequest) -> str:
    staging_cols = "\n".join(
        f"  - {c.nombre} ({c.tipo}) | regla: {c.regla} | dato no válido: {c.dato_no_valido}"
        for c in req.staging_def.columnas
    )

    dwh_tables = ""
    for t in req.dwh_model.tables:
        cols = "\n".join(
            f"    - {c.nombre} ({c.tipo}){' [SK]' if c.es_surrogate_key else ''}"
            for c in t.columnas
        )
        origen = f" | origen vinculado: {t.origen_vinculado}" if t.origen_vinculado else ""
        dwh_tables += f"\n  Tabla {t.tipo}: {t.nombre}{origen}\n{cols}\n"

    reglas = req.reglas_negocio.strip() if req.reglas_negocio.strip() else "No se especificaron reglas de negocio adicionales."

    return f"""## DESCRIPCIÓN DEL PROCESO

{req.origen_texto}

## ESQUEMA DE STAGING

Tabla: {req.staging_def.nombre_tabla}
Columnas:
{staging_cols}

## MODELO DE DWH
{dwh_tables}

## REGLAS DE NEGOCIO

{reglas}

---

Genera el proceso ETL completo para cargar desde la fuente descrita hacia el staging y luego hacia el DWH definido.
Aplica todas las reglas de negocio. Verifica la consistencia entre las tres capas.
"""


def generate_etl(req: ETLRequest) -> ETLGenerateResponse:
    prompt = _build_prompt(req)
    raw, usage = call_main(prompt, "system_etl.txt")

    data = json.loads(raw)

    return ETLGenerateResponse(
        proceso_etl=data["proceso_etl"],
        validaciones=data.get("validaciones", []),
        documentacion=data.get("documentacion", ""),
        advertencias_buenas_practicas=data.get("advertencias_buenas_practicas", []),
        metadata={
            "modelo_usado": settings.google_model_main,
            "tokens_input": usage.prompt_token_count or 0,
            "tokens_output": usage.candidates_token_count or 0,
            "region_inferencia": "google-cloud",
        },
    )
