"""Validation module — application use cases."""
from __future__ import annotations

from uuid import UUID

from app.modules.validation.application.dtos import ValidationRuleDTO
from app.modules.validation.domain.entities import ValidationRule
from app.modules.validation.domain.enums import RuleType
from app.modules.validation.domain.exceptions import ValidationRuleNotFoundError
from app.modules.validation.domain.repositories import ValidationRuleRepository


class ListValidationRules:
    def __init__(self, rule_repo: ValidationRuleRepository) -> None:
        self._rule_repo = rule_repo

    def execute(self, company_id: UUID) -> list[ValidationRuleDTO]:
        entities = self._rule_repo.list_by_company(company_id)
        return [ValidationRuleDTO.from_entity(e) for e in entities]


class CreateValidationRule:
    def __init__(self, rule_repo: ValidationRuleRepository) -> None:
        self._rule_repo = rule_repo

    def execute(
        self,
        company_id: UUID,
        rule_name: str,
        rule_type: RuleType,
        is_active: bool = True,
    ) -> ValidationRuleDTO:
        entity = ValidationRule(
            company_id=company_id,
            rule_name=rule_name,
            rule_type=rule_type,
            is_active=is_active,
        )
        saved = self._rule_repo.add(entity)
        return ValidationRuleDTO.from_entity(saved)


class UpdateValidationRule:
    def __init__(self, rule_repo: ValidationRuleRepository) -> None:
        self._rule_repo = rule_repo

    def execute(
        self,
        company_id: UUID,
        rule_id: UUID,
        rule_name: str | None = None,
        rule_type: RuleType | None = None,
        is_active: bool | None = None,
    ) -> ValidationRuleDTO:
        entity = self._rule_repo.get_by_id(rule_id)
        if not entity or entity.company_id != company_id:
            raise ValidationRuleNotFoundError(rule_id)

        if rule_name is not None:
            entity.rule_name = rule_name
        if rule_type is not None:
            entity.rule_type = rule_type
        if is_active is not None:
            entity.is_active = is_active

        updated = self._rule_repo.update(entity)
        return ValidationRuleDTO.from_entity(updated)


class DeleteValidationRule:
    def __init__(self, rule_repo: ValidationRuleRepository) -> None:
        self._rule_repo = rule_repo

    def execute(self, company_id: UUID, rule_id: UUID) -> None:
        entity = self._rule_repo.get_by_id(rule_id)
        if not entity or entity.company_id != company_id:
            raise ValidationRuleNotFoundError(rule_id)

        self._rule_repo.delete(rule_id)
