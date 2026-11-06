"""Tests for Admin module."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.admin.application.use_cases.admin import (
    GetSystemSettings,
    UpdateSystemSetting,
)
from app.modules.admin.domain.entities import SystemSetting
from app.modules.admin.domain.exceptions import SettingNotFoundError


class FakeSystemSettingsRepository:
    def __init__(self) -> None:
        self._store: dict[str, SystemSetting] = {}

    def get_by_key(self, key: str) -> SystemSetting | None:
        return self._store.get(key)

    def get_all(self) -> list[SystemSetting]:
        rows = list(self._store.values())
        rows.sort(key=lambda s: s.key)
        return rows

    def set_setting(self, setting: SystemSetting) -> SystemSetting:
        if setting.id is None:
            setting.id = uuid4()
        self._store[setting.key] = setting
        return setting


class TestAdminUseCases:
    def test_update_and_get_settings(self) -> None:
        repo = FakeSystemSettingsRepository()

        # Update (creates)
        updated = UpdateSystemSetting(repo).execute(
            key="maintenance_mode",
            value={"enabled": True},
            updated_by=uuid4(),
        )
        assert updated.key == "maintenance_mode"
        assert updated.value["enabled"] is True

        # Get all
        all_settings = GetSystemSettings(repo).execute()
        assert len(all_settings) == 1

        # Get single
        single = GetSystemSettings(repo).execute(key="maintenance_mode")
        assert len(single) == 1
        assert single[0].value["enabled"] is True

    def test_get_unknown_setting_raises(self) -> None:
        repo = FakeSystemSettingsRepository()
        with pytest.raises(SettingNotFoundError):
            GetSystemSettings(repo).execute(key="unknown_key")
