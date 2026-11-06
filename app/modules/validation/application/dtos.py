"""Validation module — application DTOs."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.validation.domain.entities import ValidationRule
from app.modules.validation.domain.enums import RuleType


class ValidationRuleDTO(BaseModel):
    id: UUID
    company_id: UUID
    rule_name: str
    rule_type: RuleType
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_entity(cls, entity: ValidationRule) -> ValidationRuleDTO:
        if entity.id is None:
            raise ValueError("Entity must have an id to create DTO")
        return cls(
            id=entity.id,
            company_id=entity.company_id,
            rule_name=entity.rule_name,
            rule_type=entity.rule_type,
            is_active=entity.is_active,
        )
