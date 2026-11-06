"""Notifications module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.notifications.domain.enums import NotificationSeverity
from app.modules.notifications.domain.exceptions import InvalidNotificationStateError


@dataclass
class Notification:
    """An alert or message for a company."""

    company_id: UUID
    title: str
    message: str
    severity: NotificationSeverity
    created_at: datetime
    is_read: bool = False
    id: UUID | None = None

    def mark_read(self) -> None:
        """Mark this notification as read."""
        if self.is_read:
            raise InvalidNotificationStateError(
                message="Esta notificación ya está marcada como leída."
            )
        self.is_read = True
