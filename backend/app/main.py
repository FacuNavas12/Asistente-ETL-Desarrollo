import logging
import os
import shutil
import sys
from contextlib import asynccontextmanager
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.log_filters import PasswordFilter
from app.routers import ai, connections, schema

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.database import create_tables
    create_tables()
    yield


app = FastAPI(title="Acelerador ETL — API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # frontend dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai.router)
app.include_router(connections.router)
app.include_router(schema.router)


@app.get("/")
async def health():
    return {"status": "ok"}
