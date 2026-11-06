"""Audit module — HTTP router."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.modules.audit.application.use_cases.audit import (
    ListAuditEvents,
    RecordAuditEvent,
)
from app.modules.audit.domain.repositories import AuditEventRepository
from app.modules.audit.presentation.dependencies import get_audit_repository
from app.modules.audit.presentation.schemas import (
    AuditEventResponse,
    CreateAuditEventRequest,
)
from app.shared.presentation.deps import (
    AuthenticatedUser,
    get_pagination,
    require_company_access,
    require_role,
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
        message="Endpoint scaffold ready", module="audit", action="health_check"
    )


@router.get("", response_model=PaginatedResponse[AuditEventResponse])
def list_audit_events(
    company_id: UUID,
    repo: Annotated[AuditEventRepository, Depends(get_audit_repository)],
    pagination: Annotated[PaginationParams, Depends(get_pagination)],
    user: Annotated[AuthenticatedUser, Depends(require_role("admin"))], # Admin only
    resource_type: str | None = Query(None, description="Filter by resource type"),
    user_id: UUID | None = Query(None, description="Filter by user ID"),
) -> PaginatedResponse[AuditEventResponse]:
    use_case = ListAuditEvents(repo)
    offset = (pagination.page - 1) * pagination.size
    dtos = use_case.execute(
        company_id=company_id,
        resource_type=resource_type,
        user_id=user_id,
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


@router.post("", response_model=AuditEventResponse, status_code=status.HTTP_201_CREATED)
def record_audit_event(
    company_id: UUID,
    request: CreateAuditEventRequest,
    repo: Annotated[AuditEventRepository, Depends(get_audit_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> AuditEventResponse:
    use_case = RecordAuditEvent(repo)
    dto = use_case.execute(
        company_id=company_id,
        action=request.action,
        resource_type=request.resource_type,
        user_id=user.user_id,
        resource_id=request.resource_id,
        event_metadata=request.event_metadata,
    )
    return AuditEventResponse.model_validate(dto, from_attributes=True)


@router.get("/export", response_model=PlaceholderResponse)
def export_audit_log(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="audit", action="export_audit_log"
    )


@router.get("/{event_id}", response_model=PlaceholderResponse)
def get_audit_event(company_id: UUID, event_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="audit", action="get_audit_event"
    )


# Re-export the activity router so bootstrap can import both from this module.
from app.modules.audit.presentation.activity_router import (  # noqa: E402
    router as activity_router,
)

__all__ = ["activity_router", "router"]
