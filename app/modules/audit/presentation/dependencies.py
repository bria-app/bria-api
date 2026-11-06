"""Audit module — dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.audit.domain.repositories import AuditEventRepository
from app.modules.audit.infrastructure.persistence.repositories import (
    SqlAuditEventRepository,
)
from app.shared.presentation.deps import get_db


def get_audit_repository(
    db: Annotated[Session, Depends(get_db, scope="function")],
) -> AuditEventRepository:
    """Dependency provider for AuditEventRepository."""
    return SqlAuditEventRepository(db)
