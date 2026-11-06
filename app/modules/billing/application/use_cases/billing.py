"""Billing module — application use cases."""
from __future__ import annotations

import calendar
import re
import secrets
import string
from datetime import datetime, timezone
from uuid import UUID

from app.modules.billing.application.dtos import (
    CheckoutResultDTO,
    PaymentDTO,
    PlanDTO,
    SubscriptionDTO,
)
from app.modules.billing.domain.entities import BillingPayment, Subscription
from app.modules.billing.domain.enums import (
    BillingCycle,
    PaymentMethod,
    PaymentStatus,
    SubscriptionStatus,
)
from app.modules.billing.domain.exceptions import (
    PaymentValidationError,
    PlanNotFoundError,
)
from app.modules.billing.domain.plans import FREE_PLAN_ID, PLANS, PREMIUM_PLAN_ID, get_plan
from app.modules.billing.domain.repositories import PaymentRepository, SubscriptionRepository

CARD_BRANDS = {"visa", "mastercard", "amex", "diners"}
_REF_ALPHABET = string.ascii_uppercase + string.digits


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _period_end(start: datetime, cycle: BillingCycle) -> datetime:
    return add_months(start, 12 if cycle == BillingCycle.YEARLY else 1)


class ListPlans:
    def execute(self) -> list[PlanDTO]:
        return [PlanDTO.from_plan(p) for p in PLANS.values()]


class GetPlan:
    def execute(self, plan_id: str) -> PlanDTO:
        plan = get_plan(plan_id)
        if plan is None:
            raise PlanNotFoundError(plan_id)
        return PlanDTO.from_plan(plan)


class GetSubscription:
    """Returns the company's subscription; with no row stored, the company is on the free plan."""

    def __init__(self, subscription_repo: SubscriptionRepository) -> None:
        self._subscription_repo = subscription_repo

    def execute(self, company_id: UUID) -> SubscriptionDTO:
        entity = self._subscription_repo.get_by_company(company_id)
        now = datetime.now(timezone.utc)
        if not entity:
            entity = Subscription(
                company_id=company_id,
                plan_id=FREE_PLAN_ID,
                status=SubscriptionStatus.ACTIVE,
                current_period_start=now,
                current_period_end=now,
            )
            return SubscriptionDTO.from_entity(entity, now)

        # A premium past its paid period (canceled, or active/trialing that was never
        # renewed) has fallen back to free.
        if entity.premium_period_over(now):
            entity.plan_id = FREE_PLAN_ID
            entity.status = SubscriptionStatus.ACTIVE
            entity = self._subscription_repo.update(entity)
        return SubscriptionDTO.from_entity(entity, now)


