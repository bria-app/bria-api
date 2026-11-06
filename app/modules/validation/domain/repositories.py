"""Validation module domain — repository ports."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.validation.domain.entities import ValidationRule


class ValidationRuleRepository(Protocol):
    """Port for ValidationRule persistence."""

    def get_by_id(self, rule_id: UUID) -> ValidationRule | None: ...
    def list_by_company(self, company_id: UUID) -> list[ValidationRule]: ...
    def add(self, rule: ValidationRule) -> ValidationRule: ...
    def update(self, rule: ValidationRule) -> ValidationRule: ...
    def delete(self, rule_id: UUID) -> bool: ...
