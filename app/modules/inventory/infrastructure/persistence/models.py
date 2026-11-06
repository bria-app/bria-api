"""Inventory module — ORM models."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.shared.infrastructure.database.portable import UTCDateTime


class InventoryMovementModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "inventory_movements"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    # Valuation + traceability: cost of the units moved and the document that moved them.
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reference_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)


class StockSnapshotModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "stock_snapshots"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ReplenishmentModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "replenishments"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="suggested", nullable=False)


class StockoutEventModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "stockout_events"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
