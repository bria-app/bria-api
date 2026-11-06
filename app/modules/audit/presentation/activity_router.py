"""Audit module — Activity HTTP router."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.audit.application.use_cases.audit import ListAuditEvents
from app.modules.audit.domain.repositories import AuditEventRepository
from app.modules.audit.presentation.dependencies import get_audit_repository
from app.modules.audit.presentation.schemas import AuditEventResponse
from app.shared.presentation.deps import (
    AuthenticatedUser,
    get_pagination,
    require_company_access,
)
from app.shared.presentation.schemas import (
    PaginatedResponse,
    PaginationParams,
    PlaceholderResponse,
)

router = APIRouter()


@router.get("/health", response_model=PlaceholderResponse)
def health_check(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="activity", action="health_check"
    )


@router.get("", response_model=PaginatedResponse[AuditEventResponse])
def get_activity_feed(
    company_id: UUID,
    repo: Annotated[AuditEventRepository, Depends(get_audit_repository)],
    pagination: Annotated[PaginationParams, Depends(get_pagination)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> PaginatedResponse[AuditEventResponse]:
    # Activity feed is just a list of audit events for the company (chronological view)
    use_case = ListAuditEvents(repo)
    offset = (pagination.page - 1) * pagination.size
    dtos = use_case.execute(
        company_id=company_id,
        offset=offset,
        limit=pagination.size,
    )
    return PaginatedResponse(
        items=[AuditEventResponse.model_validate(d) for d in dtos],
        total=len(dtos),
        page=pagination.page,
        size=pagination.size,
        pages=1,
    )
