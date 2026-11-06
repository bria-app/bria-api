"""Admin module — application DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.admin.domain.entities import SystemSetting


class SystemSettingDTO(BaseModel):
    id: UUID
    key: str
    value: dict[str, Any]
    updated_at: datetime
    updated_by: UUID | None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_entity(cls, entity: SystemSetting) -> SystemSettingDTO:
        if entity.id is None:
            raise ValueError("Entity must have an id to create DTO")
        return cls(
            id=entity.id,
            key=entity.key,
            value=entity.value,
            updated_at=entity.updated_at,
            updated_by=entity.updated_by,
        )
