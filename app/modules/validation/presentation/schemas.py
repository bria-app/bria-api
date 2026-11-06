"""Validation module — HTTP schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.validation.application.dtos import ValidationRuleDTO
from app.modules.validation.domain.enums import RuleType


class ValidationRuleResponse(ValidationRuleDTO):
    """Response schema for a validation rule."""
    pass


class CreateValidationRuleRequest(BaseModel):
    rule_name: str = Field(..., min_length=1, max_length=255)
    rule_type: RuleType
    is_active: bool = True


class UpdateValidationRuleRequest(BaseModel):
    rule_name: str | None = Field(None, min_length=1, max_length=255)
    rule_type: RuleType | None = None
    is_active: bool | None = None


# Placeholders for scaffold endpoints
class ValidationSessionRequest(BaseModel):
    pass

class ValidationSessionResponse(BaseModel):
    message: str
    module: str
    action: str

class ValidationResponseRequest(BaseModel):
    pass

class ValidationResultsResponse(BaseModel):
    message: str
    module: str
    action: str
