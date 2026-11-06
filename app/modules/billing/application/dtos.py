"""Billing module — application DTOs."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.billing.domain.entities import BillingPayment, Subscription
from app.modules.billing.domain.enums import SubscriptionStatus
from app.modules.billing.domain.plans import Plan


class SubscriptionDTO(BaseModel):
    # id is None for the implicit free plan (no row stored yet).
    id: UUID | None
    company_id: UUID
    plan_id: str
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    # Derived: premium access right now (active, trialing or canceled, inside the paid period).
    is_premium: bool = False
    # Derived: will renew at period end.
    auto_renew: bool = False

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_entity(cls, entity: Subscription, now: datetime | None = None) -> SubscriptionDTO:
        from datetime import timezone

        now = now or datetime.now(timezone.utc)
        # Same rule the plan enforcement uses: access only inside the paid period.
        is_premium = entity.has_premium_access(now)
        return cls(
            id=entity.id,
            company_id=entity.company_id,
            plan_id=entity.plan_id,
            status=entity.status,
            current_period_start=entity.current_period_start,
            current_period_end=entity.current_period_end,
            is_premium=is_premium,
            auto_renew=is_premium and entity.status == SubscriptionStatus.ACTIVE,
        )


class PlanDTO(BaseModel):
    id: str
    name: str
    tagline: str
    currency: str
    price_monthly: float
    price_yearly: float
    yearly_savings: float
    features: list[str]
    limits: list[str]

    @classmethod
    def from_plan(cls, plan: Plan) -> PlanDTO:
        return cls(
            id=plan.id,
            name=plan.name,
            tagline=plan.tagline,
            currency=plan.currency,
            price_monthly=float(plan.price_monthly),
            price_yearly=float(plan.price_yearly),
            yearly_savings=float(plan.price_monthly * 12 - plan.price_yearly),
            features=list(plan.features),
            limits=list(plan.limits),
        )


class PaymentDTO(BaseModel):
    id: UUID
    company_id: UUID
    plan_id: str
    billing_cycle: str
    amount: float
    currency: str
    method: str
    status: str
    reference: str
    card_last4: str | None
    paid_at: datetime
    created_at: datetime | None = None

    @classmethod
    def from_entity(cls, entity: BillingPayment) -> PaymentDTO:
        if entity.id is None:
            raise ValueError("Entity must have an id to create DTO")
        return cls(
            id=entity.id,
            company_id=entity.company_id,
            plan_id=entity.plan_id,
            billing_cycle=entity.billing_cycle.value,
            amount=float(entity.amount),
            currency=entity.currency,
            method=entity.method.value,
            status=entity.status.value,
            reference=entity.reference,
            card_last4=entity.card_last4,
            paid_at=entity.paid_at,
            created_at=entity.created_at,
        )


class CheckoutResultDTO(BaseModel):
    payment: PaymentDTO
    subscription: SubscriptionDTO
