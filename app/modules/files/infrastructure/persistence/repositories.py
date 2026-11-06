"""Files module — SQLAlchemy repository implementation."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.files.domain.entities import StoredFile
from app.modules.files.infrastructure.persistence.mappers import (
    stored_file_to_entity,
    stored_file_to_model,
)
from app.modules.files.infrastructure.persistence.models import StoredFileModel


class SqlStoredFileRepository:
    """SQLAlchemy implementation of StoredFileRepository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, file_id: UUID) -> StoredFile | None:
        model = self._session.get(StoredFileModel, file_id)
        return stored_file_to_entity(model) if model else None

    def list_by_company(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> list[StoredFile]:
        rows = self._session.execute(
            select(StoredFileModel)
            .where(StoredFileModel.company_id == company_id)
            .order_by(StoredFileModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).scalars().all()
        return [stored_file_to_entity(m) for m in rows]

    def add(self, stored_file: StoredFile) -> StoredFile:
        model = stored_file_to_model(stored_file)
        self._session.add(model)
        self._session.flush()
        return stored_file_to_entity(model)

    def delete(self, file_id: UUID) -> bool:
        model = self._session.get(StoredFileModel, file_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True
