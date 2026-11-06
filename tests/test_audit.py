"""Tests for Audit module."""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.audit.application.use_cases.audit import (
    ListAuditEvents,
    RecordAuditEvent,
)
from app.modules.audit.domain.entities import AuditEvent


class FakeAuditEventRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, AuditEvent] = {}

    def get_by_id(self, event_id: UUID) -> AuditEvent | None:
        return self._store.get(event_id)

    def list_by_company(
        self,
        company_id: UUID,
        resource_type: str | None = None,
        user_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[AuditEvent]:
        rows = [e for e in self._store.values() if e.company_id == company_id]
        if resource_type:
            rows = [e for e in rows if e.resource_type == resource_type]
        if user_id:
            rows = [e for e in rows if e.user_id == user_id]
        
        # sort by occurred_at desc
        rows.sort(key=lambda e: e.occurred_at, reverse=True)
        return rows[offset : offset + limit]

    def add(self, event: AuditEvent) -> AuditEvent:
        if event.id is None:
            object.__setattr__(event, "id", uuid4())
        assert event.id is not None
        self._store[event.id] = event
        return event


class TestAuditUseCases:
    def test_record_and_list_audit_events(self) -> None:
        repo = FakeAuditEventRepository()
        company_id = uuid4()
        user_id = uuid4()

        # Record
        recorded = RecordAuditEvent(repo).execute(
            company_id=company_id,
            action="update_product",
            resource_type="product",
            user_id=user_id,
            resource_id=uuid4(),
            event_metadata={"old": 1, "new": 2},
        )
        assert recorded.action == "update_product"

        # List all
        events = ListAuditEvents(repo).execute(company_id=company_id)
        assert len(events) == 1

        # List by resource type
        events = ListAuditEvents(repo).execute(
            company_id=company_id, resource_type="product"
        )
        assert len(events) == 1

        # List by unknown resource type
        events = ListAuditEvents(repo).execute(
            company_id=company_id, resource_type="user"
        )
        assert len(events) == 0

        # List by user ID
        events = ListAuditEvents(repo).execute(company_id=company_id, user_id=user_id)
        assert len(events) == 1
