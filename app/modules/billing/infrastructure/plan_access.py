"""Billing — Premium access check for other modules (the plan enforcement entry point).

Other modules (forecasting's monthly quota) must ask billing instead of reading the
subscription row themselves, so "who has Premium" has a single rule: the one in
``Subscription.has_premium_access`` (a canceled Premium keeps access until
``current_period_end``; any Premium past that instant is over, whatever its status).
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.billing.application.use_cases.billing import CheckPremiumAccess
from app.modules.billing.infrastructure.persistence.repositories import SqlSubscriptionRepository


def company_has_premium_access(
    session: Session, company_id: UUID, now: datetime | None = None
) -> bool:
    return CheckPremiumAccess(SqlSubscriptionRepository(session)).execute(company_id, now)
