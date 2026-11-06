"""Billing module domain — repository ports."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules.billing.domain.entities import BillingPayment, Subscription


class SubscriptionRepository(Protocol):
    """Port for Subscription persistence."""

    def get_by_company(self, company_id: UUID) -> Subscription | None: ...
    def add(self, subscription: Subscription) -> Subscription: ...
    def update(self, subscription: Subscription) -> Subscription: ...


class PaymentRepository(Protocol):
    """Port for BillingPayment persistence."""

    def add(self, payment: BillingPayment) -> BillingPayment: ...
    def list_by_company(self, company_id: UUID, limit: int = 50) -> list[BillingPayment]: ...
    def reference_exists(self, reference: str) -> bool: ...
