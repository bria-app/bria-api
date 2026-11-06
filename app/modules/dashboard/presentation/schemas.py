"""Dashboard module — HTTP schemas."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.dashboard.application.dtos import DashboardSummaryDTO, DashboardWidgetDTO
from app.modules.dashboard.domain.enums import WidgetType


class DashboardWidgetResponse(DashboardWidgetDTO):
    """Response schema for a dashboard widget."""
    pass


class DashboardOverviewResponse(DashboardSummaryDTO):
    """Response schema for the dashboard summary."""
    pass


class AddWidgetRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    widget_type: WidgetType
    position: int = 0
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateWidgetRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    config: dict[str, Any] | None = None


class ReorderWidgetsRequest(BaseModel):
    """Map of widget_id -> new_position"""
    positions: dict[UUID, int]


# Placeholders for endpoints not fully implemented
class DashboardChartResponse(BaseModel):
    message: str
    module: str
    action: str
