"""Suppliers module — ORM models."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin


class SupplierModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "suppliers"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    ruc: Mapped[str] = mapped_column(String(11), nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    address: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Values for the company's user-defined supplier columns (e.g. bank account).
    custom_attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
