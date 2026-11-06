"""Companies module — HTTP routers wired to use cases.

Endpoints not covered by Bloque 2A (delete_company, company settings, summary)
remain placeholders and are explicitly marked with TODO.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.companies.application.dtos import CompanyDTO, UserDTO
from app.modules.companies.application.use_cases.company import (
    GetCompany,
    SuspendCompany,
    UpdateCompany,
)
from app.modules.companies.application.use_cases.user import (
    CreateCompanyUser,
    DisableUser,
    InviteUser,
    ListCompanyUsers,
    UpdateCompanyUser,
    UpdateUserRole,
)
from app.modules.companies.domain.enums import UserStatus
from app.modules.companies.domain.repositories import CompanyRepository, UserRepository
from app.modules.companies.presentation.dependencies import (
    get_company_repository,
    get_user_repository,
    parse_role,
)
from app.modules.companies.presentation.schemas import (
    CreateCompanyUserRequest,
    InviteUserRequest,
    UpdateCompanyUserRequest,
    UpdateCompanyRequest,
    UpdateUserRoleRequest,
)
from app.shared.presentation.deps import (
    AuthenticatedUser,
    get_current_user,
    get_pagination,
    require_company_access,
    require_role,
)
from app.shared.presentation.schemas import (
    MessageResponse,
    PaginationParams,
    PlaceholderResponse,
)

router = APIRouter()
users_router = APIRouter()


# --- Companies ---------------------------------------------------------------
# There is no platform (super-admin) role, so tenants never see other companies
# (audit C-03): the list holds only the caller's own company, and companies are only
# created through /auth/register (POST /companies was removed; the web never used it).
@router.get("", response_model=list[CompanyDTO])
def list_companies(
    current: AuthenticatedUser = Depends(get_current_user),
    repo: CompanyRepository = Depends(get_company_repository),
) -> list[CompanyDTO]:
    return [GetCompany(repo).execute(current.company_id)]


@router.get("/{company_id}", response_model=CompanyDTO)
def get_company(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: CompanyRepository = Depends(get_company_repository),
) -> CompanyDTO:
    return GetCompany(repo).execute(company_id)


@router.patch("/{company_id}", response_model=CompanyDTO)
def update_company(
    company_id: UUID,
    request: UpdateCompanyRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    __: AuthenticatedUser = Depends(require_role("owner", "admin")),
    repo: CompanyRepository = Depends(get_company_repository),
) -> CompanyDTO:
    return UpdateCompany(repo).execute(
        company_id,
        name=request.name,
        business_type=request.business_type,
        address=request.address,
        phone=request.phone,
        email=request.email,
    )


@router.post("/{company_id}/suspend", response_model=CompanyDTO)
def suspend_company(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    __: AuthenticatedUser = Depends(require_role("owner")),
    repo: CompanyRepository = Depends(get_company_repository),
) -> CompanyDTO:
    return SuspendCompany(repo).execute(company_id)


@router.delete("/{company_id}", response_model=MessageResponse)
def delete_company(company_id: UUID) -> MessageResponse:
    # TODO(Bloque 2+): define company deletion / soft-delete policy.
    return MessageResponse(message="Not implemented yet")


@router.get("/{company_id}/settings", response_model=PlaceholderResponse)
def get_company_settings(company_id: UUID) -> PlaceholderResponse:
    # TODO(Bloque 2+): company settings entity not modeled yet.
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="companies", action="get_company_settings"
    )


@router.get("/{company_id}/summary", response_model=PlaceholderResponse)
def get_company_summary(company_id: UUID) -> PlaceholderResponse:
    # TODO(dashboard module): aggregation endpoint.
    return PlaceholderResponse(
        message="Endpoint scaffold ready", module="companies", action="get_company_summary"
    )


# --- Company users -----------------------------------------------------------
@users_router.get("/{company_id}/users", response_model=list[UserDTO])
def list_company_users(
    company_id: UUID,
    pagination: PaginationParams = Depends(get_pagination),
    _: AuthenticatedUser = Depends(require_company_access),
    repo: UserRepository = Depends(get_user_repository),
) -> list[UserDTO]:
    return ListCompanyUsers(repo).execute(
        company_id,
        offset=(pagination.page - 1) * pagination.size,
        limit=pagination.size,
    )


@users_router.post("/{company_id}/users", response_model=UserDTO, status_code=201)
def create_company_user(
    company_id: UUID,
    request: CreateCompanyUserRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    __: AuthenticatedUser = Depends(require_role("owner", "admin")),
    repo: UserRepository = Depends(get_user_repository),
) -> UserDTO:
    """Create a user that signs in with a username (sellers / admins)."""
    return CreateCompanyUser(repo).execute(
        company_id,
        full_name=request.full_name,
        username=request.username,
        password=request.password,
        role=parse_role(request.role),
    )


@users_router.patch("/{company_id}/users/{user_id}", response_model=UserDTO)
def update_company_user(
    company_id: UUID,
    user_id: UUID,
    request: UpdateCompanyUserRequest,
    current: AuthenticatedUser = Depends(require_company_access),
    __: AuthenticatedUser = Depends(require_role("owner", "admin")),
    repo: UserRepository = Depends(get_user_repository),
) -> UserDTO:
    """Rename, reset the password or activate/disable a company user."""
    return UpdateCompanyUser(repo).execute(
        company_id,
        user_id,
        acting_user_id=current.user_id,
        full_name=request.full_name,
        password=request.password,
        status=UserStatus(request.status) if request.status else None,
    )


@users_router.post("/{company_id}/users/invite", response_model=UserDTO, status_code=201)
def invite_company_user(
    company_id: UUID,
    request: InviteUserRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    __: AuthenticatedUser = Depends(require_role("owner", "admin")),
    repo: UserRepository = Depends(get_user_repository),
) -> UserDTO:
    return InviteUser(repo).execute(
        company_id,
        email=request.email,
        full_name=request.full_name,
        role=parse_role(request.role),
        temporary_password=request.temporary_password,
    )


@users_router.patch("/{company_id}/users/{user_id}/role", response_model=UserDTO)
def update_company_user_role(
    company_id: UUID,
    user_id: UUID,
    request: UpdateUserRoleRequest,
    current: AuthenticatedUser = Depends(require_company_access),
    __: AuthenticatedUser = Depends(require_role("owner", "admin")),
    repo: UserRepository = Depends(get_user_repository),
) -> UserDTO:
    return UpdateUserRole(repo).execute(
        company_id, user_id, role=parse_role(request.role), acting_user_id=current.user_id
    )


@users_router.delete("/{company_id}/users/{user_id}", response_model=UserDTO)
def delete_company_user(
    company_id: UUID,
    user_id: UUID,
    current: AuthenticatedUser = Depends(require_company_access),
    __: AuthenticatedUser = Depends(require_role("owner", "admin")),
    repo: UserRepository = Depends(get_user_repository),
) -> UserDTO:
    # Soft-delete: disable the user rather than removing the record.
    return DisableUser(repo).execute(company_id, user_id, acting_user_id=current.user_id)
