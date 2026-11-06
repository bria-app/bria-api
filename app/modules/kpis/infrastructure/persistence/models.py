"""KPIs module — ORM models."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.shared.infrastructure.database.portable import UTCDateTime


class KpiModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "kpis"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    kpi_type: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
