from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ModelStatus(str, enum.Enum):
    pending = "pending"
    done = "done"
    failed = "failed"


class KtrBuildStatus(str, enum.Enum):
    awaiting_model = "awaiting_model"
    awaiting_connections = "awaiting_connections"
    built = "built"
    failed = "failed"


class KtrBuildJob(Base):
    """Fila de correlación entre la generación async del modelo y las conexiones
    de destino que el usuario completa en paralelo. build_ktr() se dispara cuando
    ambos lados están listos, sin importar el orden de llegada.

    connections_map guarda solo IDs de Connection (uuid), nunca credenciales.
    """
    __tablename__ = "ktr_build_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Claim "sub" del JWT de quien creó el job (mismo criterio que Connection.owner_id)
    # — se usa para que resolve_real_connections() solo resuelva conexiones del
    # mismo dueño del job, y para que _job_or_404 rechace jobs ajenos.
    owner_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    model_status: Mapped[ModelStatus] = mapped_column(
        SAEnum(ModelStatus, name="ktr_job_model_status_enum"), default=ModelStatus.pending
    )
    model_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    connections_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    build_status: Mapped[KtrBuildStatus] = mapped_column(
        SAEnum(KtrBuildStatus, name="ktr_job_build_status_enum"), default=KtrBuildStatus.awaiting_model
    )
    # ETLGenerateResponse.model_dump() completo (proceso_etl, ktr_xml, lineage,
    # advertencias con los warnings de conexión, etc.) — lo que devuelve /status.
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
