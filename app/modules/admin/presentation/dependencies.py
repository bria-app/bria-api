"""Admin module — dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.admin.domain.repositories import SystemSettingsRepository
from app.modules.admin.infrastructure.persistence.repositories import (
    SqlSystemSettingsRepository,
)
from app.shared.presentation.deps import get_db


def get_system_settings_repository(
    db: Annotated[Session, Depends(get_db, scope="function")],
) -> SystemSettingsRepository:
    """Dependency provider for SystemSettingsRepository."""
    return SqlSystemSettingsRepository(db)
