"""Dashboard module — dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.dashboard.domain.repositories import DashboardWidgetRepository
from app.modules.dashboard.infrastructure.persistence.repositories import (
    SqlDashboardWidgetRepository,
)
from app.shared.presentation.deps import get_db


def get_dashboard_repository(
    db: Annotated[Session, Depends(get_db, scope="function")],
) -> DashboardWidgetRepository:
    """Dependency provider for DashboardWidgetRepository."""
    return SqlDashboardWidgetRepository(db)
