"""Billing module — HTTP router."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.config import settings
from app.modules.billing.application.dtos import CheckoutResultDTO, PaymentDTO, PlanDTO
from app.modules.billing.application.use_cases.billing import (
    CancelSubscription,
    Checkout,
    GetPlan,
    GetSubscription,
    ListPayments,
    ListPlans,
    ResumeSubscription,
    UpdateSubscriptionStatus,
)
from app.modules.billing.domain.enums import BillingCycle, PaymentMethod
from app.modules.billing.domain.repositories import PaymentRepository, SubscriptionRepository
from app.modules.billing.presentation.dependencies import (
    get_payment_repository,
    get_subscription_repository,
)
from app.modules.billing.presentation.schemas import (
    CheckoutRequest,
    InvoiceResponse,
    PaymentWebhookResponse,
    SubscriptionRequest,
    SubscriptionResponse,
    WebhookUpdateSubscriptionRequest,
)
from app.shared.domain.errors import ForbiddenError
from app.shared.presentation.deps import AuthenticatedUser, require_company_access
from app.shared.presentation.schemas import PlaceholderResponse

router = APIRouter()
companies_router = APIRouter()

BILLING_MANAGER_ROLES = frozenset({"owner", "admin", "superadmin"})


def require_billing_manager(
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> AuthenticatedUser:
    if user.role not in BILLING_MANAGER_ROLES:
        raise ForbiddenError(message="Solo el propietario o un administrador puede gestionar el plan.")
    return user


# --- Global Billing Endpoints ---

@router.get("/plans", response_model=list[PlanDTO])
def list_plans() -> list[PlanDTO]:
    return ListPlans().execute()


@router.get("/plans/{plan_id}", response_model=PlanDTO)
def get_plan(plan_id: str) -> PlanDTO:
    return GetPlan().execute(plan_id)


@router.post("/webhooks/payment-provider", response_model=PaymentWebhookResponse)
def payment_webhook() -> PaymentWebhookResponse:
    return PaymentWebhookResponse(message="Endpoint scaffold ready", module="billing", action="payment_webhook")


def simulate_webhook_enabled() -> bool:
    """The fake payment webhook only exists outside production (audit C-01)."""
    return not settings.is_production


# Fake webhook endpoint for testing updates to a company's subscription easily. Never
# registered in production; elsewhere it needs a logged-in owner/admin of that company.
def simulate_webhook_update(
    company_id: UUID,
    request: WebhookUpdateSubscriptionRequest,
    repo: Annotated[SubscriptionRepository, Depends(get_subscription_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_billing_manager)],
) -> SubscriptionResponse:
    """Simulates a webhook from a payment provider to update the subscription."""
    use_case = UpdateSubscriptionStatus(repo)
    dto = use_case.execute(
        company_id=company_id,
        status=request.status,
        plan_id=request.plan_id,
        period_start=request.current_period_start,
        period_end=request.current_period_end,
    )
    return SubscriptionResponse.model_validate(dto.model_dump())


if simulate_webhook_enabled():
    router.post("/webhooks/simulate/{company_id}", response_model=SubscriptionResponse)(
        simulate_webhook_update
    )


# --- Company Billing Endpoints ---

@companies_router.get("/{company_id}/billing/subscription", response_model=SubscriptionResponse)
def get_company_subscription(
    company_id: UUID,
    repo: Annotated[SubscriptionRepository, Depends(get_subscription_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> SubscriptionResponse:
    dto = GetSubscription(repo).execute(company_id=company_id)
    return SubscriptionResponse.model_validate(dto.model_dump())


@companies_router.post("/{company_id}/billing/checkout", response_model=CheckoutResultDTO, status_code=201)
def checkout(
    company_id: UUID,
    request: CheckoutRequest,
    subscriptions: Annotated[SubscriptionRepository, Depends(get_subscription_repository)],
    payments: Annotated[PaymentRepository, Depends(get_payment_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_billing_manager)],
) -> CheckoutResultDTO:
    """Simulated checkout (demo): no real charge; only card brand + last4 are received."""
    return Checkout(subscriptions, payments).execute(
        company_id=company_id,
        plan_id=request.plan_id,
        billing_cycle=BillingCycle(request.billing_cycle),
        method=PaymentMethod(request.method),
        card_brand=request.card.brand if request.card else None,
        card_last4=request.card.last4 if request.card else None,
        card_holder=request.card.holder_name if request.card else None,
        yape_code=request.yape_code,
    )


@companies_router.get("/{company_id}/billing/payments", response_model=list[PaymentDTO])
def list_payments(
    company_id: UUID,
    payments: Annotated[PaymentRepository, Depends(get_payment_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_company_access)],
) -> list[PaymentDTO]:
    return ListPayments(payments).execute(company_id)


@companies_router.post("/{company_id}/billing/cancel", response_model=SubscriptionResponse)
def cancel_subscription(
    company_id: UUID,
    repo: Annotated[SubscriptionRepository, Depends(get_subscription_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_billing_manager)],
) -> SubscriptionResponse:
    dto = CancelSubscription(repo).execute(company_id)
    return SubscriptionResponse.model_validate(dto.model_dump())


@companies_router.post("/{company_id}/billing/resume", response_model=SubscriptionResponse)
def resume_subscription(
    company_id: UUID,
    repo: Annotated[SubscriptionRepository, Depends(get_subscription_repository)],
    user: Annotated[AuthenticatedUser, Depends(require_billing_manager)],
) -> SubscriptionResponse:
    dto = ResumeSubscription(repo).execute(company_id)
    return SubscriptionResponse.model_validate(dto.model_dump())


@companies_router.post("/{company_id}/billing/subscription", response_model=PlaceholderResponse)
def create_company_subscription(company_id: UUID, request: SubscriptionRequest) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="billing", action="create_company_subscription")


@companies_router.patch("/{company_id}/billing/subscription", response_model=PlaceholderResponse)
def update_company_subscription(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="billing", action="update_company_subscription")


@companies_router.delete("/{company_id}/billing/subscription", response_model=PlaceholderResponse)
def delete_company_subscription(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="billing", action="delete_company_subscription")


@companies_router.get("/{company_id}/billing/invoices", response_model=PlaceholderResponse)
def list_company_invoices(company_id: UUID) -> PlaceholderResponse:
    return PlaceholderResponse(message="Endpoint scaffold ready", module="billing", action="list_company_invoices")


@companies_router.get("/{company_id}/billing/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_company_invoice(company_id: UUID, invoice_id: UUID) -> InvoiceResponse:
    return InvoiceResponse(message="Endpoint scaffold ready", module="billing", action="get_company_invoice")
