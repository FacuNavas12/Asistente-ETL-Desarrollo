"""
Schema extraction endpoints.

POST /api/schema/infer     — upload CSV/Excel → CanonicalSchema (Frictionless)
POST /api/schema/from-ddl  — paste DDL SQL   → list[CanonicalSchema] (sqlglot)

Design constraints:
  - Only schema structure and statistical metadata are returned.
  - Raw row values never leave the backend.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.auth import require_auth
from app.schemas.canonical import CanonicalSchema

router = APIRouter(prefix="/api/schema", tags=["schema"], dependencies=[Depends(require_auth)])
logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = frozenset({".csv", ".xlsx", ".xls"})
_MAX_BYTES = 50 * 1024 * 1024   # 50 MB hard limit


@router.post("/infer", response_model=CanonicalSchema)
async def infer_schema(file: UploadFile) -> CanonicalSchema:
    """
    Accepts a CSV or Excel file and returns its CanonicalSchema.

    The schema includes:
      - fields: name, canonical type, format (inferred_by="frictionless")
      - profile: null_pct, distinct_count per column (from ≤1000-row sample)

    No raw row data is included in the response.
    """
    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo de archivo no soportado: '{suffix}'. Use .csv, .xlsx o .xls.",
        )

    source_name = Path(file.filename or "tabla").stem

    tmp_path: str | None = None
    try:
        # Stream upload to a temp file with the correct extension so frictionless
        # can detect the format by suffix.
        with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False
        ) as tmp:
            tmp_path = tmp.name
            total = 0
            while chunk := await file.read(65536):
                total += len(chunk)
                if total > _MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Archivo demasiado grande (máximo {_MAX_BYTES // 1_048_576} MB).",
                    )
                tmp.write(chunk)

        try:
            from app.services.file_schema import infer_file_schema
        except ImportError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Dependencia no instalada para inferencia de archivos: {exc}. "
                       "Instalar con: pip install frictionless[excel]",
            )
        schema = infer_file_schema(tmp_path, source_name)
        return schema

    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("Schema inference failed for '%s': %s", file.filename, exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Unexpected error inferring schema for '%s': %s", file.filename, exc)
        raise HTTPException(status_code=500, detail="Error inesperado al procesar el archivo.")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


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
