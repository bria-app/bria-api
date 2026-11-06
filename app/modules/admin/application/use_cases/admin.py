"""Admin module — application use cases."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.modules.admin.application.dtos import SystemSettingDTO
from app.modules.admin.domain.entities import SystemSetting
from app.modules.admin.domain.exceptions import SettingNotFoundError
from app.modules.admin.domain.repositories import SystemSettingsRepository


class GetSystemSettings:
    def __init__(self, settings_repo: SystemSettingsRepository) -> None:
        self._settings_repo = settings_repo

    def execute(self, key: str | None = None) -> list[SystemSettingDTO]:
        if key:
            entity = self._settings_repo.get_by_key(key)
            if not entity:
                raise SettingNotFoundError(key)
            return [SystemSettingDTO.from_entity(entity)]
        
        entities = self._settings_repo.get_all()
        return [SystemSettingDTO.from_entity(e) for e in entities]


class UpdateSystemSetting:
    def __init__(self, settings_repo: SystemSettingsRepository) -> None:
        self._settings_repo = settings_repo

    def execute(
        self,
        key: str,
        value: dict[str, Any],
        updated_by: UUID | None = None,
    ) -> SystemSettingDTO:
        entity = SystemSetting(
            key=key,
            value=value,
            updated_at=datetime.now(timezone.utc),
            updated_by=updated_by,
        )
        saved = self._settings_repo.set_setting(entity)
        return SystemSettingDTO.from_entity(saved)
