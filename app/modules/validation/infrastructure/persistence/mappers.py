"""Validation module — mappers."""
from __future__ import annotations

from app.modules.validation.domain.entities import ValidationRule
from app.modules.validation.domain.enums import RuleType
from app.modules.validation.infrastructure.persistence.models import ValidationRuleModel


def validation_rule_to_entity(model: ValidationRuleModel) -> ValidationRule:
    return ValidationRule(
        id=model.id,
        company_id=model.company_id,
        rule_name=model.rule_name,
        rule_type=RuleType(model.rule_type),
        is_active=model.is_active,
    )


def validation_rule_to_model(entity: ValidationRule) -> ValidationRuleModel:
    return ValidationRuleModel(
        id=entity.id,
        company_id=entity.company_id,
        rule_name=entity.rule_name,
        rule_type=entity.rule_type.value,
        is_active=entity.is_active,
    )
