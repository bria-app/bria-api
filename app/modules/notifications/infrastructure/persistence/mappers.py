"""Notifications module — mappers."""
from __future__ import annotations

from app.modules.notifications.domain.entities import Notification
from app.modules.notifications.domain.enums import NotificationSeverity
from app.modules.notifications.infrastructure.persistence.models import NotificationModel


def notification_to_entity(model: NotificationModel) -> Notification:
    return Notification(
        id=model.id,
        company_id=model.company_id,
        title=model.title,
        message=model.message,
        severity=NotificationSeverity(model.severity),
        is_read=model.is_read,
        created_at=model.created_at,
    )


def notification_to_model(entity: Notification) -> NotificationModel:
    return NotificationModel(
        id=entity.id,
        company_id=entity.company_id,
        title=entity.title,
        message=entity.message,
        severity=entity.severity.value,
        is_read=entity.is_read,
        created_at=entity.created_at,
    )
