"""Notifications module domain — exceptions."""
from __future__ import annotations

from uuid import UUID

from app.shared.domain.errors import NotFoundError, ValidationError


class NotificationNotFoundError(NotFoundError):
    def __init__(self, notification_id: UUID) -> None:
        super().__init__(
            message="No encontramos esa notificación. Actualiza la página e inténtalo de nuevo.",
            details={"notification_id": str(notification_id)},
        )


class InvalidNotificationStateError(ValidationError):
    pass
