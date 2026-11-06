"""Tests for Validation module."""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.validation.application.use_cases.validation import (
    CreateValidationRule,
    DeleteValidationRule,
    ListValidationRules,
    UpdateValidationRule,
)
from app.modules.validation.domain.entities import ValidationRule
from app.modules.validation.domain.enums import RuleType


class FakeValidationRuleRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, ValidationRule] = {}

    def get_by_id(self, rule_id: UUID) -> ValidationRule | None:
        return self._store.get(rule_id)

    def list_by_company(self, company_id: UUID) -> list[ValidationRule]:
        rows = [r for r in self._store.values() if r.company_id == company_id]
        rows.sort(key=lambda r: r.rule_name)
        return rows

    def add(self, rule: ValidationRule) -> ValidationRule:
        if rule.id is None:
            rule.id = uuid4()
        self._store[rule.id] = rule
        return rule

    def update(self, rule: ValidationRule) -> ValidationRule:
        assert rule.id is not None
        self._store[rule.id] = rule
        return rule

    def delete(self, rule_id: UUID) -> bool:
        return self._store.pop(rule_id, None) is not None


class TestValidationUseCases:
    def test_crud_validation_rules(self) -> None:
        repo = FakeValidationRuleRepository()
        company_id = uuid4()

        # Create
        created = CreateValidationRule(repo).execute(
            company_id=company_id,
            rule_name="No negatives",
            rule_type=RuleType.OUTLIER,
            is_active=True,
        )
        assert created.rule_name == "No negatives"
        assert created.rule_type == RuleType.OUTLIER
        assert created.is_active is True

        # List
        rules = ListValidationRules(repo).execute(company_id=company_id)
        assert len(rules) == 1
        assert rules[0].id == created.id

        # Update
        updated = UpdateValidationRule(repo).execute(
            company_id=company_id,
            rule_id=created.id,
            is_active=False,
        )
        assert updated.is_active is False

        # Delete
        DeleteValidationRule(repo).execute(company_id=company_id, rule_id=created.id)
        assert len(ListValidationRules(repo).execute(company_id=company_id)) == 0
