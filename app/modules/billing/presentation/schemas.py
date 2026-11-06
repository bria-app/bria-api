"""Billing module — HTTP schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.billing.application.dtos import SubscriptionDTO
from app.modules.billing.domain.enums import SubscriptionStatus


class SubscriptionResponse(SubscriptionDTO):
    """Response schema for a company's subscription."""
    pass


class SubscriptionRequest(BaseModel):
    """Request schema for creating/updating a subscription."""
    plan_id: str = Field(..., min_length=1, max_length=50)


class WebhookUpdateSubscriptionRequest(BaseModel):
    """Payload for updating subscription via webhook."""
    status: SubscriptionStatus
    plan_id: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None


class CheckoutCard(BaseModel):
    """Only brand + last4 + holder. Extra fields (number, cvv…) are rejected outright."""

    model_config = ConfigDict(extra="forbid")

    brand: Literal["visa", "mastercard", "amex", "diners"]
    last4: str = Field(..., pattern=r"^\d{4}$")
    holder_name: str = Field(..., min_length=3, max_length=80)


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: Literal["premium"] = "premium"
    billing_cycle: Literal["monthly", "yearly"] = "monthly"
    method: Literal["card", "yape", "transferencia"]
    card: CheckoutCard | None = None
    yape_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    billing_ruc: str | None = Field(default=None, pattern=r"^\d{8}$|^\d{11}$")
    billing_name: str | None = Field(default=None, max_length=160)


# Placeholders for endpoints not fully implemented
class PaymentWebhookResponse(BaseModel):
    message: str
    module: str
    action: str

class InvoiceResponse(BaseModel):
    message: str
    module: str
    action: str
