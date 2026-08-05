from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import require_auth
from app.core.database import get_db
from app.schemas.job import JobCreate, JobRead, JobStatusUpdate, JobUpdate
from app.services import job_service

router = APIRouter(prefix="/api/jobs", tags=["Jobs"], dependencies=[Depends(require_auth)])


@router.get("/", response_model=List[JobRead])
def list_jobs(db: Session = Depends(get_db)):
    return job_service.list_jobs(db)


@router.post("/", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    return job_service.create_job(db, payload)


@router.get("/{id}", response_model=JobRead)
def get_job(id: str, db: Session = Depends(get_db)):
    return job_service.get_job(db, id)


@router.put("/{id}", response_model=JobRead)
def update_job(id: str, payload: JobUpdate, db: Session = Depends(get_db)):
    return job_service.update_job(db, id, payload)


@router.patch("/{id}/status", response_model=JobRead)
def set_job_status(id: str, payload: JobStatusUpdate, db: Session = Depends(get_db)):
    return job_service.set_job_status(db, id, payload)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(id: str, db: Session = Depends(get_db)):
    job_service.delete_job(db, id)
