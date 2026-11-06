"""Admin module — mappers."""
from __future__ import annotations

from app.modules.admin.domain.entities import SystemSetting
from app.modules.admin.infrastructure.persistence.models import SystemSettingModel


def system_setting_to_entity(model: SystemSettingModel) -> SystemSetting:
    return SystemSetting(
        id=model.id,
        key=model.key,
        value=model.value or {},
        updated_at=model.updated_at,
        updated_by=model.updated_by,
    )


def system_setting_to_model(entity: SystemSetting) -> SystemSettingModel:
    return SystemSettingModel(
        id=entity.id,
        key=entity.key,
        value=entity.value,
        updated_by=entity.updated_by,
    )
