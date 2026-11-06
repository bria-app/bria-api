"""Billing module domain — entities."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.modules.billing.domain.enums import (
    BillingCycle,
    PaymentMethod,
    PaymentStatus,
    SubscriptionStatus,
)
from app.modules.billing.domain.plans import PREMIUM_PLAN_ID

#: Statuses that give Premium access while the paid period lasts (past_due never does).
ACCESS_STATUSES = frozenset(
    {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.CANCELED}
)


@dataclass
class Subscription:
    """A company's billing subscription."""

    company_id: UUID
    plan_id: str
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    id: UUID | None = None

    def period_end_utc(self) -> datetime:
        """The paid period's end as an aware UTC instant (naive values are taken as UTC)."""
        end = self.current_period_end
        return end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end

    def is_premium_plan(self) -> bool:
        return self.plan_id == PREMIUM_PLAN_ID

    def premium_period_over(self, now: datetime) -> bool:
        """A Premium that would give access by its status, but whose paid period already ended.

        Active, trialing and canceled all count: with no automatic renewal, an "active"
        Premium past ``current_period_end`` is not paid any more, exactly like a canceled one.
        """
        return (
            self.is_premium_plan()
            and self.status in ACCESS_STATUSES
            and self.period_end_utc() <= now
        )

    def has_premium_access(self, now: datetime) -> bool:
        """Premium features right now: a Premium in an access status inside its paid period.

        Canceling only stops the renewal, so a canceled Premium keeps access until the period ends.
        """
        return (
            self.is_premium_plan()
            and self.status in ACCESS_STATUSES
            and self.period_end_utc() > now
        )


@dataclass
class BillingPayment:
    """A (simulated) payment for a plan. Never holds card numbers or CVV — only last4."""

    company_id: UUID
    plan_id: str
    billing_cycle: BillingCycle
    amount: Decimal
    method: PaymentMethod
    status: PaymentStatus
    reference: str
    paid_at: datetime
    currency: str = "PEN"
    card_last4: str | None = None
    id: UUID | None = None
    created_at: datetime | None = None
