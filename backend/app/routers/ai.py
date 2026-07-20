import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_owner, require_auth
from app.core.database import get_db, get_session_factory
from app.core.dependencies import get_main_llm, get_secondary_llm
from app.models.llm_base import BaseLLM
from app.models.ktr_build_job import KtrBuildJob, ModelStatus
from app.schemas.etl_schemas import (
    BuildFromRawRequest,
    ConnectionsMapRequest,
    ETLDocumentRequest,
    ETLDocumentResponse,
    ETLFromInferenceRequest,
    ETLGenerateResponse,
    ETLValidateRequest,
    ETLValidateResponse,
    GenerateAsyncResponse,
    InferRequest,
    InferResponse,
    KtrJobStatusResponse,
    RefineRequest,
)
from app.services.etl_generator import (
    build_etl_from_raw,
    generate_etl_async,
    generate_etl_from_inference,
    KtrBuildError,
    _try_build,
)
from app.services.validator import validate_etl
from app.services.documenter import document_etl
from app.services.structure_inferrer import infer_structures, refine_structures
from app.services.lineage_builder import build_lineage_from_xml, stitch_lineage_from_xml
from app.schemas.lineage import Lineage
from app.schemas.job_schemas import (
    JobAnalyzeResponse,
    JobGenerateRequest,
    JobGenerateResponse,
    JobRefineRequest,
)
from app.services import job_analyzer

router = APIRouter(tags=["ETL"], dependencies=[Depends(require_auth)])
logger = logging.getLogger(__name__)


class _KtrLogHandler(logging.Handler):
    """Forwards ktr_builder log messages into an asyncio queue for SSE streaming."""
    def __init__(self, queue: asyncio.Queue):
        super().__init__()
        self.queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait({"type": "ktr_log", "message": self.format(record)})
        except asyncio.QueueFull:
            pass

