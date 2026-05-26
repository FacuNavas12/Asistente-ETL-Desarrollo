"""
Servicio de análisis y generación de Jobs PDI (.kjb).

Flujo:
1. analyze_job  — parsea los .ktr subidos, extrae metadata, llama a Gemini para
                  inferir el orden lógico y estructura del job. Guarda los archivos
                  en un directorio temporal con un session_id único.
2. refine_job   — aplica una corrección en lenguaje natural manteniendo historial.
                  Reutiliza el session_id; no requiere re-subida de archivos.
3. generate_job — toma el JobPlan confirmado, construye el XML .kjb y genera la
                  explicación en lenguaje natural. Limpia los archivos temporales.
"""
import json
import logging
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET

from fastapi import UploadFile

from app.core.config import settings
from app.models.gemini_client import call_main, call_secondary
from app.schemas.job_schemas import (
    JobAnalyzeResponse,
    JobEntry,
    JobGenerateResponse,
    JobPlan,
    JobRefineRequest,
    KTRMetadata,
)

logger = logging.getLogger(__name__)

_SYSTEM_ANALYZE = "system_job.txt"
_SYSTEM_EXPLAIN = "system_job_kjb.txt"
_MAX_HISTORY_FULL = 10
_TEMP_ROOT = Path(tempfile.gettempdir()) / "etl_sessions"
_TEMP_ROOT.mkdir(exist_ok=True)


# ─── Temp file management ─────────────────────────────────────────────────────

def _session_dir(session_id: str) -> Path:
    return _TEMP_ROOT / session_id


def _save_ktr_files(files_content: Dict[str, str]) -> str:
    session_id = str(uuid.uuid4())
    sess_dir = _session_dir(session_id)
    sess_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in files_content.items():
        (sess_dir / filename).write_text(content, encoding="utf-8")
    return session_id


def _cleanup_session(session_id: str) -> None:
    sess_dir = _session_dir(session_id)
    if sess_dir.exists():
        shutil.rmtree(sess_dir, ignore_errors=True)


# ─── KTR parsing ──────────────────────────────────────────────────────────────

def parse_ktr_metadata(filename: str, xml_content: str) -> KTRMetadata:
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        raise ValueError(f"XML inválido en {filename}: {e}")

    def _text(path: str, default: str = "") -> str:
        el = root.find(path)
        return el.text.strip() if el is not None and el.text else default

    transformation_name = _text("./info/name") or _text("./name") or filename
    description = _text("./info/description") or _text("./description") or ""

    step_types = list({
        el.text.strip()
        for el in root.findall(".//step/type")
        if el.text
    })

    input_conns = list({
        el.text.strip()
        for step in root.findall(".//step")
        if step.findtext("type", "") in ("TableInput", "DBLookup")
        for el in step.findall("connection")
        if el.text
    })
    output_conns = list({
        el.text.strip()
        for step in root.findall(".//step")
        if step.findtext("type", "") in ("TableOutput", "TableInput")
        for el in step.findall("connection")
        if el.text and el.text.strip() not in input_conns
    })

    name_lower = (transformation_name + " " + description).lower()
    has_staging = any(k in name_lower for k in ("stg", "staging"))
    has_dwh = any(k in name_lower for k in ("dwh", "warehouse", "dim_", "fact_", "dimension"))

    return KTRMetadata(
        filename=filename,
        transformation_name=transformation_name,
        description=description,
        step_types=step_types,
        input_connections=input_conns,
        output_connections=output_conns,
        has_staging=has_staging,
        has_dwh=has_dwh,
        raw_content=xml_content,
    )


# ─── Prompt builders ─────────────────────────────────────────────────────────

