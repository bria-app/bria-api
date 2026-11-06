"""Dashboard module domain layer."""
from app.modules.dashboard.domain.entities import DashboardWidget
from app.modules.dashboard.domain.enums import WidgetType
from app.modules.dashboard.domain.exceptions import DashboardWidgetNotFoundError
from app.modules.dashboard.domain.repositories import DashboardWidgetRepository

__all__ = [
    "DashboardWidget",
    "DashboardWidgetNotFoundError",
    "DashboardWidgetRepository",
    "WidgetType",
]
