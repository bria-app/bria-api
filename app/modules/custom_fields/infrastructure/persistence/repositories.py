"""Custom fields module — SQL repositories."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.custom_fields.domain.entities import CustomFieldDefinition
from app.modules.custom_fields.infrastructure.persistence.models import (
    CustomFieldDefinitionModel,
    UiPreferenceModel,
)


def _to_entity(m: CustomFieldDefinitionModel) -> CustomFieldDefinition:
    return CustomFieldDefinition(
        id=m.id,
        company_id=m.company_id,
        entity=m.entity,
        key=m.key,
        label=m.label,
        field_type=m.field_type,
        options=list(m.options or []),
        position=m.position,
        is_visible=m.is_visible,
        is_required=m.is_required,
        category_ids=list(m.category_ids or []),
        rules=dict(m.rules) if isinstance(m.rules, dict) else {},
    )


class SqlCustomFieldRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self, company_id: UUID, entity: str | None = None) -> list[CustomFieldDefinition]:
        stmt = select(CustomFieldDefinitionModel).where(
            CustomFieldDefinitionModel.company_id == company_id
        )
        if entity:
            stmt = stmt.where(CustomFieldDefinitionModel.entity == entity)
        stmt = stmt.order_by(CustomFieldDefinitionModel.position, CustomFieldDefinitionModel.created_at)
        return [_to_entity(m) for m in self._session.scalars(stmt)]

    def get(self, field_id: UUID) -> CustomFieldDefinition | None:
        m = self._session.get(CustomFieldDefinitionModel, field_id)
        return _to_entity(m) if m else None

    def get_by_key(self, company_id: UUID, entity: str, key: str) -> CustomFieldDefinition | None:
        m = self._session.scalars(
            select(CustomFieldDefinitionModel).where(
                CustomFieldDefinitionModel.company_id == company_id,
                CustomFieldDefinitionModel.entity == entity,
                CustomFieldDefinitionModel.key == key,
            )
        ).first()
        return _to_entity(m) if m else None

    def next_position(self, company_id: UUID, entity: str) -> int:
        current = self._session.execute(
            select(func.max(CustomFieldDefinitionModel.position)).where(
                CustomFieldDefinitionModel.company_id == company_id,
                CustomFieldDefinitionModel.entity == entity,
            )
        ).scalar_one()
        return (current or 0) + 1

    def add(self, field: CustomFieldDefinition) -> CustomFieldDefinition:
        m = CustomFieldDefinitionModel(
            company_id=field.company_id,
            entity=field.entity,
            key=field.key,
            label=field.label,
            field_type=field.field_type,
            options=field.options,
            position=field.position,
            is_visible=field.is_visible,
            is_required=field.is_required,
            category_ids=field.category_ids,
            rules=dict(field.rules or {}),
        )
        self._session.add(m)
        self._session.flush()
        return _to_entity(m)

    def update(self, field: CustomFieldDefinition) -> CustomFieldDefinition:
        m = self._session.get(CustomFieldDefinitionModel, field.id)
        assert m is not None
        m.label = field.label
        m.field_type = field.field_type
        m.options = field.options
        m.position = field.position
        m.is_visible = field.is_visible
        m.is_required = field.is_required
        m.category_ids = list(field.category_ids)
        m.rules = dict(field.rules or {})
        self._session.flush()
        return _to_entity(m)

    def delete(self, field_id: UUID) -> None:
        m = self._session.get(CustomFieldDefinitionModel, field_id)
        if m is not None:
            self._session.delete(m)
            self._session.flush()


class SqlUiPreferenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, company_id: UUID, key: str) -> Any | None:
        m = self._session.scalars(
            select(UiPreferenceModel).where(
                UiPreferenceModel.company_id == company_id, UiPreferenceModel.key == key
            )
        ).first()
        return m.value if m else None

    def put(self, company_id: UUID, key: str, value: Any) -> Any:
        m = self._session.scalars(
            select(UiPreferenceModel).where(
                UiPreferenceModel.company_id == company_id, UiPreferenceModel.key == key
            )
        ).first()
        if m is None:
            m = UiPreferenceModel(company_id=company_id, key=key, value=value)
            self._session.add(m)
        else:
            m.value = value
        self._session.flush()
        return m.value
