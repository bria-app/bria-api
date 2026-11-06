"""Data preparation module — SQLAlchemy repository implementation."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data_preparation.domain.entities import PreparedDataset
from app.modules.data_preparation.domain.exceptions import (
    PreparedDatasetNotFoundError,
)
from app.modules.data_preparation.infrastructure.persistence.mappers import (
    dataset_to_entity,
    dataset_to_model,
)
from app.modules.data_preparation.infrastructure.persistence.models import (
    PreparedDatasetModel,
)


class SqlPreparedDatasetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, dataset_id: UUID) -> PreparedDataset | None:
        model = self._session.get(PreparedDatasetModel, dataset_id)
        return dataset_to_entity(model) if model else None

    def list_by_company(self, company_id: UUID) -> list[PreparedDataset]:
        rows = self._session.execute(
            select(PreparedDatasetModel)
            .where(PreparedDatasetModel.company_id == company_id)
            .order_by(PreparedDatasetModel.created_at.desc())
        ).scalars().all()
        return [dataset_to_entity(m) for m in rows]

    def add(self, dataset: PreparedDataset) -> PreparedDataset:
        model = dataset_to_model(dataset)
        self._session.add(model)
        self._session.flush()
        return dataset_to_entity(model)

    def update(self, dataset: PreparedDataset) -> PreparedDataset:
        model = self._session.get(PreparedDatasetModel, dataset.id)
        if model is None:
            raise PreparedDatasetNotFoundError(
                message="No encontramos ese dataset. Actualiza la página e inténtalo de nuevo."
            )
        model.source_batch_id = dataset.source_batch_id
        model.status = dataset.status.value
        model.product_count = dataset.product_count
        model.period_start = dataset.period.start if dataset.period else None
        model.period_end = dataset.period.end if dataset.period else None
        model.series = dataset_to_model(dataset).series
        self._session.flush()
        return dataset_to_entity(model)

    def delete(self, dataset_id: UUID) -> bool:
        model = self._session.get(PreparedDatasetModel, dataset_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True
