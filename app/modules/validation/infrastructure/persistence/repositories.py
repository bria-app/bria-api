"""Validation module — SQLAlchemy repository implementation."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.validation.domain.entities import ValidationRule
from app.modules.validation.domain.exceptions import ValidationRuleNotFoundError
from app.modules.validation.infrastructure.persistence.mappers import (
    validation_rule_to_entity,
    validation_rule_to_model,
)
from app.modules.validation.infrastructure.persistence.models import ValidationRuleModel


class SqlValidationRuleRepository:
    """SQLAlchemy implementation of ValidationRuleRepository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, rule_id: UUID) -> ValidationRule | None:
        model = self._session.get(ValidationRuleModel, rule_id)
        return validation_rule_to_entity(model) if model else None

    def list_by_company(self, company_id: UUID) -> list[ValidationRule]:
        rows = self._session.execute(
            select(ValidationRuleModel)
            .where(ValidationRuleModel.company_id == company_id)
            .order_by(ValidationRuleModel.rule_name)
        ).scalars().all()
        return [validation_rule_to_entity(m) for m in rows]

    def add(self, rule: ValidationRule) -> ValidationRule:
        model = validation_rule_to_model(rule)
        self._session.add(model)
        self._session.flush()
        return validation_rule_to_entity(model)

    def update(self, rule: ValidationRule) -> ValidationRule:
        model = self._session.get(ValidationRuleModel, rule.id)
        if model is None:
            raise ValidationRuleNotFoundError(rule.id)  # type: ignore[arg-type]
        
        model.rule_name = rule.rule_name
        model.rule_type = rule.rule_type.value
        model.is_active = rule.is_active
        
        self._session.flush()
        return validation_rule_to_entity(model)

    def delete(self, rule_id: UUID) -> bool:
        model = self._session.get(ValidationRuleModel, rule_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True
