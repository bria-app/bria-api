"""Audit module domain — repository ports."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.audit.domain.entities import AuditEvent


class AuditEventRepository(Protocol):
    """Port for AuditEvent persistence (append-only)."""

    def get_by_id(self, event_id: UUID) -> AuditEvent | None: ...
    
    def list_by_company(
        self,
        company_id: UUID,
        resource_type: str | None = None,
        user_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[AuditEvent]: ...
    
    def add(self, event: AuditEvent) -> AuditEvent: ...
