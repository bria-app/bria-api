"""Recommendations module — ORM models."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin


class RecommendationModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "recommendations"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    recommended_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="pending", nullable=False)
