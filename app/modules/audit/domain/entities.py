"""Audit module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class AuditEvent:
    """An immutable, append-only record of a system event."""

    company_id: UUID
    action: str
    resource_type: str
    occurred_at: datetime
    user_id: UUID | None = None
    resource_id: UUID | None = None
    event_metadata: dict[str, Any] = field(default_factory=dict)
    id: UUID | None = None
