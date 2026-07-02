from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        from app.core.config import settings
        connect_args: dict = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def create_tables() -> None:
    # TODO: Alembic para versionar el schema más adelante
    import app.models.connection  # noqa: F401
    import app.models.etl  # noqa: F401
    import app.models.job  # noqa: F401
    import app.models.ktr_build_job  # noqa: F401
    Base.metadata.create_all(bind=_get_engine())


def _get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=_get_engine(), autoflush=False, autocommit=False
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = _get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> sessionmaker:
    """FastAPI dependency wrapping _get_session_factory() so background tasks
    (asyncio.create_task, outside the request's own Session lifetime) can open
    their own session using the same factory the request used — overridable in
    tests via app.dependency_overrides, unlike importing _get_session_factory
    directly."""
    return _get_session_factory()