def _metadata_summary(metas: List[KTRMetadata]) -> str:
    lines = []
    for m in metas:
        lines.append(f"- Archivo: {m.filename}")
        lines.append(f"  Nombre transformación: {m.transformation_name}")
        lines.append(f"  Descripción: {m.description or '(sin descripción)'}")
        lines.append(f"  Tipos de steps: {', '.join(m.step_types) if m.step_types else '(desconocido)'}")
        lines.append(f"  ¿Carga a Staging?: {'Sí' if m.has_staging else 'No'}")
        lines.append(f"  ¿Carga a DWH?: {'Sí' if m.has_dwh else 'No'}")
        lines.append("")
    return "\n".join(lines)


def _build_analyze_prompt(
    metas: List[KTRMetadata],
    job_description: str,
    business_rules: Optional[str],
) -> str:
    return f"""Analizá las siguientes transformaciones PDI e inferí el plan del job.

TRANSFORMACIONES DISPONIBLES:
{_metadata_summary(metas)}

DESCRIPCIÓN DEL JOB:
{job_description}

REGLAS ADICIONALES:
{business_rules or 'Sin reglas adicionales.'}

Devolvé ÚNICAMENTE el JSON con la estructura JobPlan. Sin texto adicional."""


def _build_refine_prompt(req: JobRefineRequest) -> str:
    if len(req.history) > _MAX_HISTORY_FULL:
        history_txt = (
            f"[{len(req.history)} iteraciones previas — últimas correcciones: "
            + "; ".join(h.get("correction", "") for h in req.history[-3:])
            + "]"
        )
    else:
        history_txt = (
            json.dumps(req.history, ensure_ascii=False, indent=2)
            if req.history
            else "Sin iteraciones previas."
        )

    return f"""El usuario solicitó la siguiente corrección sobre el plan del job:

CORRECCIÓN SOLICITADA:
{req.correction}

PLAN ACTUAL:
{req.current_job_plan.model_dump_json(indent=2)}

CONTEXTO ORIGINAL:
Descripción del job: {req.job_description}
Reglas adicionales: {req.business_rules or 'Sin reglas adicionales.'}

HISTORIAL DE CORRECCIONES:
{history_txt}

Aplicá la corrección y devolvé el JSON actualizado con el JobPlan completo.
Respetá todas las correcciones anteriores del historial.
Sin texto adicional."""


def _build_explain_prompt(job_plan: JobPlan) -> str:
    return f"""Generá una explicación en lenguaje natural del siguiente job PDI para un usuario de negocio.

PLAN DEL JOB:
{job_plan.model_dump_json(indent=2)}

Respondé ÚNICAMENTE con el JSON de explicación indicado en el system prompt."""


# ─── Response parser ──────────────────────────────────────────────────────────

def _parse_job_plan(raw: str) -> JobPlan:
    data = json.loads(raw)
    if "execution_order" not in data:
        raise ValueError("La respuesta del modelo no contiene execution_order.")
    if not data["execution_order"]:
        raise ValueError("execution_order está vacío.")
    return JobPlan(**data)


# ─── KJB XML builder ─────────────────────────────────────────────────────────

