"""Dashboard module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.modules.dashboard.domain.enums import WidgetType


@dataclass
class DashboardWidget:
    """A widget placed on a company's dashboard."""

    company_id: UUID
    title: str
    widget_type: WidgetType
    position: int
    config: dict[str, Any] = field(default_factory=dict)
    id: UUID | None = None
