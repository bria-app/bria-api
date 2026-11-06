"""Admin module domain — repository ports."""
from __future__ import annotations

from typing import Protocol

from app.modules.admin.domain.entities import SystemSetting


class SystemSettingsRepository(Protocol):
    """Port for SystemSettings persistence."""

    def get_by_key(self, key: str) -> SystemSetting | None: ...
    def get_all(self) -> list[SystemSetting]: ...
    def set_setting(self, setting: SystemSetting) -> SystemSetting: ...
