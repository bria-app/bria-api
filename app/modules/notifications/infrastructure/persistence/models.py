"""Notifications module — ORM models."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, UUIDMixin
from app.shared.infrastructure.database.portable import UTCDateTime


class NotificationModel(Base, UUIDMixin):
    __tablename__ = "notifications"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False
    )
