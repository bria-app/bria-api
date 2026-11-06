"""Companies module — ORM models (separate from domain entities)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.shared.infrastructure.database.portable import UTCDateTime


class CompanyModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_id: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    business_type: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    address: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    # Next number for auto-generated product codes (per-company, global across the catalog).
    next_product_code: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class UserModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id"), index=True, nullable=False
    )
    # Owners sign in with email; sellers created by the admin sign in with username.
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(60), unique=True, index=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="viewer", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="invited", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
