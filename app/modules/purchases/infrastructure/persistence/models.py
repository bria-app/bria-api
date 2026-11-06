"""Purchases module — ORM models."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin


class PurchaseModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "purchases"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    supplier_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="PEN", nullable=False)
    # Supplier's own comprobante number (e.g. F001-000123) and the bulk import it came from.
    document_number: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    import_batch_id: Mapped[UUID | None] = mapped_column(nullable=True)
    notes: Mapped[str] = mapped_column(String(500), default="", nullable=False)
