"""Admin module — SQLAlchemy repository implementation."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.admin.domain.entities import SystemSetting
from app.modules.admin.infrastructure.persistence.mappers import (
    system_setting_to_entity,
    system_setting_to_model,
)
from app.modules.admin.infrastructure.persistence.models import SystemSettingModel


class SqlSystemSettingsRepository:
    """SQLAlchemy implementation of SystemSettingsRepository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_key(self, key: str) -> SystemSetting | None:
        model = self._session.execute(
            select(SystemSettingModel).where(SystemSettingModel.key == key)
        ).scalar_one_or_none()
        return system_setting_to_entity(model) if model else None

    def get_all(self) -> list[SystemSetting]:
        rows = self._session.execute(
            select(SystemSettingModel).order_by(SystemSettingModel.key)
        ).scalars().all()
        return [system_setting_to_entity(m) for m in rows]

    def set_setting(self, setting: SystemSetting) -> SystemSetting:
        model = self._session.execute(
            select(SystemSettingModel).where(SystemSettingModel.key == setting.key)
        ).scalar_one_or_none()

        if model is None:
            # Create
            model = system_setting_to_model(setting)
            self._session.add(model)
        else:
            # Update
            model.value = setting.value
            model.updated_by = setting.updated_by
            # updated_at is handled by TimestampMixin

        self._session.flush()
        return system_setting_to_entity(model)
