"""Products module — ORM models."""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin


class CategoryModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "product_categories"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_categories.id"), nullable=True
    )


class ProductModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("company_id", "sku", name="uq_products_company_sku"),
    )

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_categories.id"), nullable=True
    )
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="PEN", nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(20), default="unit", nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    safety_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reorder_point: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    # Data URL (base64) or external URL of the product photo.
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Values for the company's user-defined product columns, keyed by field key.
    custom_attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Cost of the most recent purchase; unit_cost holds the weighted-average cost.
    last_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
