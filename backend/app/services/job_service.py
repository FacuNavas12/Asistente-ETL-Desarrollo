from __future__ import annotations

from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.job import Job
from app.repositories.job_repository import job_repo
from app.schemas.job import JobCreate, JobStatusUpdate, JobUpdate


def list_jobs(db: Session) -> List[Job]:
    return job_repo.list_all(db)


def get_job(db: Session, id: str) -> Job:
    obj = job_repo.get(db, id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return obj


def create_job(db: Session, payload: JobCreate) -> Job:
    # mode="json" serializa enums como su .value (str puro para SQLite/Postgres)
    data = payload.model_dump(by_alias=False, exclude_none=True, mode="json")
    return job_repo.create(db, data)


def update_job(db: Session, id: str, payload: JobUpdate) -> Job:
    obj = get_job(db, id)
    data = payload.model_dump(by_alias=False, exclude_unset=True, mode="json")
    return job_repo.update(db, obj, data)


def set_job_status(db: Session, id: str, payload: JobStatusUpdate) -> Job:
    obj = get_job(db, id)
    return job_repo.update(db, obj, {"status": payload.status.value})


def delete_job(db: Session, id: str) -> None:
    obj = get_job(db, id)
    job_repo.delete(db, obj)
