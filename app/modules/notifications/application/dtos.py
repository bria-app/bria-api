"""Notifications module — application DTOs."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.notifications.domain.entities import Notification
from app.modules.notifications.domain.enums import NotificationSeverity


class NotificationDTO(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    message: str
    severity: NotificationSeverity
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_entity(cls, entity: Notification) -> NotificationDTO:
        if entity.id is None:
            raise ValueError("Entity must have an id to create DTO")
        return cls(
            id=entity.id,
            company_id=entity.company_id,
            title=entity.title,
            message=entity.message,
            severity=entity.severity,
            is_read=entity.is_read,
            created_at=entity.created_at,
        )
