"""Sales module — ORM models."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.shared.infrastructure.database.portable import UTCDateTime


class SalesBatchModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sales_batches"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)


class SaleModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sales"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    batch_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="PEN", nullable=False)
    # POS line: which ticket it belongs to, who sold it and the cost at that moment.
    order_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    seller_id: Mapped[UUID | None] = mapped_column(nullable=True)
    seller_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)


class SalesOrderModel(Base, UUIDMixin, TimestampMixin):
    """A POS ticket: the cart the seller closed, with client and comprobante data."""

    __tablename__ = "sales_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "order_number", name="uq_sales_orders_company_number"),
    )

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    order_number: Mapped[int] = mapped_column(Integer, nullable=False)
    seller_id: Mapped[UUID | None] = mapped_column(index=True, nullable=True)
    seller_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    document_type: Mapped[str] = mapped_column(String(12), default="boleta", nullable=False)
    client_doc_type: Mapped[str] = mapped_column(String(10), default="none", nullable=False)
    client_doc_number: Mapped[str] = mapped_column(String(11), default="", nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    client_address: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), default="efectivo", nullable=False)
    amount_received: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    igv: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="PEN", nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="completed", nullable=False)
    invoice_id: Mapped[UUID | None] = mapped_column(nullable=True)
    notes: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    sold_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class LostSaleModel(Base, UUIDMixin, TimestampMixin):
    """A sale attempt that could not happen because there was not enough stock (quiebre)."""

    __tablename__ = "lost_sales"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    requested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    seller_id: Mapped[UUID | None] = mapped_column(nullable=True)
    seller_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="pos", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
