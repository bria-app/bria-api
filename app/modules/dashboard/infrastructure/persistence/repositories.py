"""Dashboard module — SQLAlchemy repository implementation."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.dashboard.domain.entities import DashboardWidget
from app.modules.dashboard.domain.exceptions import DashboardWidgetNotFoundError
from app.modules.dashboard.infrastructure.persistence.mappers import (
    widget_to_entity,
    widget_to_model,
)
from app.modules.dashboard.infrastructure.persistence.models import (
    DashboardWidgetModel,
)


class SqlDashboardWidgetRepository:
    """SQLAlchemy implementation of DashboardWidgetRepository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, widget_id: UUID) -> DashboardWidget | None:
        model = self._session.get(DashboardWidgetModel, widget_id)
        return widget_to_entity(model) if model else None

    def list_by_company(self, company_id: UUID) -> list[DashboardWidget]:
        rows = self._session.execute(
            select(DashboardWidgetModel)
            .where(DashboardWidgetModel.company_id == company_id)
            .order_by(DashboardWidgetModel.position.asc())
        ).scalars().all()
        return [widget_to_entity(m) for m in rows]

    def add(self, widget: DashboardWidget) -> DashboardWidget:
        model = widget_to_model(widget)
        self._session.add(model)
        self._session.flush()
        return widget_to_entity(model)

    def update(self, widget: DashboardWidget) -> DashboardWidget:
        model = self._session.get(DashboardWidgetModel, widget.id)
        if model is None:
            raise DashboardWidgetNotFoundError(widget.id)  # type: ignore[arg-type]
        
        model.title = widget.title
        model.widget_type = widget.widget_type.value
        model.position = widget.position
        model.config = widget.config
        
        self._session.flush()
        return widget_to_entity(model)

    def delete(self, widget_id: UUID) -> bool:
        model = self._session.get(DashboardWidgetModel, widget_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True

    def update_positions(
        self, company_id: UUID, position_updates: dict[UUID, int]
    ) -> None:
        """Batch update positions for widgets."""
        if not position_updates:
            return

        for widget_id, position in position_updates.items():
            self._session.execute(
                update(DashboardWidgetModel)
                .where(
                    DashboardWidgetModel.id == widget_id,
                    DashboardWidgetModel.company_id == company_id,
                )
                .values(position=position)
            )
        self._session.flush()
