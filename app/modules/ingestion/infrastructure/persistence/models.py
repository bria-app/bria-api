"""Ingestion module — ORM models."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin


class IngestionBatchModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ingestion_batches"

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    column_mapping: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="uploaded", nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
