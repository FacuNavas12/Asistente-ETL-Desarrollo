from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.etl import Etl
from app.outbox import get_outbox
from app.outbox.port import OutboxEntry, SyncStatus
from app.repositories.etl_repository import etl_repo
from app.schemas.common import WorkflowStatus
from app.schemas.etl import EtlCreate, EtlRead, EtlStatusUpdate, EtlUpdate


# ── Converters ────────────────────────────────────────────────────────────────

def _etl_to_read(etl: Etl, sync_status: SyncStatus = SyncStatus.synced) -> EtlRead:
    return EtlRead(
        id=etl.id,
        name=etl.name,
        status=WorkflowStatus(etl.status),
        sync_status=sync_status,
        form_data=etl.form_data,
        result=etl.result,
        created_at=etl.created_at,
        updated_at=etl.updated_at,
    )


def _entry_to_read(entry: OutboxEntry) -> EtlRead:
    p = entry.payload
    created_raw = p.get("created_at")
    updated_raw = p.get("updated_at")
    created = datetime.fromisoformat(created_raw) if isinstance(created_raw, str) else (created_raw or datetime.now(timezone.utc))
    updated = datetime.fromisoformat(updated_raw) if isinstance(updated_raw, str) else (updated_raw or created)
    return EtlRead(
        id=entry.id,
        name=p["name"],
        status=WorkflowStatus(p.get("status", WorkflowStatus.draft.value)),
        sync_status=entry.sync_status,
        form_data=p.get("form_data"),
        result=p.get("result"),
        created_at=created,
        updated_at=updated,
    )


# ── Read operations (merge Supabase + outbox) ─────────────────────────────────

def list_etls(db: Session) -> List[EtlRead]:
    # Synced records live in Supabase.
    supabase: dict[str, EtlRead] = {e.id: _etl_to_read(e, SyncStatus.synced) for e in etl_repo.list_all(db)}

    # Pending/failed records exist only in the outbox (not yet in Supabase).
    # list_non_synced() never returns synced entries so there is no ID collision.
    outbox_pending: dict[str, EtlRead] = {e.id: _entry_to_read(e) for e in get_outbox().list_non_synced()}

    merged = {**supabase, **outbox_pending}
    return sorted(merged.values(), key=lambda x: x.created_at, reverse=True)


def get_etl(db: Session, id: str) -> EtlRead:
    # Pending/failed: outbox is the source of truth (not yet written to Supabase).
    entry = get_outbox().get_by_id(id)
    if entry and entry.sync_status != SyncStatus.synced:
        return _entry_to_read(entry)

    # Synced: Supabase is the source of truth.
    obj = etl_repo.get(db, id)
    if obj:
        return _etl_to_read(obj, SyncStatus.synced)

    # Edge-case: outbox entry exists as synced but Supabase row was deleted externally.
    if entry:
        return _entry_to_read(entry)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ETL not found")


# ── Write operations ───────────────────────────────────────────────────────────

def create_etl(payload: EtlCreate) -> EtlRead:
    """
    Non-blocking create. Writes to the local outbox and returns immediately.
    The background runner will drain the outbox to Supabase asynchronously.
    """
    etl_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    data = payload.model_dump(by_alias=False, exclude_none=True, mode="json")
    data["id"] = etl_id
    data["created_at"] = now.isoformat()
    data["updated_at"] = now.isoformat()

    get_outbox().enqueue(etl_id, data)

    return EtlRead(
        id=etl_id,
        name=payload.name,
        status=payload.status,
        sync_status=SyncStatus.pending,
        form_data=payload.form_data,
        result=payload.result,
        created_at=now,
        updated_at=now,
    )


def update_etl(db: Session, id: str, payload: EtlUpdate) -> EtlRead:
    """
    Non-blocking update. Reads current state (outbox wins over Supabase),
    applies changes, and enqueues the full snapshot. Never touches Supabase directly.
    Re-enqueueing an already-synced ETL resets its sync_status to pending.
    """
    current = get_etl(db, id)  # 404 if not found in either outbox or Supabase
    updates = payload.model_dump(by_alias=False, exclude_unset=True, mode="json")
    now = datetime.now(timezone.utc)

    snapshot = {
        "id": id,
        "name": updates.get("name", current.name),
        "status": updates.get("status", current.status.value),
        "form_data": updates.get("form_data", current.form_data),
        "result": updates.get("result", current.result),
        "created_at": current.created_at.isoformat(),
        "updated_at": now.isoformat(),
    }
    get_outbox().enqueue(id, snapshot)

    return EtlRead(
        id=id,
        name=snapshot["name"],
        status=WorkflowStatus(snapshot["status"]),
        sync_status=SyncStatus.pending,
        form_data=snapshot["form_data"],
        result=snapshot["result"],
        created_at=current.created_at,
        updated_at=now,
    )


def set_etl_status(db: Session, id: str, payload: EtlStatusUpdate) -> EtlRead:
    """Non-blocking status patch. Same outbox path as update_etl."""
    current = get_etl(db, id)
    now = datetime.now(timezone.utc)

    snapshot = {
        "id": id,
        "name": current.name,
        "status": payload.status.value,
        "form_data": current.form_data,
        "result": current.result,
        "created_at": current.created_at.isoformat(),
        "updated_at": now.isoformat(),
    }
    get_outbox().enqueue(id, snapshot)

    return EtlRead(
        id=id,
        name=current.name,
        status=payload.status,
        sync_status=SyncStatus.pending,
        form_data=current.form_data,
        result=current.result,
        created_at=current.created_at,
        updated_at=now,
    )


def delete_etl(db: Session, id: str) -> None:
    obj = _get_etl_orm(db, id)
    etl_repo.delete(db, obj)


def _get_etl_orm(db: Session, id: str) -> Etl:
    obj = etl_repo.get(db, id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ETL not found")
    return obj
