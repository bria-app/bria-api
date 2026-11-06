"""Forecasting module — ORM models."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.shared.infrastructure.database.portable import UTCDateTime


class ForecastRunModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "forecast_runs"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    dataset_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # How the run was scoped (e.g. {"type": "recent_sales", "months": 6}) and what it covered.
    scope: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    product_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(10), nullable=True)


class ForecastResultModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "forecast_results"

    run_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    points: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    # In-sample history buckets (observed/cleaned/fitted) — nullable for legacy rows.
    history: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=list, nullable=True)


class ForecastMetricsModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "forecast_metrics"

    run_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    # Nullable: an unmeasurable metric is stored as NULL, never as a misleading 0.
    mape: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    mae: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    rmse: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    mase: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    rmsse: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    order_selected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_used: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ok", nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    validation_rmse: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
