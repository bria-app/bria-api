"""Audit module — ORM models."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, UUIDMixin
from app.shared.infrastructure.database.portable import UTCDateTime


class AuditEventModel(Base, UUIDMixin):
    __tablename__ = "audit_events"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id"), index=True, nullable=False
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), index=True, nullable=False
    )