def build_kjb_xml(job_plan: JobPlan) -> str:
    ts = datetime.now().strftime("%Y/%m/%d %H:%M:%S.000")
    entries = job_plan.execution_order
    checkpoint_names = {c.after_transformation for c in job_plan.checkpoints}

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<job>",
        f"  <name>{_esc(job_plan.job_name)}</name>",
        f"  <description>{_esc(job_plan.description)}</description>",
        "  <extended_description/>",
        "  <job_version/>",
        "  <job_status>0</job_status>",
        "  <directory>&#47;</directory>",
        "  <created_user>-</created_user>",
        f"  <created_date>{ts}</created_date>",
        "  <modified_user>-</modified_user>",
        f"  <modified_date>{ts}</modified_date>",
    ]

    if job_plan.variables:
        lines.append("  <parameters>")
        for v in job_plan.variables:
            lines += [
                "    <parameter>",
                f"      <name>{_esc(v.name)}</name>",
                f"      <default_value>{_esc(v.value)}</default_value>",
                f"      <description>{_esc(v.description)}</description>",
                "    </parameter>",
            ]
        lines.append("  </parameters>")

    # ── Entries ──
    lines.append("  <entries>")

    lines += [
        "    <entry>",
        "      <name>START</name>",
        "      <type>SPECIAL</type>",
        "      <start>Y</start>",
        "      <dummy>N</dummy>",
        "      <repeat>N</repeat>",
        "      <schedulerType>0</schedulerType>",
        "      <GUI><xloc>100</xloc><yloc>200</yloc><draw>Y</draw></GUI>",
        "    </entry>",
    ]

    for i, entry in enumerate(entries):
        x = 300 + i * 200
        lines += _trans_entry(entry, x, 200)
        if entry.transformation_name in checkpoint_names:
            cp = next(
                (c for c in job_plan.checkpoints if c.after_transformation == entry.transformation_name),
                None,
            )
            msg = cp.description if cp else f"Completada: {entry.transformation_name}"
            lines += _log_entry(f"Log {entry.transformation_name}", msg, x, 320)

    abort_x = 300 + len(entries) * 200
    lines += [
        "    <entry>",
        "      <name>Abort job</name>",
        "      <type>ABORT</type>",
        "      <always_log_rows>N</always_log_rows>",
        f"      <GUI><xloc>{abort_x}</xloc><yloc>400</yloc><draw>Y</draw></GUI>",
        "    </entry>",
    ]

    success_x = abort_x + 200
    lines += [
        "    <entry>",
        "      <name>SUCCESS</name>",
        "      <type>SPECIAL</type>",
        "      <start>N</start>",
        "      <dummy>N</dummy>",
        "      <repeat>N</repeat>",
        "      <schedulerType>0</schedulerType>",
        f"      <GUI><xloc>{success_x}</xloc><yloc>200</yloc><draw>Y</draw></GUI>",
        "    </entry>",
    ]

    lines.append("  </entries>")

    # ── Hops ──
    lines.append("  <hops>")

    if entries:
        lines += _hop("START", entries[0].transformation_name, "Y", "Y")

    for i, entry in enumerate(entries):
        has_log = entry.transformation_name in checkpoint_names
        next_name = entries[i + 1].transformation_name if i + 1 < len(entries) else "SUCCESS"

        if has_log:
            log_name = f"Log {entry.transformation_name}"
            lines += _hop(entry.transformation_name, log_name, "Y", "N")
            lines += _hop(log_name, next_name, "Y", "N")
        else:
            lines += _hop(entry.transformation_name, next_name, "Y", "N")

        lines += _hop(entry.transformation_name, "Abort job", "N", "N")

    lines.append("  </hops>")
    lines += [
        "  <slave-step-copy-partition-distribution/>",
        "  <slave_transformation>N</slave_transformation>",
        "</job>",
    ]

    return "\n".join(lines)


def _trans_entry(entry: JobEntry, x: int, y: int) -> List[str]:
    return [
        "    <entry>",
        f"      <name>{_esc(entry.transformation_name)}</name>",
        "      <type>TRANS</type>",
        f"      <description>{_esc(entry.rationale)}</description>",
        "      <specification_method>filename</specification_method>",
        "      <trans_object_id/>",
        f"      <filename>./{_esc(entry.filename)}</filename>",
        "      <transname/>",
        "      <set_logfile>N</set_logfile>",
        "      <logfile/>",
        "      <logext/>",
        "      <add_date>N</add_date>",
        "      <add_time>N</add_time>",
        "      <loglevel>Basic</loglevel>",
        "      <clear_rows>N</clear_rows>",
        "      <clear_files>N</clear_files>",
        "      <set_append_logfile>N</set_append_logfile>",
        "      <wait_until_finished>Y</wait_until_finished>",
        "      <follow_abort_remote>N</follow_abort_remote>",
        "      <create_parent_folder>N</create_parent_folder>",
        "      <parameters><pass_all_parameters>Y</pass_all_parameters></parameters>",
        f"      <GUI><xloc>{x}</xloc><yloc>{y}</yloc><draw>Y</draw></GUI>",
        "    </entry>",
    ]


