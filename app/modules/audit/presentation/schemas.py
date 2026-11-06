"""Audit module — HTTP schemas."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.audit.application.dtos import AuditEventDTO


class AuditEventResponse(AuditEventDTO):
    """Response schema for an audit event."""
    pass


class CreateAuditEventRequest(BaseModel):
    """Request schema for manually recording an audit event (for testing/integration)."""
    action: str = Field(..., min_length=1, max_length=255)
    resource_type: str = Field(..., min_length=1, max_length=100)
    resource_id: UUID | None = None
    event_metadata: dict[str, Any] = Field(default_factory=dict)
