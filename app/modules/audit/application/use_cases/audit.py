"""Audit module — application use cases."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.modules.audit.application.dtos import AuditEventDTO
from app.modules.audit.domain.entities import AuditEvent
from app.modules.audit.domain.repositories import AuditEventRepository


class RecordAuditEvent:
    def __init__(self, audit_repo: AuditEventRepository) -> None:
        self._audit_repo = audit_repo

    def execute(
        self,
        company_id: UUID,
        action: str,
        resource_type: str,
        user_id: UUID | None = None,
        resource_id: UUID | None = None,
        event_metadata: dict[str, Any] | None = None,
    ) -> AuditEventDTO:
        entity = AuditEvent(
            company_id=company_id,
            action=action,
            resource_type=resource_type,
            occurred_at=datetime.now(timezone.utc),
            user_id=user_id,
            resource_id=resource_id,
            event_metadata=event_metadata or {},
        )
        saved = self._audit_repo.add(entity)
        return AuditEventDTO.from_entity(saved)


class ListAuditEvents:
    def __init__(self, audit_repo: AuditEventRepository) -> None:
        self._audit_repo = audit_repo

    def execute(
        self,
        company_id: UUID,
        resource_type: str | None = None,
        user_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[AuditEventDTO]:
        entities = self._audit_repo.list_by_company(
            company_id=company_id,
            resource_type=resource_type,
            user_id=user_id,
            offset=offset,
            limit=limit,
        )
        return [AuditEventDTO.from_entity(e) for e in entities]
