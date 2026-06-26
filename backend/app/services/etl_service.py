from __future__ import annotations

from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.etl import Etl
from app.repositories.etl_repository import etl_repo
from app.schemas.etl import EtlCreate, EtlStatusUpdate, EtlUpdate


def list_etls(db: Session) -> List[Etl]:
    return etl_repo.list_all(db)

def get_etl(db: Session, id: str) -> Etl:
    obj = etl_repo.get(db, id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ETL not found")
    return obj

def create_etl(db: Session, payload: EtlCreate) -> Etl:
    # mode="json" serializa enums como su .value (str puro para SQLite/Postgres)
    data = payload.model_dump(by_alias=False, exclude_none=True, mode="json")
    return etl_repo.create(db, data)

def update_etl(db: Session, id: str, payload: EtlUpdate) -> Etl:
    obj = get_etl(db, id)
    data = payload.model_dump(by_alias=False, exclude_unset=True, mode="json")
    return etl_repo.update(db, obj, data)

def set_etl_status(db: Session, id: str, payload: EtlStatusUpdate) -> Etl:
    obj = get_etl(db, id)
    return etl_repo.update(db, obj, {"status": payload.status.value})

def delete_etl(db: Session, id: str) -> None:
    obj = get_etl(db, id)
    etl_repo.delete(db, obj)