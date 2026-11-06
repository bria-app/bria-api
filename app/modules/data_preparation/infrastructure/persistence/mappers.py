"""Data preparation module — mappers (with JSON (de)serialization of series)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.data_preparation.domain.entities import (
    PreparedDataset,
    PreparedTimeSeries,
)
from app.modules.data_preparation.domain.enums import DatasetStatus
from app.modules.data_preparation.domain.value_objects import SeriesPoint
from app.modules.data_preparation.infrastructure.persistence.models import (
    PreparedDatasetModel,
)
from app.shared.domain.value_objects import DateRange


def _series_to_dict(series: PreparedTimeSeries) -> dict[str, Any]:
    return {
        "product_id": str(series.product_id),
        "has_stockout_flags": series.has_stockout_flags,
        "outliers_treated": series.outliers_treated,
        "points": [
            {
                "period_date": p.period_date.isoformat(),
                "demand": str(p.demand),
                "is_stockout": p.is_stockout,
            }
            for p in series.points
        ],
    }


def _series_from_dict(dataset_id: UUID, data: dict[str, Any]) -> PreparedTimeSeries:
    return PreparedTimeSeries(
        dataset_id=dataset_id,
        product_id=UUID(str(data["product_id"])),
        points=[
            SeriesPoint(
                period_date=date.fromisoformat(str(p["period_date"])),
                demand=Decimal(str(p["demand"])),
                is_stockout=bool(p.get("is_stockout", False)),
            )
            for p in data.get("points", [])
        ],
        has_stockout_flags=bool(data.get("has_stockout_flags", False)),
        outliers_treated=bool(data.get("outliers_treated", False)),
    )


def dataset_to_entity(model: PreparedDatasetModel) -> PreparedDataset:
    period = None
    if model.period_start is not None and model.period_end is not None:
        period = DateRange(model.period_start, model.period_end)
    return PreparedDataset(
        id=model.id,
        company_id=model.company_id,
        source_batch_id=model.source_batch_id,
        status=DatasetStatus(model.status),
        product_count=model.product_count,
        period=period,
        series=[_series_from_dict(model.id, s) for s in model.series],
    )


def dataset_to_model(entity: PreparedDataset) -> PreparedDatasetModel:
    return PreparedDatasetModel(
        id=entity.id,
        company_id=entity.company_id,
        source_batch_id=entity.source_batch_id,
        status=entity.status.value,
        product_count=entity.product_count,
        period_start=entity.period.start if entity.period else None,
        period_end=entity.period.end if entity.period else None,
        series=[_series_to_dict(s) for s in entity.series],
    )
