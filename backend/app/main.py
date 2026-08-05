import logging
import os
import shutil
import sys
from contextlib import asynccontextmanager
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.log_filters import PasswordFilter
from app.routers import ai, connections, schema
from app.routers import etl as etl_router
from app.routers import job as job_router

_log_dir = Path(__file__).resolve().parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)

_fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


class _SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """On Windows, os.rename() fails when a sibling process holds the file open.
    Fall back to copy+truncate so the active writers keep their handles intact."""

    def rotate(self, source: str, dest: str) -> None:
        if sys.platform == "win32":
            try:
                os.rename(source, dest)
            except PermissionError:
                shutil.copy2(source, dest)
                with open(source, "w"):
                    pass
        else:
            super().rotate(source, dest)


# Rotación diaria; retención 90 días (Ley 18.331 — Limitación de conservación).
# Los archivos rotan a medianoche UTC y se nombran generaciones.log.YYYY-MM-DD.
_file_handler = _SafeTimedRotatingFileHandler(
    _log_dir / "generaciones.log",
    when="midnight",
    interval=1,
    backupCount=90,
    encoding="utf-8",
    utc=True,
)
_file_handler.setFormatter(logging.Formatter(_fmt))

logging.basicConfig(
    level=logging.INFO,
    format=_fmt,
    handlers=[
        logging.StreamHandler(),
        _file_handler,
    ],
)
logging.getLogger().addFilter(PasswordFilter())


async def _purge_expired_ktr_jobs(session_factory) -> None:
    """Barrido periódico de ktr_build_jobs vencidos (TTL 30 min) — cubre el caso
    de un usuario que arranca la generación y abandona el formulario de
    conexiones sin volver. El chequeo lazy en _job_or_404 ya evita servir una
    fila vencida; esto solo evita que se acumulen filas huérfanas."""
    from asyncio import sleep
    from datetime import datetime, timezone

    from app.models.ktr_build_job import KtrBuildJob

    while True:
        await sleep(300)
        db = session_factory()
        try:
            db.query(KtrBuildJob).filter(KtrBuildJob.expires_at < datetime.now(timezone.utc)).delete()
            db.commit()
        except Exception:
            logging.getLogger(__name__).exception("Error al purgar ktr_build_jobs vencidos")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from asyncio import create_task

    from app.core.database import _get_session_factory
    from app.outbox import get_outbox
    from app.outbox.runner import run_in_process

    # Entrypoint A — in-process drain loop.
    # To switch to an external process/cron (entrypoint B), remove this task
    # and wire app.outbox.runner.run_drain_once_sync() to your scheduler.
    # Pieces 1 (OutboxPort) and 2 (drainer.drain) are not touched.
    _drain_task = create_task(run_in_process(get_outbox(), _get_session_factory()))
    _ktr_ttl_task = create_task(_purge_expired_ktr_jobs(_get_session_factory()))

    yield

    _drain_task.cancel()
    _ktr_ttl_task.cancel()


app = FastAPI(title="Acelerador ETL — API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,  # dev: localhost:5173; prod: dominio de Vercel (ALLOWED_ORIGINS)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai.router)
app.include_router(connections.router)
app.include_router(schema.router)
app.include_router(etl_router.router)
app.include_router(job_router.router)


@app.get("/")
async def health():
    return {"status": "ok"}
