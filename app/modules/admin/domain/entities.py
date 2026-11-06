"""Admin module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class SystemSetting:
    """A global system configuration setting."""

    key: str
    value: dict[str, Any]
    updated_at: datetime
    updated_by: UUID | None = None
    id: UUID | None = None
