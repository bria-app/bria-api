"""Notifications module — SQLAlchemy repository implementation."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.notifications.domain.entities import Notification
from app.modules.notifications.domain.exceptions import NotificationNotFoundError
from app.modules.notifications.infrastructure.persistence.mappers import (
    notification_to_entity,
    notification_to_model,
)
from app.modules.notifications.infrastructure.persistence.models import (
    NotificationModel,
)


class SqlNotificationRepository:
    """SQLAlchemy implementation of NotificationRepository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, notification_id: UUID) -> Notification | None:
        model = self._session.get(NotificationModel, notification_id)
        return notification_to_entity(model) if model else None

    def list_by_company(
        self,
        company_id: UUID,
        unread_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Notification]:
        stmt = select(NotificationModel).where(
            NotificationModel.company_id == company_id
        )
        if unread_only:
            stmt = stmt.where(NotificationModel.is_read.is_(False))
        
        # Order by created_at descending (newest first)
        stmt = stmt.order_by(NotificationModel.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)

        rows = self._session.execute(stmt).scalars().all()
        return [notification_to_entity(m) for m in rows]

    def count_by_company(self, company_id: UUID, unread_only: bool = False) -> int:
        stmt = select(func.count(NotificationModel.id)).where(
            NotificationModel.company_id == company_id
        )
        if unread_only:
            stmt = stmt.where(NotificationModel.is_read.is_(False))
        return int(self._session.execute(stmt).scalar_one())

    def mark_all_read(self, company_id: UUID) -> int:
        rows = self._session.execute(
            select(NotificationModel).where(
                NotificationModel.company_id == company_id,
                NotificationModel.is_read.is_(False),
            )
        ).scalars().all()
        for model in rows:
            model.is_read = True
        if rows:
            self._session.flush()
        return len(rows)

    def add(self, notification: Notification) -> Notification:
        model = notification_to_model(notification)
        self._session.add(model)
        self._session.flush()
        return notification_to_entity(model)

    def update(self, notification: Notification) -> Notification:
        model = self._session.get(NotificationModel, notification.id)
        if model is None:
            raise NotificationNotFoundError(notification.id)  # type: ignore[arg-type]
        
        model.company_id = notification.company_id
        model.title = notification.title
        model.message = notification.message
        model.severity = notification.severity.value
        model.is_read = notification.is_read
        model.created_at = notification.created_at
        
        self._session.flush()
        return notification_to_entity(model)

    def delete(self, notification_id: UUID) -> bool:
        model = self._session.get(NotificationModel, notification_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True
