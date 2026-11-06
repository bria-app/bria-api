"""Ingestion module — SQLAlchemy repository implementation."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ingestion.domain.entities import IngestionBatch
from app.modules.ingestion.domain.exceptions import IngestionBatchNotFoundError
from app.modules.ingestion.infrastructure.persistence.mappers import (
    batch_to_entity,
    batch_to_model,
)
from app.modules.ingestion.infrastructure.persistence.models import (
    IngestionBatchModel,
)


class SqlIngestionBatchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, batch_id: UUID) -> IngestionBatch | None:
        model = self._session.get(IngestionBatchModel, batch_id)
        return batch_to_entity(model) if model else None

    def list_by_company(self, company_id: UUID) -> list[IngestionBatch]:
        rows = self._session.execute(
            select(IngestionBatchModel)
            .where(IngestionBatchModel.company_id == company_id)
            .order_by(IngestionBatchModel.created_at.desc())
        ).scalars().all()
        return [batch_to_entity(m) for m in rows]

    def add(self, batch: IngestionBatch) -> IngestionBatch:
        model = batch_to_model(batch)
        self._session.add(model)
        self._session.flush()
        return batch_to_entity(model)

    def update(self, batch: IngestionBatch) -> IngestionBatch:
        model = self._session.get(IngestionBatchModel, batch.id)
        if model is None:
            raise IngestionBatchNotFoundError(
                message="No encontramos esa carga de archivo. Actualiza la página e inténtalo de nuevo."
            )
        model.file_name = batch.file_name
        model.file_path = batch.file_path
        model.file_type = batch.file_type.value
        model.column_mapping = dict(batch.column_mapping)
        model.status = batch.status.value
        model.row_count = batch.row_count
        model.error_count = batch.error_count
        self._session.flush()
        return batch_to_entity(model)
