"""Auth module — HTTP router wired to authentication use cases.

Implemented in Bloque 2A: register, login, refresh-token, me (GET), me/password.
The remaining endpoints (logout, me PATCH, forgot/reset password, email verification)
stay as explicit placeholders for a later iteration.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.auth.application.dtos import TokenDTO
from app.modules.auth.application.use_cases.authentication import (
    ChangePassword,
    GetCurrentUserProfile,
    Login,
    RefreshToken,
    RegisterAccount,
)
from app.modules.auth.presentation.dependencies import (
    get_company_repository,
    get_user_repository,
)
from app.modules.auth.presentation.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
)
from app.modules.companies.application.dtos import UserDTO
from app.modules.companies.domain.repositories import CompanyRepository, UserRepository
from app.shared.presentation.deps import AuthenticatedUser, get_current_user
from app.shared.presentation.schemas import MessageResponse, PlaceholderResponse

router = APIRouter()


@router.post("/register", response_model=TokenDTO, status_code=201)
def register(
    request: RegisterRequest,
    companies: CompanyRepository = Depends(get_company_repository),
    users: UserRepository = Depends(get_user_repository),
) -> TokenDTO:
    return RegisterAccount(companies, users).execute(
        email=request.email,
        password=request.password,
        full_name=request.full_name,
        company_name=request.company_name,
        tax_id=request.tax_id,
        business_type=request.business_type,
    )


@router.post("/login", response_model=TokenDTO)
def login(
    request: LoginRequest,
    users: UserRepository = Depends(get_user_repository),
) -> TokenDTO:
    return Login(users).execute(
        identifier=request.identifier or request.email or "", password=request.password
    )


@router.post("/refresh-token", response_model=TokenDTO)
def refresh_token(
    request: RefreshTokenRequest,
    users: UserRepository = Depends(get_user_repository),
) -> TokenDTO:
    return RefreshToken(users).execute(refresh_token=request.refresh_token)


@router.get("/me", response_model=UserDTO)
def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
    users: UserRepository = Depends(get_user_repository),
) -> UserDTO:
    return GetCurrentUserProfile(users).execute(current_user.user_id)


@router.patch("/me/password", response_model=MessageResponse)
def update_password(
    request: ChangePasswordRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    users: UserRepository = Depends(get_user_repository),
) -> MessageResponse:
    ChangePassword(users).execute(
        current_user.user_id,
        current_password=request.current_password,
        new_password=request.new_password,
    )
    return MessageResponse(message="Password updated successfully")


# --- Not implemented yet (explicit placeholders) -----------------------------
@router.post("/logout", response_model=MessageResponse)
def logout() -> MessageResponse:
    # TODO: token revocation / blacklist (requires a token store).
    return MessageResponse(message="Logout is stateless; discard the token client-side")


@router.patch("/me", response_model=PlaceholderResponse)
def update_me() -> PlaceholderResponse:
    # TODO: update own profile (full_name, etc.).
    return PlaceholderResponse(message="Endpoint scaffold ready", module="auth", action="update_me")


@router.post("/forgot-password", response_model=PlaceholderResponse)
def forgot_password() -> PlaceholderResponse:
    # TODO: requires EmailPort + reset-token store.
    return PlaceholderResponse(message="Endpoint scaffold ready", module="auth", action="forgot_password")


@router.post("/reset-password", response_model=PlaceholderResponse)
def reset_password() -> PlaceholderResponse:
    # TODO: requires reset-token validation.
    return PlaceholderResponse(message="Endpoint scaffold ready", module="auth", action="reset_password")


@router.post("/verify-email", response_model=PlaceholderResponse)
def verify_email() -> PlaceholderResponse:
    # TODO: requires email verification flow.
    return PlaceholderResponse(message="Endpoint scaffold ready", module="auth", action="verify_email")


@router.post("/resend-verification", response_model=PlaceholderResponse)
def resend_verification() -> PlaceholderResponse:
    # TODO: requires EmailPort.
    return PlaceholderResponse(message="Endpoint scaffold ready", module="auth", action="resend_verification")