def _log_entry(name: str, message: str, x: int, y: int) -> List[str]:
    return [
        "    <entry>",
        f"      <name>{_esc(name)}</name>",
        "      <type>WRITE_TO_LOG</type>",
        f"      <logmessage>{_esc(message)}</logmessage>",
        "      <loglevel>Basic</loglevel>",
        f"      <GUI><xloc>{x}</xloc><yloc>{y}</yloc><draw>Y</draw></GUI>",
        "    </entry>",
    ]


def _hop(from_: str, to_: str, evaluation: str, unconditional: str) -> List[str]:
    return [
        "    <hop>",
        f"      <from>{_esc(from_)}</from>",
        f"      <to>{_esc(to_)}</to>",
        "      <from_nr>0</from_nr>",
        "      <to_nr>0</to_nr>",
        "      <enabled>Y</enabled>",
        f"      <evaluation>{evaluation}</evaluation>",
        f"      <unconditional>{unconditional}</unconditional>",
        "    </hop>",
    ]


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _sanitize_filename(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name)


# ─── Public service functions ─────────────────────────────────────────────────

async def analyze_job(
    ktr_files: List[UploadFile],
    job_description: str,
    business_rules: Optional[str],
) -> JobAnalyzeResponse:
    files_content: Dict[str, str] = {}
    warnings: List[str] = []
    metas: List[KTRMetadata] = []

    for f in ktr_files:
        raw = (await f.read()).decode("utf-8")
        try:
            meta = parse_ktr_metadata(f.filename, raw)
            metas.append(meta)
            files_content[f.filename] = raw
        except ValueError as e:
            warnings.append(str(e))
            logger.warning("No se pudo parsear %s: %s", f.filename, e)

    if not metas:
        raise ValueError("No se pudo parsear ningún archivo .ktr válido.")

    session_id = _save_ktr_files(files_content)

    prompt = _build_analyze_prompt(metas, job_description, business_rules)
    raw, _ = call_main(prompt, _SYSTEM_ANALYZE)

    try:
        job_plan = _parse_job_plan(raw)
    except (ValueError, KeyError) as e:
        logger.warning("Primer intento de análisis de job inválido (%s), reintentando...", e)
        raw, _ = call_main(prompt, _SYSTEM_ANALYZE)
        job_plan = _parse_job_plan(raw)

    return JobAnalyzeResponse(
        job_plan=job_plan,
        iteration=1,
        warnings=warnings,
        session_id=session_id,
    )


async def refine_job(request: JobRefineRequest) -> JobAnalyzeResponse:
    prompt = _build_refine_prompt(request)
    raw, _ = call_main(prompt, _SYSTEM_ANALYZE)

    try:
        job_plan = _parse_job_plan(raw)
    except (ValueError, KeyError) as e:
        logger.warning("Primer intento de refinamiento de job inválido (%s), reintentando...", e)
        raw, _ = call_main(prompt, _SYSTEM_ANALYZE)
        job_plan = _parse_job_plan(raw)

    return JobAnalyzeResponse(
        job_plan=job_plan,
        iteration=len(request.history) + 2,
        warnings=[],
        session_id=request.session_id,
    )


async def generate_job(session_id: str, job_plan: JobPlan) -> JobGenerateResponse:
    kjb_xml = build_kjb_xml(job_plan)

    explain_prompt = _build_explain_prompt(job_plan)
    raw_explain, _ = call_secondary(explain_prompt, _SYSTEM_EXPLAIN)
    try:
        explanation = json.loads(raw_explain).get("explanation", raw_explain)
    except (json.JSONDecodeError, AttributeError):
        explanation = raw_explain or ""

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    kjb_filename = f"{_sanitize_filename(job_plan.job_name)}_{ts}.kjb"

    _cleanup_session(session_id)

    return JobGenerateResponse(
        job_plan=job_plan,
        kjb_xml=kjb_xml,
        kjb_filename=kjb_filename,
        explanation=explanation,
    )
