"""Notifications module — HTTP router."""
from __future__ import annotations

import math
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.modules.notifications.application.use_cases.notification import (
    CountNotifications,
    CreateNotification,
    DeleteNotification,
    GetNotification,
    ListNotifications,
    MarkAllRead,
    MarkRead,
)
from app.modules.notifications.domain.repositories import NotificationRepository
from app.modules.notifications.presentation.dependencies import get_notification_repository
from app.modules.notifications.presentation.schemas import (
    CreateNotificationRequest,
    MarkAllReadResponse,
    NotificationPreferencesResponse,
    NotificationResponse,
    UnreadCountResponse,
    UpdateNotificationPreferencesRequest,
)
from app.shared.presentation.deps import (
    AuthenticatedUser,
    get_pagination,
    require_company_access,
)
from app.shared.presentation.schemas import (
    MessageResponse,
    PaginatedResponse,
    PaginationParams,
    PlaceholderResponse,
)

router = APIRouter()


@router.get("/health", response_model=PlaceholderResponse)
def health_check(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="notifications", action="health_check"
    )


@router.get("", response_model=PaginatedResponse[NotificationResponse])
def list_notifications(
    company_id: UUID,
    repo: Annotated[NotificationRepository, Depends(get_notification_repository)],
    pagination: Annotated[PaginationParams, Depends(get_pagination)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
    unread_only: bool = Query(False, description="Filter by unread notifications only"),
) -> PaginatedResponse[NotificationResponse]:
    use_case = ListNotifications(repo)
    offset = (pagination.page - 1) * pagination.size
    dtos = use_case.execute(
        company_id=company_id,
        unread_only=unread_only,
        offset=offset,
        limit=pagination.size,
    )
    total = CountNotifications(repo).execute(company_id=company_id, unread_only=unread_only)
    return PaginatedResponse(
        items=[NotificationResponse.model_validate(d) for d in dtos],
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=max(1, math.ceil(total / pagination.size)),
    )


@router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
def create_notification(
    company_id: UUID,
    request: CreateNotificationRequest,
    repo: Annotated[NotificationRepository, Depends(get_notification_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> NotificationResponse:
    use_case = CreateNotification(repo)
    dto = use_case.execute(
        company_id=company_id,
        title=request.title,
        message=request.message,
        severity=request.severity,
    )
    return NotificationResponse.model_validate(dto, from_attributes=True)


@router.get("/unread-count", response_model=UnreadCountResponse)
def get_unread_count(
    company_id: UUID,
    repo: Annotated[NotificationRepository, Depends(get_notification_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> UnreadCountResponse:
    return UnreadCountResponse(
        unread=CountNotifications(repo).execute(company_id=company_id, unread_only=True)
    )


@router.get("/preferences", response_model=NotificationPreferencesResponse)
def get_preferences(company_id: UUID) -> NotificationPreferencesResponse:
    return NotificationPreferencesResponse(
        message="Endpoint scaffold ready", module="notifications", action="get_preferences"
    )


@router.patch("/preferences", response_model=NotificationPreferencesResponse)
def update_preferences(
    company_id: UUID, request: UpdateNotificationPreferencesRequest
) -> NotificationPreferencesResponse:
    return NotificationPreferencesResponse(
        message="Endpoint scaffold ready", module="notifications", action="update_preferences"
    )


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
def mark_all_read(
    company_id: UUID,
    repo: Annotated[NotificationRepository, Depends(get_notification_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> MarkAllReadResponse:
    updated = MarkAllRead(repo).execute(company_id=company_id)
    if updated == 0:
        message = "No tenías avisos sin leer."
    elif updated == 1:
        message = "Marcamos 1 aviso como leído."
    else:
        message = f"Marcamos {updated} avisos como leídos."
    return MarkAllReadResponse(message=message, updated=updated)


@router.post("/test-email", response_model=PlaceholderResponse)
def test_email(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="notifications", action="test_email"
    )


@router.post("/send-stockout-alert", response_model=PlaceholderResponse)
def send_stockout_alert(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="notifications", action="send_stockout_alert"
    )


@router.post("/send-forecast-completed", response_model=PlaceholderResponse)
def send_forecast_completed(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="notifications", action="send_forecast_completed"
    )


@router.post("/send-report-ready", response_model=PlaceholderResponse)
def send_report_ready(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="notifications", action="send_report_ready"
    )


@router.get("/{notification_id}", response_model=NotificationResponse)
def get_notification(
    company_id: UUID,
    notification_id: UUID,
    repo: Annotated[NotificationRepository, Depends(get_notification_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> NotificationResponse:
    use_case = GetNotification(repo)
    dto = use_case.execute(company_id=company_id, notification_id=notification_id)
    return NotificationResponse.model_validate(dto, from_attributes=True)


@router.patch("/{notification_id}", response_model=NotificationResponse)
def update_notification(company_id: UUID, notification_id: UUID) -> NotificationResponse:
    # We do not have an UpdateNotification use case explicitly in the scope, keep placeholder response?
    # Actually schema returns NotificationResponse, so we need to either implement it or leave it.
    # The prompt didn't ask for update notification. I will raise NotImplemented.
    raise NotImplementedError("update_notification not implemented")


@router.delete("/{notification_id}", response_model=MessageResponse)
def delete_notification(
    company_id: UUID,
    notification_id: UUID,
    repo: Annotated[NotificationRepository, Depends(get_notification_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> MessageResponse:
    use_case = DeleteNotification(repo)
    use_case.execute(company_id=company_id, notification_id=notification_id)
    return MessageResponse(message="Notification deleted successfully")


@router.post("/{notification_id}/mark-read", response_model=MessageResponse)
def mark_notification_read(
    company_id: UUID,
    notification_id: UUID,
    repo: Annotated[NotificationRepository, Depends(get_notification_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> MessageResponse:
    use_case = MarkRead(repo)
    use_case.execute(company_id=company_id, notification_id=notification_id)
    return MessageResponse(message="Notification marked as read")
