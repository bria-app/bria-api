"""Data preparation module — application output DTOs."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.modules.data_preparation.domain.entities import PreparedDataset


class SeriesSummaryDTO(BaseModel):
    product_id: UUID
    point_count: int
    has_stockout_flags: bool
    outliers_treated: bool


class PreparedDatasetDTO(BaseModel):
    id: UUID
    company_id: UUID
    source_batch_id: UUID | None
    status: str
    product_count: int
    period_start: date | None
    period_end: date | None
    series: list[SeriesSummaryDTO]

    @classmethod
    def from_entity(cls, dataset: PreparedDataset) -> PreparedDatasetDTO:
        assert dataset.id is not None
        return cls(
            id=dataset.id,
            company_id=dataset.company_id,
            source_batch_id=dataset.source_batch_id,
            status=dataset.status.value,
            product_count=dataset.product_count,
            period_start=dataset.period.start if dataset.period else None,
            period_end=dataset.period.end if dataset.period else None,
            series=[
                SeriesSummaryDTO(
                    product_id=s.product_id,
                    point_count=len(s.points),
                    has_stockout_flags=s.has_stockout_flags,
                    outliers_treated=s.outliers_treated,
                )
                for s in dataset.series
            ],
        )
