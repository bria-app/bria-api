"""Data preparation module — ORM models.

PreparedDataset is the aggregate root; its child time series are stored denormalized
as a JSON document on the dataset row (sufficient for the thesis scope; can be
normalized into a child table later if needed).
"""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin


class PreparedDatasetModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "prepared_datasets"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    source_batch_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    product_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    series: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
