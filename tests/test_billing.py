"""Tests for Billing module."""
from __future__ import annotations

from uuid import UUID, uuid4


from app.modules.billing.application.use_cases.billing import (
    GetSubscription,
    UpdateSubscriptionStatus,
)
from app.modules.billing.domain.entities import Subscription
from app.modules.billing.domain.enums import SubscriptionStatus


class FakeSubscriptionRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, Subscription] = {}

    def get_by_company(self, company_id: UUID) -> Subscription | None:
        return self._store.get(company_id)

    def add(self, subscription: Subscription) -> Subscription:
        if subscription.id is None:
            subscription.id = uuid4()
        self._store[subscription.company_id] = subscription
        return subscription

    def update(self, subscription: Subscription) -> Subscription:
        assert subscription.id is not None
        self._store[subscription.company_id] = subscription
        return subscription


class TestBillingUseCases:
    def test_update_and_get_subscription(self) -> None:
        repo = FakeSubscriptionRepository()
        company_id = uuid4()

        # Update (creates since it doesn't exist)
        updated = UpdateSubscriptionStatus(repo).execute(
            company_id=company_id,
            status=SubscriptionStatus.ACTIVE,
            plan_id="pro_plan",
        )
        assert updated.plan_id == "pro_plan"
        assert updated.status == SubscriptionStatus.ACTIVE

        # Get
        got = GetSubscription(repo).execute(company_id=company_id)
        assert got.id == updated.id

        # Update again (updates existing)
        updated2 = UpdateSubscriptionStatus(repo).execute(
            company_id=company_id,
            status=SubscriptionStatus.CANCELED,
        )
        assert updated2.status == SubscriptionStatus.CANCELED

    def test_unknown_subscription_falls_back_to_free_plan(self) -> None:
        # A company without a subscription row is on the free plan (ERP + FTGM for 1 product).
        repo = FakeSubscriptionRepository()
        got = GetSubscription(repo).execute(company_id=uuid4())
        assert got.plan_id == "free"
        assert got.status == SubscriptionStatus.ACTIVE
