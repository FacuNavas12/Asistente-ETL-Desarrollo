from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_owner, require_auth
from app.core.database import get_db
from app.schemas.etl import EtlCreate, EtlRead, EtlStatusUpdate, EtlUpdate
from app.schemas.etl_schemas import ConnectionsMapRequest, ETLGenerateResponse, MetadataResponse
from app.services import etl_service
from app.services.etl_generator import KtrBuildError, _build_response_from_two_ktr_data
from app.services.ktr_builder import missing_layer_warnings, resolve_real_connections

router = APIRouter(prefix="/api/etls", tags=["ETLs"], dependencies=[Depends(require_auth)])


@router.get("/", response_model=List[EtlRead])
def list_etls(db: Session = Depends(get_db)):
    return etl_service.list_etls(db)


@router.post("/", response_model=EtlRead, status_code=status.HTTP_201_CREATED)
def create_etl(payload: EtlCreate):
    # No DB dependency — write goes to the local outbox only; never blocks on Supabase.
    return etl_service.create_etl(payload)


@router.get("/{id}", response_model=EtlRead)
def get_etl(id: str, db: Session = Depends(get_db)):
    return etl_service.get_etl(db, id)


@router.put("/{id}", response_model=EtlRead)
def update_etl(id: str, payload: EtlUpdate, db: Session = Depends(get_db)):
    return etl_service.update_etl(db, id, payload)


@router.patch("/{id}/status", response_model=EtlRead)
def set_etl_status(id: str, payload: EtlStatusUpdate, db: Session = Depends(get_db)):
    return etl_service.set_etl_status(db, id, payload)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_etl(id: str, db: Session = Depends(get_db)):
    etl_service.delete_etl(db, id)


@router.post("/{id}/connections", response_model=ETLGenerateResponse)
def update_etl_connections(
    id: str,
    body: ConnectionsMapRequest,
    db: Session = Depends(get_db),
    payload: Optional[dict] = Depends(require_auth),
):
    """Re-adapta la conexión destino (staging/DWH) de un ETL ya generado —
    equivalente a editar el conector en Spoon, pero desde acá. No vuelve a
    llamar al LLM: reconstruye el .ktr a partir del raw_data que se guardó
    junto con el ETL (form_data.rawLlmData, ver KtrJobStatusResponse.raw_llm_data
    en /api/v1/etl/{job_id}/status) aplicando la conexión real nueva.
    Si el ETL se generó antes de que existiera esa persistencia, no hay
    raw_data para reconstruir."""
    etl = etl_service.get_etl(db, id)
    raw = (etl.form_data or {}).get("rawLlmData") or {}
    if not raw.get("ktr_1") or not raw.get("ktr_2"):
        raise HTTPException(
            status_code=409,
            detail="Este ETL no tiene datos crudos guardados para reconstruir el .ktr — regeneralo desde cero.",
        )
    metadata_raw = (etl.result or {}).get("metadata")
    if not metadata_raw:
        raise HTTPException(status_code=409, detail="Este ETL no tiene metadata guardada para reconstruir el .ktr.")

    connections_map = body.model_dump(exclude_none=True)
    real_connections, conn_warnings = resolve_real_connections(
        connections_map, db, owner=get_current_owner(payload)
    )
    # Capa que ni siquiera llegó en el body (ej. "Completar en Spoon" sin marcar
    # explícito, o conn_origen ausente) — mismo criterio que _try_build (D15).
    conn_warnings = [*conn_warnings, *missing_layer_warnings(real_connections)]

    try:
        result = _build_response_from_two_ktr_data(
            raw["ktr_1"], raw["ktr_2"], MetadataResponse(**metadata_raw),
            real_connections=real_connections,
            connection_warnings=conn_warnings,
            strict_connections=True,
            # sin esto, cada reconstrucción vía este endpoint (reconectar destino)
            # pisa etl.result sin dwh_ddl/stg_ddl porque raw_llm_data (ai.py) nunca
            # los guardó — ResultView oculta la sección de DDL apenas se llama acá.
            dwh_ddl=(etl.result or {}).get("dwh_ddl"),
            stg_ddl=(etl.result or {}).get("stg_ddl"),
        )
    except KtrBuildError as exc:
        raise HTTPException(status_code=422, detail=str(exc.original_error))

    new_form_data = {**(etl.form_data or {}), "connectionsMap": connections_map}
    etl_service.update_etl(
        db, id, EtlUpdate(form_data=new_form_data, result=result.model_dump(mode="json"))
    )
    return result
