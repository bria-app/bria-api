"""Reports module domain — repository ports."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.reports.domain.entities import Report


class ReportRepository(Protocol):
    """Port for Report persistence."""

    def get_by_id(self, report_id: UUID) -> Report | None: ...
    def list_by_company(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Report]: ...
    def add(self, report: Report) -> Report: ...
    def update(self, report: Report) -> Report: ...
    def delete(self, report_id: UUID) -> bool: ...
