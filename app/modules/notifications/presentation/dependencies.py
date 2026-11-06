"""Notifications module — dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.notifications.domain.repositories import NotificationRepository
from app.modules.notifications.infrastructure.persistence.repositories import (
    SqlNotificationRepository,
)
from app.shared.presentation.deps import get_db


def get_notification_repository(
    db: Annotated[Session, Depends(get_db, scope="function")],
) -> NotificationRepository:
    """Dependency provider for NotificationRepository."""
    return SqlNotificationRepository(db)
