"""Tests for Dashboard module."""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.dashboard.application.use_cases.dashboard import (
    AddWidget,
    GetDashboardSummary,
    RemoveWidget,
    ReorderWidgets,
    UpdateWidget,
)
from app.modules.dashboard.domain.entities import DashboardWidget
from app.modules.dashboard.domain.enums import WidgetType


class FakeDashboardWidgetRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, DashboardWidget] = {}

    def get_by_id(self, widget_id: UUID) -> DashboardWidget | None:
        return self._store.get(widget_id)

    def list_by_company(self, company_id: UUID) -> list[DashboardWidget]:
        rows = [w for w in self._store.values() if w.company_id == company_id]
        rows.sort(key=lambda w: w.position)
        return rows

    def add(self, widget: DashboardWidget) -> DashboardWidget:
        if widget.id is None:
            widget.id = uuid4()
        self._store[widget.id] = widget
        return widget

    def update(self, widget: DashboardWidget) -> DashboardWidget:
        assert widget.id is not None
        self._store[widget.id] = widget
        return widget

    def delete(self, widget_id: UUID) -> bool:
        return self._store.pop(widget_id, None) is not None

    def update_positions(
        self, company_id: UUID, position_updates: dict[UUID, int]
    ) -> None:
        for w_id, pos in position_updates.items():
            w = self._store.get(w_id)
            if w and w.company_id == company_id:
                w.position = pos


class TestDashboardUseCases:
    def test_add_and_get_summary(self) -> None:
        repo = FakeDashboardWidgetRepository()
        company_id = uuid4()

        added = AddWidget(repo).execute(
            company_id=company_id,
            title="Revenue",
            widget_type=WidgetType.KPI_CARD,
            position=0,
            config={"color": "blue"},
        )
        assert added.title == "Revenue"

        summary = GetDashboardSummary(repo).execute(company_id=company_id)
        assert len(summary.widgets) == 1
        assert summary.widgets[0].id == added.id
        assert summary.metrics["total_products"] == 1500

    def test_update_and_remove_widget(self) -> None:
        repo = FakeDashboardWidgetRepository()
        company_id = uuid4()

        added = AddWidget(repo).execute(
            company_id=company_id,
            title="Old",
            widget_type=WidgetType.TABLE,
            position=1,
        )

        updated = UpdateWidget(repo).execute(
            company_id=company_id, widget_id=added.id, title="New"
        )
        assert updated.title == "New"

        RemoveWidget(repo).execute(company_id=company_id, widget_id=added.id)
        assert repo.get_by_id(added.id) is None

    def test_reorder_widgets(self) -> None:
        repo = FakeDashboardWidgetRepository()
        company_id = uuid4()

        w1 = AddWidget(repo).execute(
            company_id=company_id,
            title="W1",
            widget_type=WidgetType.KPI_CARD,
            position=0,
        )
        w2 = AddWidget(repo).execute(
            company_id=company_id,
            title="W2",
            widget_type=WidgetType.KPI_CARD,
            position=1,
        )

        ReorderWidgets(repo).execute(
            company_id=company_id, position_updates={w1.id: 1, w2.id: 0}
        )

        summary = GetDashboardSummary(repo).execute(company_id=company_id)
        assert summary.widgets[0].id == w2.id
        assert summary.widgets[1].id == w1.id
