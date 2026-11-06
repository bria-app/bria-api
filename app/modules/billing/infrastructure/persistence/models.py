"""Billing module — ORM models."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.shared.infrastructure.database.portable import UTCDateTime


class SubscriptionModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id"), unique=True, index=True, nullable=False
    )
    plan_id: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False
    )


class BillingPaymentModel(Base, UUIDMixin, TimestampMixin):
    """Simulated plan payments. Only card last4 is ever stored."""

    __tablename__ = "billing_payments"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(50), nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(10), nullable=False, default="monthly")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PEN")
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="paid")
    reference: Mapped[str] = mapped_column(String(40), nullable=False)
    card_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
