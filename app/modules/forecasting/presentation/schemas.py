"""Forecasting module — presentation request schemas."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

ScopeType = Literal["recent_sales", "supplier", "seller", "category", "products", "all"]
Frequency = Literal["auto", "monthly", "weekly"]


class ForecastScope(BaseModel):
    type: ScopeType
    months: int | None = Field(default=None, ge=1, le=120)
    supplier_id: UUID | None = None
    seller_id: UUID | None = None
    category_id: UUID | None = None
    product_ids: list[UUID] | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class CreateForecastRunRequest(BaseModel):
    model_name: str = "FTGM"
    horizon_days: int = Field(default=30, ge=1, le=730)
    # Legacy CSV path.
    dataset_id: UUID | None = None
    # ERP path: scope (+ frequency). The job starts right away.
    scope: ForecastScope | None = None
    frequency: Frequency = "auto"
    # Optional cut-off (backtesting): history strictly before it; defaults to today (Lima).
    as_of: date | None = None


class ScopePreviewRequest(BaseModel):
    scope: ForecastScope
    frequency: Frequency = "auto"
    as_of: date | None = None
