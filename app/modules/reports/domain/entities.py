"""Reports module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID
from typing import Any

from app.modules.reports.domain.enums import ReportStatus, ReportType
from app.modules.reports.domain.exceptions import InvalidReportStateError


@dataclass
class Report:
    """A generated report."""

    company_id: UUID
    title: str
    report_type: ReportType
    status: ReportStatus = ReportStatus.PENDING
    file_path: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    id: UUID | None = None
    #: When it was asked for (set by the database on insert).
    created_at: datetime | None = None

    def mark_ready(self, file_path: str) -> None:
        if self.status == ReportStatus.READY:
            raise InvalidReportStateError(message="Este reporte ya está listo. Descárgalo.")
        self.status = ReportStatus.READY
        self.file_path = file_path

    def mark_failed(self) -> None:
        if self.status != ReportStatus.PENDING:
            raise InvalidReportStateError(
                message=f"El reporte no puede pasar a fallido desde «{self.status}»."
            )
        self.status = ReportStatus.FAILED
