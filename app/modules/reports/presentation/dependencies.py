"""Reports module — dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.reports.domain.repositories import ReportRepository
from app.modules.reports.infrastructure.persistence.repositories import (
    SqlReportRepository,
)
from app.shared.presentation.deps import get_db


def get_report_repository(
    db: Annotated[Session, Depends(get_db, scope="function")],
) -> ReportRepository:
    """Dependency provider for ReportRepository."""
    return SqlReportRepository(db)