#TODO: modelo anthropic devuelve algo que da error 502 mal manejado de nuestro lado.
async def _handle(fn, *args):
    try:
        return await fn(*args)
    except KtrBuildError as e:
        logger.error("build_ktr failed: %s", str(e.original_error))
        raise HTTPException(status_code=502, detail={
            "message": f"El modelo respondió pero falló la construcción del .ktr: {e.original_error}",
            "raw_llm_data": e.raw_data,
        })
    except json.JSONDecodeError as e:
        logger.error("JSON parse error: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except Exception as e:
        logger.error("Service error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))



# ── ETL — endpoints principales ───────────────────────────────────────────────

@router.post("/api/v1/etl/validate", response_model=ETLValidateResponse)
async def validate(
    req: ETLValidateRequest,
    llm: BaseLLM = Depends(get_secondary_llm),
):
    """RF8, RF9 — Valida calidad y malas prácticas."""
    return await _handle(validate_etl, req, llm)


@router.post("/api/v1/etl/document", response_model=ETLDocumentResponse)
async def document(
    req: ETLDocumentRequest,
    llm: BaseLLM = Depends(get_secondary_llm),
):
    """RF11, RF12, RF13 — Genera documentación en lenguaje natural."""
    return await _handle(document_etl, req, llm)


# ── Flujo de inferencia automática ────────────────────────────────────────────

@router.post("/api/v1/etl/infer-structures", response_model=InferResponse)
async def infer(
    req: InferRequest,
    llm: BaseLLM = Depends(get_main_llm),
    db:  Session = Depends(get_db),
):
    """Infiere automáticamente la tabla STG y el modelo DWH a partir de los 3 campos del usuario."""
    return await _handle(infer_structures, req, llm, db)


@router.post("/api/v1/etl/infer-structures/refine", response_model=InferResponse)
async def refine(
    req: RefineRequest,
    llm: BaseLLM = Depends(get_main_llm),
    db:  Session = Depends(get_db),
):
    """Incorpora una corrección en lenguaje natural y regenera las estructuras con contexto acumulado."""
    return await _handle(refine_structures, req, llm, db)


@router.post("/api/v1/etl/generate-from-inference", response_model=ETLGenerateResponse)
async def generate_from_inference(
    req: ETLFromInferenceRequest,
    llm: BaseLLM = Depends(get_main_llm),
    db:  Session = Depends(get_db),
):
    """Genera el proceso ETL completo usando estructuras STG/DWH inferidas por el modelo."""
    return await _handle(generate_etl_from_inference, req, llm, db)


@router.post("/api/v1/etl/build-from-raw", response_model=ETLGenerateResponse)
async def build_from_raw(req: BuildFromRawRequest):
    """Reconstruye el .ktr a partir de una respuesta cruda del modelo guardada previamente
    por el frontend (descargada tras un fallo de build_ktr). No llama al LLM.

    Repair loop (repair_ktr_steps) desconectado a propósito acá — ver discusión
    pendiente sobre si "Reutilizar respuesta" debe poder llamar al modelo."""
    return await _handle(build_etl_from_raw, req.raw_llm_data)


# ── Flujo async: modelo + conexiones destino en paralelo ─────────────────────
# generate-async dispara el modelo en background y devuelve job_id de inmediato.
# El cliente arranca el formulario de conexiones (staging/DWH) al mismo tiempo,
# sin esperar al modelo. build_ktr() es una barrera: se dispara en cuanto ambos
# lados (JSON del modelo + connections_map) están listos, sin importar el orden.

_JOB_TTL_MINUTES = 30


def _job_or_404(job_id: str, db: Session, owner: Optional[str] = None) -> KtrBuildJob:
    """
    owner: owner_id del caller autenticado (None en modo AUTH_REQUIRED=false,
    salta el chequeo). Un job ajeno se trata igual que "no encontrado" — mismo
    404 que un job_id inválido o inexistente, sin distinción — de lo contrario
    alguien podría leer /status de un job de otro usuario (y el .ktr con
    passwords resueltos que ese status devuelve) con solo adivinar el UUID.
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="job_id inválido.")

    job = db.get(KtrBuildJob, job_uuid)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    if owner is not None and job.owner_id != owner:
        raise HTTPException(status_code=404, detail="Job no encontrado.")

    # SQLite no preserva tzinfo en columnas DateTime(timezone=True) — expires_at
    # vuelve naive al leerlo. Siempre se escribe en UTC, así que asumirlo es seguro.
    expires_at = job.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        db.delete(job)
        db.commit()
        raise HTTPException(status_code=410, detail="El job expiró (30 min). Generá el ETL de nuevo.")

    return job


def _status_response(job: KtrBuildJob) -> KtrJobStatusResponse:
    # build_status == "failed": el modelo ya respondió (job.model_json quedó
    # poblado en generate_etl_async) pero build_ktr() falló en _try_build.
    # Devolvemos esa respuesta cruda para que el frontend no la pierda.
    raw_llm_data = None
    if job.build_status.value == "failed" and job.model_json:
        data_1 = job.model_json.get("raw_data_1")
        data_2 = job.model_json.get("raw_data_2")
        if data_1 is not None and data_2 is not None:
            raw_llm_data = {"ktr_1": data_1, "ktr_2": data_2}

    return KtrJobStatusResponse(
        model_status=job.model_status.value,
        build_status=job.build_status.value,
        error=job.model_error,
        result=ETLGenerateResponse(**job.result_json) if job.result_json else None,
        raw_llm_data=raw_llm_data,
    )


@router.post("/api/v1/etl/generate-async", response_model=GenerateAsyncResponse)
async def generate_async(
    req: ETLFromInferenceRequest,
    llm: BaseLLM = Depends(get_main_llm),
    db:  Session = Depends(get_db),
    session_factory = Depends(get_session_factory),
    payload: Optional[dict] = Depends(require_auth),
):
    """Crea el job y dispara la llamada al modelo en background — responde con
    job_id sin esperar al modelo, para que el cliente arranque el formulario de
    conexiones en paralelo."""
    job = KtrBuildJob(
        owner_id=get_current_owner(payload),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=_JOB_TTL_MINUTES),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    asyncio.create_task(generate_etl_async(job.id, req, llm, session_factory))

    return GenerateAsyncResponse(job_id=str(job.id))


@router.post("/api/v1/etl/{job_id}/connections", response_model=KtrJobStatusResponse)
async def submit_job_connections(
    job_id: str,
    body: ConnectionsMapRequest,
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    """Ata connection_id ya creados (vía POST /api/connections, mismo formulario
    reusado del frontend) al job. No pide datos de conexión — eso ya ocurrió
    en el navegador antes de esta llamada.

    El frontend dispara una llamada fire-and-forget por cada conexión (origen,
    staging, dwh) apenas queda lista, sin esperar a las anteriores — nada
    garantiza que lleguen acá en el mismo orden en que se enviaron. Mergear
    (en vez de reemplazar el dict entero) hace que el orden de llegada no
    importe: una request más chica que llega tarde ya no puede pisar una
    conexión que otra request más nueva escribió antes. Reemplazar el dict
    entero perdía en silencio la conexión que no venía en el último payload
    en llegar — build_ktr() terminaba con esa capa en placeholder sin que
    nada lo señalara como error de este paso."""
    job = _job_or_404(job_id, db, get_current_owner(payload))
    job.connections_map = {**(job.connections_map or {}), **body.model_dump(exclude_none=True)}
    db.commit()
    _try_build(job.id, db)
    db.refresh(job)
    return _status_response(job)


@router.get("/api/v1/etl/{job_id}/status", response_model=KtrJobStatusResponse)
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    """Poleado por el cliente hasta build_status == 'built' (o 'failed')."""
    job = _job_or_404(job_id, db, get_current_owner(payload))
    return _status_response(job)


@router.post("/api/v1/etl/generate-from-inference/stream")
async def generate_from_inference_sse(
    req: ETLFromInferenceRequest,
    llm: BaseLLM = Depends(get_main_llm),
    db:  Session = Depends(get_db),
):
    """SSE stream: emite llm_done → ktr_log* → result (o error)."""
    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)

        ktr_logger = logging.getLogger("app.services.ktr_builder")
        handler = _KtrLogHandler(queue)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.setLevel(logging.DEBUG)
        ktr_logger.addHandler(handler)

        result_box: list = []
        error_box:  list = []

        async def on_llm_done():
            await queue.put({"type": "llm_done"})

        async def run():
            try:
                result = await generate_etl_from_inference(req, llm, db, on_llm_done=on_llm_done)
                result_box.append(result)
            except Exception as exc:
                error_box.append(exc)
            finally:
                await queue.put({"type": "done"})

        task = asyncio.create_task(run())

        try:
            while True:
                msg = await queue.get()
                if msg["type"] == "done":
                    if error_box:
                        exc = error_box[0]
                        if isinstance(exc, KtrBuildError):
                            payload = json.dumps({
                                "type": "error",
                                "message": f"El modelo respondió pero falló la construcción del .ktr: {exc.original_error}",
                                "raw_llm_data": exc.raw_data,
                            })
                        else:
                            payload = json.dumps({"type": "error", "message": str(exc)})
                    else:
                        data = result_box[0].model_dump() if hasattr(result_box[0], "model_dump") else result_box[0].dict()
                        payload = json.dumps({"type": "result", "data": data})
                    yield f"data: {payload}\n\n"
                    break
                elif msg["type"] == "ktr_log":
                    yield f"data: {json.dumps(msg)}\n\n"
                    await asyncio.sleep(0.12)
                else:
                    yield f"data: {json.dumps(msg)}\n\n"
        finally:
            ktr_logger.removeHandler(handler)
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Integración Superset ─────────────────────────────────────────────────────

def _resolve_conn_dwh(etl_id: str, db: Session):
    """
    Devuelve siempre None: el backend ya no persiste passwords de conexión,
    así que no hay forma de abrir una conexión real a conn_dwh en este punto
    (no hay ninguna request en curso de la que tomar un password fresco —
    esto corre en checks post-hoc, potencialmente mucho después de que el
    usuario tipeó la contraseña). Los dos callers (superset_dwh_status,
    superset_export) ya tratan conn is None como "no se puede confirmar
    nada" sin romper el flujo. Esta función y sus callers se revisan a
    fondo en el cambio de Superset a configuración manual.
    """
    return None


def _expected_dwh_tables(etl) -> list[str]:
    """Nombres de tabla DWH (no-staging) esperados según dwh_sample del resultado."""
    from app.services.superset_client import STAGING_PREFIXES

    dwh_sample = ((etl.result or {}).get("dwh_sample")) or {}
    return [
        name for name in dwh_sample.keys()
        if not any(str(name).lower().startswith(p) for p in STAGING_PREFIXES)
    ]


@router.get("/api/v1/etl/{etl_id}/superset/dwh-status")
def superset_dwh_status(etl_id: str, db: Session = Depends(get_db)):
    """
    Estado real (existencia + row count, sin filas) de las tablas DWH
    esperadas para este ETL, consultando conn_dwh directamente. Gate on-click
    antes de exportar a Superset: available=False si no hay conn_dwh
    configurada (ETLs viejos, o el usuario nunca la completó) — en ese caso
    el frontend no bloquea, simplemente no puede confirmar nada.
    """
    from app.models.etl import Etl
    from app.services.db_connector import check_dwh_tables

    etl = db.get(Etl, etl_id)
    if etl is None:
        raise HTTPException(status_code=404, detail="ETL no encontrado.")

    conn = _resolve_conn_dwh(etl_id, db)
    if conn is None:
        return {"available": False, "hasData": False, "tables": []}

    table_names = _expected_dwh_tables(etl)
    if not table_names:
        return {"available": False, "hasData": False, "tables": []}

    tables = check_dwh_tables(conn, table_names)
    has_data = any(t["rowCount"] > 0 for t in tables)
    return {"available": True, "hasData": has_data, "tables": tables}


@router.post("/api/v1/etl/{etl_id}/superset/export")
async def superset_export(etl_id: str, db: Session = Depends(get_db)):
    """Arma el ZIP de dashboard de Superset para este ETL (backend, sin upload) y lo
    importa. Reemplaza al viejo POST /api/v1/superset/import — el frontend ya no
    construye el ZIP, solo pide con el etl_id."""
    from app.models.etl import Etl
    from app.services.db_connector import check_dwh_tables
    from app.services.superset_client import SupersetClient, SupersetError, build_superset_uri
    from app.services.superset_export import build as build_export_zip
    from app.core.config import settings as _settings

    etl = db.get(Etl, etl_id)
    if etl is None:
        raise HTTPException(status_code=404, detail="ETL no encontrado.")

    try:
        zip_bytes, dwh_sample = build_export_zip(etl)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    real_table_status: dict[str, dict] | None = None
    real_uri: str | None = None
    conn = _resolve_conn_dwh(etl_id, db)
    if conn is not None:
        try:
            real_uri = build_superset_uri(conn)
        except Exception as exc:
            logger.warning("No se pudo armar la URI real de conn_dwh: %s", exc)
        table_names = _expected_dwh_tables(etl)
        if table_names:
            status_list = check_dwh_tables(conn, table_names)
            real_table_status = {s["name"].lower(): s for s in status_list}

    client = SupersetClient(
        _settings.superset_url,
        _settings.superset_username,
        _settings.superset_password,
    )
    try:
        url = await client.import_dashboard(
            zip_bytes, dwh_sample=dwh_sample, real_table_status=real_table_status, real_uri=real_uri,
        )
        return {"dashboard_url": url}
    except SupersetError as e:
        logger.error("Superset import error: %s", str(e))
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("Superset import unexpected error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Linaje de datos ───────────────────────────────────────────────────────────

class _KtrXmlBody(BaseModel):
    ktr_xml: str
    ktr2_xml: Optional[str] = None

@router.post("/api/ai/lineage-from-ktr", response_model=Lineage)
async def lineage_from_ktr(body: _KtrXmlBody):
    """Parsea 1 o 2 .ktr XML ya serializados y devuelve el grafo de linaje. Sin llamada al modelo.

    ktr2_xml es opcional: si viene (flujo de 2 KTR + 1 .kjb), cose origen→STG→DWH
    con stitch_lineage_from_xml(). El orden es fijo por convención de nuestro propio
    flujo de generación (ktr_xml = KTR_1 origen→STG, ktr2_xml = KTR_2 STG→DWH) —
    no depende del .kjb para deducirlo.
    """
    if not body.ktr_xml:
        raise HTTPException(status_code=422, detail="ktr_xml no puede estar vacío.")
    if body.ktr2_xml:
        return stitch_lineage_from_xml(body.ktr_xml, body.ktr2_xml)
    return build_lineage_from_xml(body.ktr_xml)


# ── Flujo de generación de Jobs PDI (.kjb) ────────────────────────────────────

@router.post("/api/v1/job/analyze", response_model=JobAnalyzeResponse)
async def analyze_job(
    ktr_files:        List[UploadFile] = File(...),
    job_description:  str              = Form(...),
    business_rules:   Optional[str]    = Form(None),
    main_llm:         BaseLLM          = Depends(get_main_llm),
):
    """Parsea N archivos .ktr, infiere el orden lógico y devuelve el plan del job para revisión."""
    try:
        return await job_analyzer.analyze_job(ktr_files, job_description, business_rules, main_llm)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error en analyze_job: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except Exception as e:
        logger.error("Error en analyze_job: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/job/refine", response_model=JobAnalyzeResponse)
async def refine_job(
    req:      JobRefineRequest,
    main_llm: BaseLLM = Depends(get_main_llm),
):
    """Incorpora una corrección en lenguaje natural y regenera el plan del job con historial acumulado."""
    try:
        return await job_analyzer.refine_job(req, main_llm)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error en refine_job: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except Exception as e:
        logger.error("Error en refine_job: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/job/generate", response_model=JobGenerateResponse)
async def generate_job(
    req:           JobGenerateRequest,
    secondary_llm: BaseLLM = Depends(get_secondary_llm),
):
    """Toma el JobPlan confirmado y genera el XML .kjb final + explicación en lenguaje natural."""
    try:
        return await job_analyzer.generate_job(req.session_id, req.job_plan, secondary_llm)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error en generate_job: %s", str(e))
        raise HTTPException(status_code=502, detail="El modelo devolvió una respuesta con formato inválido.")
    except FileNotFoundError as e:
        logger.error("Sesión no encontrada: %s", str(e))
        raise HTTPException(status_code=404, detail="Sesión expirada o no encontrada. Volvé a subir los archivos .ktr.")
    except Exception as e:
        logger.error("Error en generate_job: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
