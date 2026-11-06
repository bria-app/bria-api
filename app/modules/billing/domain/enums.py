"""Billing module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class BillingCycle(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class PaymentMethod(StrEnum):
    CARD = "card"
    YAPE = "yape"
    TRANSFER = "transferencia"


class PaymentStatus(StrEnum):
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
