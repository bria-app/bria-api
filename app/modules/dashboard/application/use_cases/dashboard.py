"""Dashboard module — application use cases."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.dashboard.application.dtos import (
    DashboardSummaryDTO,
    DashboardWidgetDTO,
)
from app.modules.dashboard.domain.entities import DashboardWidget
from app.modules.dashboard.domain.enums import WidgetType
from app.modules.dashboard.domain.exceptions import DashboardWidgetNotFoundError
from app.modules.dashboard.domain.repositories import DashboardWidgetRepository


class GetDashboardSummary:
    def __init__(self, widget_repo: DashboardWidgetRepository) -> None:
        self._widget_repo = widget_repo

    def execute(self, company_id: UUID) -> DashboardSummaryDTO:
        entities = self._widget_repo.list_by_company(company_id)
        widgets = [DashboardWidgetDTO.from_entity(e) for e in entities]
        
        # STUB metrics for scaffold
        metrics = {
            "total_products": 1500,
            "stockouts_predicted": 12,
            "overstock_value": 45000.0,
            "turnover_rate": 4.5,
        }
        
        return DashboardSummaryDTO(
            company_id=company_id,
            widgets=widgets,
            metrics=metrics,
        )


class AddWidget:
    def __init__(self, widget_repo: DashboardWidgetRepository) -> None:
        self._widget_repo = widget_repo

    def execute(
        self,
        company_id: UUID,
        title: str,
        widget_type: WidgetType,
        position: int,
        config: dict[str, Any] | None = None,
    ) -> DashboardWidgetDTO:
        entity = DashboardWidget(
            company_id=company_id,
            title=title,
            widget_type=widget_type,
            position=position,
            config=config or {},
        )
        saved = self._widget_repo.add(entity)
        return DashboardWidgetDTO.from_entity(saved)


class UpdateWidget:
    def __init__(self, widget_repo: DashboardWidgetRepository) -> None:
        self._widget_repo = widget_repo

    def execute(
        self,
        company_id: UUID,
        widget_id: UUID,
        title: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> DashboardWidgetDTO:
        entity = self._widget_repo.get_by_id(widget_id)
        if not entity or entity.company_id != company_id:
            raise DashboardWidgetNotFoundError(widget_id)

        if title is not None:
            entity.title = title
        if config is not None:
            entity.config = config

        updated = self._widget_repo.update(entity)
        return DashboardWidgetDTO.from_entity(updated)


class RemoveWidget:
    def __init__(self, widget_repo: DashboardWidgetRepository) -> None:
        self._widget_repo = widget_repo

    def execute(self, company_id: UUID, widget_id: UUID) -> None:
        entity = self._widget_repo.get_by_id(widget_id)
        if not entity or entity.company_id != company_id:
            raise DashboardWidgetNotFoundError(widget_id)

        self._widget_repo.delete(widget_id)


class ReorderWidgets:
    def __init__(self, widget_repo: DashboardWidgetRepository) -> None:
        self._widget_repo = widget_repo

    def execute(self, company_id: UUID, position_updates: dict[UUID, int]) -> None:
        """Batch update widget positions."""
        # For simplicity in this scaffold, we just trust the position_updates
        # In a real scenario, we might want to validate that all widgets belong to the company
        self._widget_repo.update_positions(company_id, position_updates)
