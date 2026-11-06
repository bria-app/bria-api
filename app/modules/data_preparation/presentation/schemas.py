"""Data preparation module — presentation request schemas."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class SeriesPointRequest(BaseModel):
    period_date: date
    demand: Decimal
    is_stockout: bool = False


class SeriesRequest(BaseModel):
    product_id: UUID
    points: list[SeriesPointRequest] = []
    has_stockout_flags: bool = False
    outliers_treated: bool = False


class CreatePreparedDatasetRequest(BaseModel):
    source_batch_id: UUID | None = None
    period_start: date | None = None
    period_end: date | None = None
    series: list[SeriesRequest] = []


class PrepareFromBatchRequest(BaseModel):
    batch_id: UUID
    treat_zero_as_stockout: bool = False
