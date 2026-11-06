"""Reports module — mappers."""
from __future__ import annotations

from app.modules.reports.domain.entities import Report
from app.modules.reports.domain.enums import ReportStatus, ReportType
from app.modules.reports.infrastructure.persistence.models import ReportModel


def report_to_entity(model: ReportModel) -> Report:
    return Report(
        id=model.id,
        company_id=model.company_id,
        title=model.title,
        report_type=ReportType(model.report_type),
        status=ReportStatus(model.status),
        file_path=model.file_path,
        params=model.params or {},
        created_at=model.created_at,
    )


def report_to_model(entity: Report) -> ReportModel:
    model = ReportModel(
        id=entity.id,
        company_id=entity.company_id,
        title=entity.title,
        report_type=entity.report_type.value,
        status=entity.status.value,
        file_path=entity.file_path,
        params=entity.params,
    )
    # Left unset on new rows so the database default stamps it (an explicit None would not).
    if entity.created_at is not None:
        model.created_at = entity.created_at
    return model
