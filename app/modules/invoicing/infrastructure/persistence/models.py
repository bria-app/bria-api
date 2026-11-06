"""Invoicing module — ORM models."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.shared.infrastructure.database.portable import UTCDateTime


class InvoiceModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "invoices"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(10), nullable=False)
    series: Mapped[str] = mapped_column(String(4), nullable=False)
    correlativo: Mapped[int] = mapped_column(Integer, nullable=False)
    client_doc_type: Mapped[str] = mapped_column(String(10), default="none", nullable=False)
    client_doc_number: Mapped[str] = mapped_column(String(11), default="", nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), default="Público en general", nullable=False)
    client_address: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    igv: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="PEN", nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="emitida", nullable=False)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    sale_id: Mapped[UUID | None] = mapped_column(nullable=True)