class UpdateSubscriptionStatus:
    """Updates a subscription status (e.g. via webhook)."""

    def __init__(self, subscription_repo: SubscriptionRepository) -> None:
        self._subscription_repo = subscription_repo

    def execute(
        self,
        company_id: UUID,
        status: SubscriptionStatus,
        plan_id: str | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> SubscriptionDTO:
        entity = self._subscription_repo.get_by_company(company_id)
        now = datetime.now(timezone.utc)

        if entity:
            entity.status = status
            if plan_id:
                entity.plan_id = plan_id
            if period_start:
                entity.current_period_start = period_start
            if period_end:
                entity.current_period_end = period_end
        else:
            entity = Subscription(
                company_id=company_id,
                plan_id=plan_id or "default_plan",
                status=status,
                current_period_start=period_start or now,
                current_period_end=period_end or now,
            )

        # Access lasts only while the paid period does: activating a premium without
        # dates is a monthly renewal from now, not a premium that is already over.
        if period_end is None and entity.premium_period_over(now):
            if period_start is None:
                entity.current_period_start = now
            entity.current_period_end = add_months(entity.current_period_start, 1)
            if entity.period_end_utc() <= now:
                entity.current_period_end = add_months(now, 1)

        saved = (
            self._subscription_repo.update(entity)
            if entity.id is not None
            else self._subscription_repo.add(entity)
        )
        return SubscriptionDTO.from_entity(saved, now)


class Checkout:
    """
    Simulated checkout: validates the (already sanitized) payment data, records a paid
    payment and activates the plan. No card number or CVV ever reaches this layer.
    """

    def __init__(self, subscription_repo: SubscriptionRepository, payment_repo: PaymentRepository) -> None:
        self._subscription_repo = subscription_repo
        self._payment_repo = payment_repo

    def _reference(self) -> str:
        for _ in range(10):
            ref = "PAY-" + "".join(secrets.choice(_REF_ALPHABET) for _ in range(8))
            if not self._payment_repo.reference_exists(ref):
                return ref
        raise PaymentValidationError("No se pudo generar la referencia de pago. Inténtalo de nuevo.")

    def execute(
        self,
        company_id: UUID,
        plan_id: str,
        billing_cycle: BillingCycle,
        method: PaymentMethod,
        card_brand: str | None = None,
        card_last4: str | None = None,
        card_holder: str | None = None,
        yape_code: str | None = None,
    ) -> CheckoutResultDTO:
        plan = get_plan(plan_id)
        if plan is None:
            raise PlanNotFoundError(plan_id)
        if plan.id != PREMIUM_PLAN_ID:
            raise PaymentValidationError("Solo el plan Premium requiere pago", "plan_id")

        last4: str | None = None
        if method == PaymentMethod.CARD:
            if not card_brand or card_brand.lower() not in CARD_BRANDS:
                raise PaymentValidationError("No aceptamos esa marca de tarjeta. Usa Visa, Mastercard u otra de la lista.", "card.brand")
            if not card_last4 or not re.fullmatch(r"\d{4}", card_last4):
                raise PaymentValidationError("La tarjeta no es válida. Revisa el número.", "card.last4")
            if not card_holder or len(card_holder.strip()) < 3:
                raise PaymentValidationError("Ingresa el titular de la tarjeta", "card.holder_name")
            last4 = card_last4
        elif method == PaymentMethod.YAPE:
            if not yape_code or not re.fullmatch(r"\d{6}", yape_code):
                raise PaymentValidationError("El código de aprobación Yape debe tener 6 dígitos", "yape_code")

        now = datetime.now(timezone.utc)
        current = self._subscription_repo.get_by_company(company_id)

        # Renewing an unexpired premium extends from its current end.
        start = now
        if current and current.has_premium_access(now):
            start = current.period_end_utc()
        end = _period_end(start, billing_cycle)

        payment = self._payment_repo.add(
            BillingPayment(
                company_id=company_id,
                plan_id=plan.id,
                billing_cycle=billing_cycle,
                amount=plan.price_for(billing_cycle),
                currency=plan.currency,
                method=method,
                status=PaymentStatus.PAID,
                reference=self._reference(),
                card_last4=last4,
                paid_at=now,
            )
        )

        if current:
            if start == now:
                current.current_period_start = now
            current.plan_id = plan.id
            current.status = SubscriptionStatus.ACTIVE
            current.current_period_end = end
            saved = self._subscription_repo.update(current)
        else:
            saved = self._subscription_repo.add(
                Subscription(
                    company_id=company_id,
                    plan_id=plan.id,
                    status=SubscriptionStatus.ACTIVE,
                    current_period_start=now,
                    current_period_end=end,
                )
            )

        return CheckoutResultDTO(
            payment=PaymentDTO.from_entity(payment),
            subscription=SubscriptionDTO.from_entity(saved, now),
        )


class CheckPremiumAccess:
    """Whether the company may use Premium features right now (the plan enforcement rule).

    Same rule as ``SubscriptionDTO.is_premium``: a canceled Premium keeps access until
    ``current_period_end``; any Premium past that instant is over, whatever its status.
    """

    def __init__(self, subscription_repo: SubscriptionRepository) -> None:
        self._subscription_repo = subscription_repo

    def execute(self, company_id: UUID, now: datetime | None = None) -> bool:
        entity = self._subscription_repo.get_by_company(company_id)
        return bool(entity and entity.has_premium_access(now or datetime.now(timezone.utc)))


class ListPayments:
    def __init__(self, payment_repo: PaymentRepository) -> None:
        self._payment_repo = payment_repo

    def execute(self, company_id: UUID) -> list[PaymentDTO]:
        return [PaymentDTO.from_entity(p) for p in self._payment_repo.list_by_company(company_id)]


class CancelSubscription:
    """Stops renewal: premium stays available until the current period ends."""

    def __init__(self, subscription_repo: SubscriptionRepository) -> None:
        self._subscription_repo = subscription_repo

    def execute(self, company_id: UUID) -> SubscriptionDTO:
        entity = self._subscription_repo.get_by_company(company_id)
        if not entity or entity.plan_id != PREMIUM_PLAN_ID:
            raise PaymentValidationError("No tienes una suscripción Premium para cancelar")
        now = datetime.now(timezone.utc)
        # Past its paid period the premium is already over: there is no renewal to stop
        # (and canceling must not hand out extra time).
        if not entity.has_premium_access(now):
            raise PaymentValidationError(
                "Tu Premium ya venció, así que no hay nada que cancelar. "
                "Puedes volver a contratarlo cuando quieras."
            )
        if entity.status == SubscriptionStatus.CANCELED:
            return SubscriptionDTO.from_entity(entity, now)
        entity.status = SubscriptionStatus.CANCELED
        return SubscriptionDTO.from_entity(self._subscription_repo.update(entity), now)


class ResumeSubscription:
    """Re-enables renewal of a canceled premium that has not expired yet."""

    def __init__(self, subscription_repo: SubscriptionRepository) -> None:
        self._subscription_repo = subscription_repo

    def execute(self, company_id: UUID) -> SubscriptionDTO:
        entity = self._subscription_repo.get_by_company(company_id)
        now = datetime.now(timezone.utc)
        if (
            not entity
            or entity.status != SubscriptionStatus.CANCELED
            or not entity.has_premium_access(now)
        ):
            raise PaymentValidationError("No hay una suscripción Premium cancelada para reactivar")
        entity.status = SubscriptionStatus.ACTIVE
        return SubscriptionDTO.from_entity(self._subscription_repo.update(entity), now)
