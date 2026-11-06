"""Audit module — SQLAlchemy repository implementation."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.domain.entities import AuditEvent
from app.modules.audit.infrastructure.persistence.mappers import (
    audit_event_to_entity,
    audit_event_to_model,
)
from app.modules.audit.infrastructure.persistence.models import AuditEventModel


class SqlAuditEventRepository:
    """SQLAlchemy implementation of AuditEventRepository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, event_id: UUID) -> AuditEvent | None:
        model = self._session.get(AuditEventModel, event_id)
        return audit_event_to_entity(model) if model else None

    def list_by_company(
        self,
        company_id: UUID,
        resource_type: str | None = None,
        user_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[AuditEvent]:
        stmt = select(AuditEventModel).where(
            AuditEventModel.company_id == company_id
        )
        if resource_type:
            stmt = stmt.where(AuditEventModel.resource_type == resource_type)
        if user_id:
            stmt = stmt.where(AuditEventModel.user_id == user_id)
        
        # Order by occurred_at descending (newest first)
        stmt = stmt.order_by(AuditEventModel.occurred_at.desc())
        stmt = stmt.offset(offset).limit(limit)

        rows = self._session.execute(stmt).scalars().all()
        return [audit_event_to_entity(m) for m in rows]

    def add(self, event: AuditEvent) -> AuditEvent:
        model = audit_event_to_model(event)
        self._session.add(model)
        self._session.flush()
        return audit_event_to_entity(model)
