"""Notifications module — application use cases."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.modules.notifications.application.dtos import NotificationDTO
from app.modules.notifications.domain.entities import Notification
from app.modules.notifications.domain.enums import NotificationSeverity
from app.modules.notifications.domain.exceptions import NotificationNotFoundError
from app.modules.notifications.domain.repositories import NotificationRepository


class CreateNotification:
    def __init__(self, notification_repo: NotificationRepository) -> None:
        self._notification_repo = notification_repo

    def execute(
        self,
        company_id: UUID,
        title: str,
        message: str,
        severity: NotificationSeverity,
    ) -> NotificationDTO:
        entity = Notification(
            company_id=company_id,
            title=title,
            message=message,
            severity=severity,
            created_at=datetime.now(timezone.utc),
        )
        saved = self._notification_repo.add(entity)
        return NotificationDTO.from_entity(saved)


class ListNotifications:
    def __init__(self, notification_repo: NotificationRepository) -> None:
        self._notification_repo = notification_repo

    def execute(
        self,
        company_id: UUID,
        unread_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> list[NotificationDTO]:
        entities = self._notification_repo.list_by_company(
            company_id=company_id,
            unread_only=unread_only,
            offset=offset,
            limit=limit,
        )
        return [NotificationDTO.from_entity(e) for e in entities]


class CountNotifications:
    """How many notices the company has (all, or only the unread ones)."""

    def __init__(self, notification_repo: NotificationRepository) -> None:
        self._notification_repo = notification_repo

    def execute(self, company_id: UUID, unread_only: bool = False) -> int:
        return self._notification_repo.count_by_company(company_id, unread_only=unread_only)


class MarkAllRead:
    """Marks as read every unread notice of the caller's company; returns how many changed."""

    def __init__(self, notification_repo: NotificationRepository) -> None:
        self._notification_repo = notification_repo

    def execute(self, company_id: UUID) -> int:
        return self._notification_repo.mark_all_read(company_id)


class GetNotification:
    def __init__(self, notification_repo: NotificationRepository) -> None:
        self._notification_repo = notification_repo

    def execute(self, company_id: UUID, notification_id: UUID) -> NotificationDTO:
        entity = self._notification_repo.get_by_id(notification_id)
        if not entity or entity.company_id != company_id:
            raise NotificationNotFoundError(notification_id)
        return NotificationDTO.from_entity(entity)


class MarkRead:
    def __init__(self, notification_repo: NotificationRepository) -> None:
        self._notification_repo = notification_repo

    def execute(self, company_id: UUID, notification_id: UUID) -> None:
        entity = self._notification_repo.get_by_id(notification_id)
        if not entity or entity.company_id != company_id:
            raise NotificationNotFoundError(notification_id)
        
        # Don't fail if already read, just idempotently return or mark it.
        # But domain raises an error if already read. We can catch it or let it propagate.
        # Let's check first to make it idempotent in the application layer.
        if not entity.is_read:
            entity.mark_read()
            self._notification_repo.update(entity)


class DeleteNotification:
    def __init__(self, notification_repo: NotificationRepository) -> None:
        self._notification_repo = notification_repo

    def execute(self, company_id: UUID, notification_id: UUID) -> None:
        entity = self._notification_repo.get_by_id(notification_id)
        if not entity or entity.company_id != company_id:
            raise NotificationNotFoundError(notification_id)
        
        self._notification_repo.delete(notification_id)
