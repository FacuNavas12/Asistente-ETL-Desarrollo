"""
Schema extraction endpoints.

POST /api/schema/infer     — upload CSV/Excel → CanonicalSchema (Frictionless)
POST /api/schema/from-ddl  — paste DDL SQL   → list[CanonicalSchema] (sqlglot)

Design constraints:
  - Only schema structure and statistical metadata are returned.
  - Raw row values never leave the backend.
  - The upload boundary (disk I/O, size/extension policy) lives in
    services/file_schema.py, not here (R2, docs/arquitectura-objetivo.md) —
    this router only translates HTTP <-> bytes and maps exceptions to status
    codes.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.auth import require_auth
from app.schemas.canonical import CanonicalSchema

router = APIRouter(prefix="/api/schema", tags=["schema"], dependencies=[Depends(require_auth)])
logger = logging.getLogger(__name__)


@router.post("/infer", response_model=CanonicalSchema)
async def infer_schema(file: UploadFile) -> CanonicalSchema:
    """
    Accepts a CSV or Excel file and returns its CanonicalSchema.

    The schema includes:
      - fields: name, canonical type, format (inferred_by="frictionless")
      - profile: null_pct, distinct_count per column (from ≤1000-row sample)

    No raw row data is included in the response.
    """
    try:
        from app.services.file_schema import (
            FileTooLarge,
            UnsupportedFileType,
            infer_schema_from_upload,
        )
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Dependencia no instalada para inferencia de archivos: {exc}. "
                   "Instalar con: pip install frictionless[excel]",
        )

    async def _chunks():
        while chunk := await file.read(65536):
            yield chunk

    try:
        return await infer_schema_from_upload(file.filename, _chunks())
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FileTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except ValueError as exc:
        logger.warning("Schema inference failed for '%s': %s", file.filename, exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Unexpected error inferring schema for '%s': %s", file.filename, exc)
        raise HTTPException(status_code=500, detail="Error inesperado al procesar el archivo.")


# ── DDL endpoint ──────────────────────────────────────────────────────────────

_DDL_DIALECTS = {"ansi", "postgres", "tsql", "mysql"}


class DdlRequest(BaseModel):
    ddl: str
    dialect: Literal["ansi", "postgres", "tsql", "mysql"] = "ansi"


@router.post("/from-ddl", response_model=list[CanonicalSchema])
def from_ddl(body: DdlRequest) -> list[CanonicalSchema]:
    """
    Parse one or more CREATE TABLE statements and return a CanonicalSchema per table.

    - Unknown or proprietary SQL types map to CanonicalType.UNKNOWN (no error).
    - Dialect controls how SQL Server (tsql), PostgreSQL (postgres), MySQL (mysql)
      or standard SQL (ansi) syntax is interpreted.
    - Returns an empty list if no CREATE TABLE is found in the input.
    """
    ddl = body.ddl.strip()
    if not ddl:
        raise HTTPException(status_code=422, detail="El DDL no puede estar vacío.")

    sqlglot_dialect = None if body.dialect == "ansi" else body.dialect

    try:
        from app.services.adapters.ddl_adapter import parse_ddl
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Dependencia no instalada para parseo de DDL: {exc}. "
                   "Instalar con: pip install sqlglot",
        )
    try:
        schemas = parse_ddl(ddl, sqlglot_dialect)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Unexpected error parsing DDL: %s", exc)
        raise HTTPException(status_code=500, detail="Error inesperado al parsear el DDL.")

    if not schemas:
        raise HTTPException(
            status_code=422,
            detail="No se encontró ningún CREATE TABLE en el DDL proporcionado.",
        )
    return schemas
