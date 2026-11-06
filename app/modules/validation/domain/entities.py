"""Validation module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.modules.validation.domain.enums import RuleType


@dataclass
class ValidationRule:
    """A data validation rule configuration."""

    company_id: UUID
    rule_name: str
    rule_type: RuleType
    is_active: bool = True
    id: UUID | None = None
