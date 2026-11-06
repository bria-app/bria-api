"""Admin module — HTTP router."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.modules.admin.application.use_cases.admin import (
    GetSystemSettings,
    UpdateSystemSetting,
)
from app.modules.admin.domain.repositories import SystemSettingsRepository
from app.modules.admin.presentation.dependencies import get_system_settings_repository
from app.modules.admin.presentation.schemas import (
    AdminCompanyResponse,
    AdminSystemStatusResponse,
    AdminUserResponse,
    SystemSettingResponse,
    UpdateSystemSettingRequest,
)
from app.shared.presentation.deps import AuthenticatedUser, require_role
from app.shared.presentation.schemas import PlaceholderResponse

router = APIRouter()


@router.get("/health", response_model=PlaceholderResponse)
def admin_health_check(
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="admin", action="health_check"
    )


# --- System Settings Endpoints ---

@router.get("/system/settings", response_model=list[SystemSettingResponse])
def get_system_settings(
    repo: Annotated[SystemSettingsRepository, Depends(get_system_settings_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))],
) -> list[SystemSettingResponse]:
    use_case = GetSystemSettings(repo)
    dtos = use_case.execute()
    return [SystemSettingResponse.model_validate(d) for d in dtos]


@router.get("/system/settings/{key}", response_model=SystemSettingResponse)
def get_system_setting(
    key: str,
    repo: Annotated[SystemSettingsRepository, Depends(get_system_settings_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))],
) -> SystemSettingResponse:
    use_case = GetSystemSettings(repo)
    dtos = use_case.execute(key=key)
    return SystemSettingResponse.model_validate(dtos[0], from_attributes=True)


@router.put("/system/settings/{key}", response_model=SystemSettingResponse)
def update_system_setting(
    key: str,
    request: UpdateSystemSettingRequest,
    repo: Annotated[SystemSettingsRepository, Depends(get_system_settings_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))],
) -> SystemSettingResponse:
    use_case = UpdateSystemSetting(repo)
    dto = use_case.execute(
        key=key,
        value=request.value,
        updated_by=user.user_id,
    )
    return SystemSettingResponse.model_validate(dto, from_attributes=True)


# --- Placeholder Endpoints ---

@router.get("/users", response_model=PlaceholderResponse)
def list_admin_users(
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="admin", action="list_admin_users")

@router.get("/users/{user_id}", response_model=AdminUserResponse)
def get_admin_user(
    user_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> AdminUserResponse:
    return AdminUserResponse(message="Endpoint scaffold ready", module="admin", action="get_admin_user")

@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def update_admin_user(
    user_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> AdminUserResponse:
    return AdminUserResponse(message="Endpoint scaffold ready", module="admin", action="update_admin_user")

@router.delete("/users/{user_id}", response_model=PlaceholderResponse)
def delete_admin_user(
    user_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="admin", action="delete_admin_user")

@router.get("/companies", response_model=PlaceholderResponse)
def list_admin_companies(
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="admin", action="list_admin_companies")

@router.get("/companies/{company_id}", response_model=AdminCompanyResponse)
def get_admin_company(
    company_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> AdminCompanyResponse:
    return AdminCompanyResponse(message="Endpoint scaffold ready", module="admin", action="get_admin_company")

@router.patch("/companies/{company_id}", response_model=AdminCompanyResponse)
def update_admin_company(
    company_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> AdminCompanyResponse:
    return AdminCompanyResponse(message="Endpoint scaffold ready", module="admin", action="update_admin_company")

@router.get("/system/status", response_model=AdminSystemStatusResponse)
def get_system_status(
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> AdminSystemStatusResponse:
    return AdminSystemStatusResponse(message="Endpoint scaffold ready", module="admin", action="get_system_status")

@router.get("/system/jobs", response_model=PlaceholderResponse)
def get_system_jobs(
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="admin", action="get_system_jobs")

@router.get("/system/errors", response_model=PlaceholderResponse)
def get_system_errors(
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="admin", action="get_system_errors")

@router.get("/system/audit", response_model=PlaceholderResponse)
def get_system_audit(
    user: Annotated[AuthenticatedUser, Depends(require_role("superadmin"))]
) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="admin", action="get_system_audit")
