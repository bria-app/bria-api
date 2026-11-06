"""Data preparation module domain — entities.

Design note: PreparedTimeSeries is modeled as an entity (not a frozen VO)
because it belongs to a dataset and may have its flags mutated during the
preparation pipeline (e.g., marking outliers_treated). It does not have its
own id because it is identified by (dataset_id, product_id) — a child entity
within the PreparedDataset aggregate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.modules.data_preparation.domain.enums import DatasetStatus
from app.modules.data_preparation.domain.value_objects import SeriesPoint
from app.shared.domain.value_objects import DateRange


@dataclass
class PreparedTimeSeries:
    """Time-series data for a single product within a dataset.

    This is a child entity within the PreparedDataset aggregate.
    Identified by (dataset_id, product_id).
    """

    dataset_id: UUID
    product_id: UUID
    points: list[SeriesPoint] = field(default_factory=list)
    has_stockout_flags: bool = False
    outliers_treated: bool = False


@dataclass
class PreparedDataset:
    """A dataset ready (or being prepared) for forecasting.

    Aggregate root: owns its child PreparedTimeSeries. Persistence may load
    ``series`` lazily, but the domain treats them as part of this aggregate.
    """

    company_id: UUID
    source_batch_id: UUID | None = None
    status: DatasetStatus = DatasetStatus.PENDING
    product_count: int = 0
    period: DateRange | None = None
    series: list[PreparedTimeSeries] = field(default_factory=list)
    id: UUID | None = None
