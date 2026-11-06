"""Reports module — SQLAlchemy repository implementation."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.reports.domain.entities import Report
from app.modules.reports.domain.exceptions import ReportNotFoundError
from app.modules.reports.infrastructure.persistence.mappers import (
    report_to_entity,
    report_to_model,
)
from app.modules.reports.infrastructure.persistence.models import ReportModel


class SqlReportRepository:
    """SQLAlchemy implementation of ReportRepository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, report_id: UUID) -> Report | None:
        model = self._session.get(ReportModel, report_id)
        return report_to_entity(model) if model else None

    def list_by_company(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Report]:
        rows = self._session.execute(
            select(ReportModel)
            .where(ReportModel.company_id == company_id)
            .order_by(ReportModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).scalars().all()
        return [report_to_entity(m) for m in rows]

    def add(self, report: Report) -> Report:
        model = report_to_model(report)
        self._session.add(model)
        self._session.flush()
        return report_to_entity(model)

    def update(self, report: Report) -> Report:
        model = self._session.get(ReportModel, report.id)
        if model is None:
            raise ReportNotFoundError(report.id)  # type: ignore[arg-type]
        
        model.company_id = report.company_id
        model.title = report.title
        model.report_type = report.report_type.value
        model.status = report.status.value
        model.file_path = report.file_path
        model.params = report.params
        
        self._session.flush()
        return report_to_entity(model)

    def delete(self, report_id: UUID) -> bool:
        model = self._session.get(ReportModel, report_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True
