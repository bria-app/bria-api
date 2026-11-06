"""Dashboard module — mappers."""
from __future__ import annotations

from app.modules.dashboard.domain.entities import DashboardWidget
from app.modules.dashboard.domain.enums import WidgetType
from app.modules.dashboard.infrastructure.persistence.models import (
    DashboardWidgetModel,
)


def widget_to_entity(model: DashboardWidgetModel) -> DashboardWidget:
    return DashboardWidget(
        id=model.id,
        company_id=model.company_id,
        title=model.title,
        widget_type=WidgetType(model.widget_type),
        position=model.position,
        config=model.config or {},
    )


def widget_to_model(entity: DashboardWidget) -> DashboardWidgetModel:
    return DashboardWidgetModel(
        id=entity.id,
        company_id=entity.company_id,
        title=entity.title,
        widget_type=entity.widget_type.value,
        position=entity.position,
        config=entity.config,
    )
