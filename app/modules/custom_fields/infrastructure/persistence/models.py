"""Custom fields module — ORM models."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base, TimestampMixin, UUIDMixin


class CustomFieldDefinitionModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "custom_field_definitions"
    __table_args__ = (
        UniqueConstraint("company_id", "entity", "key", name="uq_custom_fields_company_entity_key"),
    )

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    entity: Mapped[str] = mapped_column(String(20), nullable=False)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    options: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Product columns only: categories the column applies to (and their subcategories).
    # Empty = every product.
    category_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Advanced config: {"validation": {...}, "alert": {...}}; {} = no rules.
    rules: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False, server_default="{}"
    )


class UiPreferenceModel(Base, UUIDMixin, TimestampMixin):
    """Saved per-company UI state, e.g. which built-in inventory columns are hidden."""

    __tablename__ = "ui_preferences"
    __table_args__ = (UniqueConstraint("company_id", "key", name="uq_ui_preferences_company_key"),)

    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
