"""Audit module — application DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.audit.domain.entities import AuditEvent


class AuditEventDTO(BaseModel):
    id: UUID
    company_id: UUID
    action: str
    resource_type: str
    occurred_at: datetime
    user_id: UUID | None
    resource_id: UUID | None
    event_metadata: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_entity(cls, entity: AuditEvent) -> AuditEventDTO:
        if entity.id is None:
            raise ValueError("Entity must have an id to create DTO")
        return cls(
            id=entity.id,
            company_id=entity.company_id,
            action=entity.action,
            resource_type=entity.resource_type,
            occurred_at=entity.occurred_at,
            user_id=entity.user_id,
            resource_id=entity.resource_id,
            event_metadata=entity.event_metadata,
        )
