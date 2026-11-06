"""Notifications module domain layer."""
from app.modules.notifications.domain.entities import Notification
from app.modules.notifications.domain.enums import NotificationSeverity
from app.modules.notifications.domain.exceptions import (
    InvalidNotificationStateError,
    NotificationNotFoundError,
)
from app.modules.notifications.domain.repositories import NotificationRepository

__all__ = [
    "InvalidNotificationStateError",
    "Notification",
    "NotificationNotFoundError",
    "NotificationRepository",
    "NotificationSeverity",
]
