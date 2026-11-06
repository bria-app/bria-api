"""Dashboard module — application DTOs."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.dashboard.domain.entities import DashboardWidget
from app.modules.dashboard.domain.enums import WidgetType


class DashboardWidgetDTO(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    widget_type: WidgetType
    position: int
    config: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_entity(cls, entity: DashboardWidget) -> DashboardWidgetDTO:
        if entity.id is None:
            raise ValueError("Entity must have an id to create DTO")
        return cls(
            id=entity.id,
            company_id=entity.company_id,
            title=entity.title,
            widget_type=entity.widget_type,
            position=entity.position,
            config=entity.config,
        )


class DashboardSummaryDTO(BaseModel):
    """A summary of key metrics and the dashboard layout."""
    company_id: UUID
    widgets: list[DashboardWidgetDTO]
    metrics: dict[str, Any]
