"""Notifications module — HTTP schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.notifications.application.dtos import NotificationDTO
from app.modules.notifications.domain.enums import NotificationSeverity


class NotificationResponse(NotificationDTO):
    """Response schema for a single notification."""
    pass


class CreateNotificationRequest(BaseModel):
    """Request schema to create a notification manually (usually for testing/system)."""
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1, max_length=1000)
    severity: NotificationSeverity = NotificationSeverity.INFO


class UnreadCountResponse(BaseModel):
    """How many notices of the company are still unread."""
    unread: int


class MarkAllReadResponse(BaseModel):
    message: str
    #: How many notices went from unread to read.
    updated: int


# Placeholders for existing endpoints we don't fully implement yet
class NotificationPreferencesResponse(BaseModel):
    message: str
    module: str
    action: str

class UpdateNotificationPreferencesRequest(BaseModel):
    pass
