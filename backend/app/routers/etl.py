from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.etl import EtlCreate, EtlRead, EtlStatusUpdate, EtlUpdate
from app.services import etl_service

router = APIRouter(prefix="/api/etls", tags=["ETLs"])


@router.get("/", response_model=List[EtlRead])
def list_etls(db: Session = Depends(get_db)):
    return etl_service.list_etls(db)


@router.post("/", response_model=EtlRead, status_code=status.HTTP_201_CREATED)
def create_etl(payload: EtlCreate, db: Session = Depends(get_db)):
    return etl_service.create_etl(db, payload)


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
