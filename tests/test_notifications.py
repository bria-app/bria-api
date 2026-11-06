"""Tests for Notifications module."""
from __future__ import annotations

from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.modules.notifications.application.use_cases.notification import (
    CreateNotification,
    ListNotifications,
    MarkRead,
)
from app.modules.notifications.domain.entities import Notification
from app.modules.notifications.domain.enums import NotificationSeverity
from app.modules.notifications.domain.exceptions import NotificationNotFoundError
from app.shared.presentation.deps import get_current_user


# --- In-memory fake repository -----------------------------------------------
class FakeNotificationRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, Notification] = {}

    def get_by_id(self, notification_id: UUID) -> Notification | None:
        return self._store.get(notification_id)

    def list_by_company(
        self,
        company_id: UUID,
        unread_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Notification]:
        rows = [n for n in self._store.values() if n.company_id == company_id]
        if unread_only:
            rows = [n for n in rows if not n.is_read]
        # Sort descending by created_at
        rows.sort(key=lambda x: x.created_at, reverse=True)
        return rows[offset : offset + limit]

    def add(self, notification: Notification) -> Notification:
        if notification.id is None:
            notification.id = uuid4()
        self._store[notification.id] = notification
        return notification

    def update(self, notification: Notification) -> Notification:
        assert notification.id is not None
        self._store[notification.id] = notification
        return notification

    def delete(self, notification_id: UUID) -> bool:
        return self._store.pop(notification_id, None) is not None


# --- Use-case unit tests -----------------------------------------------------
class TestNotificationUseCases:
    def test_create_and_list_notifications(self) -> None:
        repo = FakeNotificationRepository()
        company_id = uuid4()

        created = CreateNotification(repo).execute(
            company_id=company_id,
            title="Stockout Warning",
            message="Item X is out of stock",
            severity=NotificationSeverity.WARNING,
        )
        assert created.title == "Stockout Warning"
        assert created.is_read is False

        notifications = ListNotifications(repo).execute(company_id=company_id)
        assert len(notifications) == 1
        assert notifications[0].id == created.id

    def test_mark_read(self) -> None:
        repo = FakeNotificationRepository()
        company_id = uuid4()

        created = CreateNotification(repo).execute(
            company_id=company_id,
            title="Info",
            message="Hello",
            severity=NotificationSeverity.INFO,
        )
        MarkRead(repo).execute(company_id=company_id, notification_id=created.id)

        # Unread only should be empty
        unread = ListNotifications(repo).execute(company_id=company_id, unread_only=True)
        assert len(unread) == 0

    def test_mark_read_wrong_company_raises(self) -> None:
        repo = FakeNotificationRepository()
        company_id = uuid4()

        created = CreateNotification(repo).execute(
            company_id=company_id,
            title="Info",
            message="Hello",
            severity=NotificationSeverity.INFO,
        )
        with pytest.raises(NotificationNotFoundError):
            MarkRead(repo).execute(company_id=uuid4(), notification_id=created.id)


# --- Endpoint integration tests (SQLite) ------------------------------------
@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    from app.main import app
    from app.shared.infrastructure.database import Base, get_db

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSession()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    
    # We mock get_current_user to return a fake authenticated user to bypass auth
    from app.shared.presentation.deps import AuthenticatedUser
    fake_user = AuthenticatedUser(
        user_id=uuid4(),
        company_id=uuid4(),
        role="owner",
    )
    app.dependency_overrides[get_current_user] = lambda: fake_user

    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


class TestNotificationsEndpoints:
    def test_create_list_flow(self, client: TestClient) -> None:
        # We need the company_id generated by the fake user
        from app.main import app
        
        # Get the mocked user
        user = app.dependency_overrides[get_current_user]()
        company_id = str(user.company_id)

        # Create
        create_resp = client.post(
            f"/api/v1/companies/{company_id}/notifications",
            json={
                "title": "System Alert",
                "message": "CPU High",
                "severity": "critical"
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        notif_id = create_resp.json()["id"]

        # List
        list_resp = client.get(f"/api/v1/companies/{company_id}/notifications")
        assert list_resp.status_code == 200, list_resp.text
        items = list_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == notif_id
        assert items[0]["is_read"] is False

        # Mark read
        mark_resp = client.post(f"/api/v1/companies/{company_id}/notifications/{notif_id}/mark-read")
        assert mark_resp.status_code == 200, mark_resp.text

        # List unread only
        unread_resp = client.get(f"/api/v1/companies/{company_id}/notifications?unread_only=true")
        assert unread_resp.status_code == 200, unread_resp.text
        assert len(unread_resp.json()["items"]) == 0
