from __future__ import annotations

from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Única capa que toca la DB. Cada método recibe una Session explícita."""

    def __init__(self, model: Type[ModelT]) -> None:
        self.model = model

    def list_all(self, db: Session) -> List[ModelT]:
        return db.query(self.model).order_by(self.model.created_at.desc()).all()  # type: ignore[attr-defined]

    def get(self, db: Session, id: str) -> Optional[ModelT]:
        return db.get(self.model, id)

    def create(self, db: Session, data: dict) -> ModelT:
        obj = self.model(**data)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def update(self, db: Session, obj: ModelT, data: dict) -> ModelT:
        for key, value in data.items():
            setattr(obj, key, value)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(self, db: Session, obj: ModelT) -> None:
        db.delete(obj)
        db.commit()
