"""Audit module — mappers."""
from __future__ import annotations

from app.modules.audit.domain.entities import AuditEvent
from app.modules.audit.infrastructure.persistence.models import AuditEventModel


def audit_event_to_entity(model: AuditEventModel) -> AuditEvent:
    return AuditEvent(
        id=model.id,
        company_id=model.company_id,
        user_id=model.user_id,
        action=model.action,
        resource_type=model.resource_type,
        resource_id=model.resource_id,
        event_metadata=model.event_metadata or {},
        occurred_at=model.occurred_at,
    )


def audit_event_to_model(entity: AuditEvent) -> AuditEventModel:
    return AuditEventModel(
        id=entity.id,
        company_id=entity.company_id,
        user_id=entity.user_id,
        action=entity.action,
        resource_type=entity.resource_type,
        resource_id=entity.resource_id,
        event_metadata=entity.event_metadata,
        occurred_at=entity.occurred_at,
    )
