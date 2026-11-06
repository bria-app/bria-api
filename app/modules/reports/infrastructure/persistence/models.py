"""Reports module — ORM models."""
from __future__ import annotations

from uuid import UUID
from typing import Any

from sqlalchemy import ForeignKey, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin


class ReportModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "reports"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
