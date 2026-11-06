"""Storage — ORM model for database-backed file blobs.

Stores uploaded file bytes inside Postgres so they survive container restarts
and ephemeral filesystems (e.g. Render/Railway free tiers). Used by DbFileStorage.
"""
from __future__ import annotations

from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin


class StoredBlobModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "stored_blobs"

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
