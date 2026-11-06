"""Data preparation module — use cases.

Bloque 2 implements dataset persistence and a way to register prepared series so the
forecasting module can consume them. The automatic preparation pipeline (parsing the
ingested file, cleaning, outlier treatment, stockout flagging) is a later block.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.modules.data_preparation.application.dtos import PreparedDatasetDTO
from app.modules.data_preparation.domain.entities import (
    PreparedDataset,
    PreparedTimeSeries,
)
from app.modules.data_preparation.domain.enums import DatasetStatus
from app.modules.data_preparation.domain.exceptions import (
    PreparedDatasetNotFoundError,
)
from app.modules.data_preparation.domain.repositories import (
    PreparedDatasetRepository,
)
from app.modules.data_preparation.domain.value_objects import SeriesPoint
from app.shared.domain.value_objects import DateRange


def _build_series(
    dataset_id: UUID, raw: list[dict[str, Any]]
) -> list[PreparedTimeSeries]:
    series: list[PreparedTimeSeries] = []
    for item in raw:
        points = [
            SeriesPoint(
                period_date=date.fromisoformat(str(p["period_date"])),
                demand=Decimal(str(p["demand"])),
                is_stockout=bool(p.get("is_stockout", False)),
            )
            for p in item.get("points", [])
        ]
        series.append(
            PreparedTimeSeries(
                dataset_id=dataset_id,
                product_id=UUID(str(item["product_id"])),
                points=points,
                has_stockout_flags=bool(item.get("has_stockout_flags", False)),
                outliers_treated=bool(item.get("outliers_treated", False)),
            )
        )
    return series


class CreatePreparedDataset:
    def __init__(self, datasets: PreparedDatasetRepository) -> None:
        self._datasets = datasets

    def execute(
        self,
        company_id: UUID,
        *,
        series: list[dict[str, Any]],
        source_batch_id: UUID | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> PreparedDatasetDTO:
        dataset_id = uuid4()
        built = _build_series(dataset_id, series)
        period = None
        if period_start is not None and period_end is not None:
            period = DateRange(period_start, period_end)
        dataset = PreparedDataset(
            id=dataset_id,
            company_id=company_id,
            source_batch_id=source_batch_id,
            status=DatasetStatus.READY if built else DatasetStatus.PENDING,
            product_count=len(built),
            period=period,
            series=built,
        )
        return PreparedDatasetDTO.from_entity(self._datasets.add(dataset))


class GetPreparedDataset:
    def __init__(self, datasets: PreparedDatasetRepository) -> None:
        self._datasets = datasets

    def execute(self, company_id: UUID, dataset_id: UUID) -> PreparedDatasetDTO:
        dataset = self._datasets.get_by_id(dataset_id)
        if dataset is None or dataset.company_id != company_id:
            raise PreparedDatasetNotFoundError(
                message="No encontramos ese dataset. Actualiza la página e inténtalo de nuevo."
            )
        return PreparedDatasetDTO.from_entity(dataset)


class ListPreparedDatasets:
    def __init__(self, datasets: PreparedDatasetRepository) -> None:
        self._datasets = datasets

    def execute(self, company_id: UUID) -> list[PreparedDatasetDTO]:
        return [
            PreparedDatasetDTO.from_entity(d)
            for d in self._datasets.list_by_company(company_id)
        ]


class DeletePreparedDataset:
    def __init__(self, datasets: PreparedDatasetRepository) -> None:
        self._datasets = datasets

    def execute(self, company_id: UUID, dataset_id: UUID) -> bool:
        dataset = self._datasets.get_by_id(dataset_id)
        if dataset is None or dataset.company_id != company_id:
            raise PreparedDatasetNotFoundError(
                message="No encontramos ese dataset. Actualiza la página e inténtalo de nuevo."
            )
        if not self._datasets.delete(dataset_id):
            raise PreparedDatasetNotFoundError(
                message="No encontramos ese dataset. Actualiza la página e inténtalo de nuevo."
            )
        return True
