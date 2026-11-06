"""Validation module — dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.validation.domain.repositories import ValidationRuleRepository
from app.modules.validation.infrastructure.persistence.repositories import (
    SqlValidationRuleRepository,
)
from app.shared.presentation.deps import get_db


def get_validation_rule_repository(
    db: Annotated[Session, Depends(get_db, scope="function")],
) -> ValidationRuleRepository:
    """Dependency provider for ValidationRuleRepository."""
    return SqlValidationRuleRepository(db)
