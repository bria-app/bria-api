"""Billing module — mappers."""
from __future__ import annotations

from app.modules.billing.domain.entities import BillingPayment, Subscription
from app.modules.billing.domain.enums import (
    BillingCycle,
    PaymentMethod,
    PaymentStatus,
    SubscriptionStatus,
)
from app.modules.billing.infrastructure.persistence.models import (
    BillingPaymentModel,
    SubscriptionModel,
)


def subscription_to_entity(model: SubscriptionModel) -> Subscription:
    return Subscription(
        id=model.id,
        company_id=model.company_id,
        plan_id=model.plan_id,
        status=SubscriptionStatus(model.status),
        current_period_start=model.current_period_start,
        current_period_end=model.current_period_end,
    )


def subscription_to_model(entity: Subscription) -> SubscriptionModel:
    return SubscriptionModel(
        id=entity.id,
        company_id=entity.company_id,
        plan_id=entity.plan_id,
        status=entity.status.value,
        current_period_start=entity.current_period_start,
        current_period_end=entity.current_period_end,
    )


def payment_to_entity(model: BillingPaymentModel) -> BillingPayment:
    return BillingPayment(
        id=model.id,
        company_id=model.company_id,
        plan_id=model.plan_id,
        billing_cycle=BillingCycle(model.billing_cycle),
        amount=model.amount,
        currency=model.currency,
        method=PaymentMethod(model.method),
        status=PaymentStatus(model.status),
        reference=model.reference,
        card_last4=model.card_last4,
        paid_at=model.paid_at,
        created_at=model.created_at,
    )


def payment_to_model(entity: BillingPayment) -> BillingPaymentModel:
    return BillingPaymentModel(
        id=entity.id,
        company_id=entity.company_id,
        plan_id=entity.plan_id,
        billing_cycle=entity.billing_cycle.value,
        amount=entity.amount,
        currency=entity.currency,
        method=entity.method.value,
        status=entity.status.value,
        reference=entity.reference,
        card_last4=entity.card_last4,
        paid_at=entity.paid_at,
    )
