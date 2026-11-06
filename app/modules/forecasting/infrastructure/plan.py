"""Forecasting — plan lookup and the free plan's monthly prediction quota."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.billing.infrastructure.plan_access import company_has_premium_access
from app.modules.forecasting.infrastructure.persistence.models import ForecastRunModel


#: Free plan: any scope (whole catalog included), up to this many runs per month.
FREE_MONTHLY_RUNS = 3

_LIMA = timezone(timedelta(hours=-5))


def company_is_premium(session: Session, company_id: UUID) -> bool:
    """Premium while the paid period lasts (one rule with billing: a canceled Premium keeps
    access until its period ends; an active one past its end is no longer Premium)."""
    return company_has_premium_access(session, company_id)


def runs_used_this_month(session: Session, company_id: UUID) -> int:
    """Forecast runs launched this calendar month (Lima). Failed/cancelled don't count."""
    month_start = datetime.now(_LIMA).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(
        session.execute(
            select(func.count()).where(
                ForecastRunModel.company_id == company_id,
                ForecastRunModel.created_at >= month_start.astimezone(timezone.utc),
                ForecastRunModel.status.not_in(("failed", "cancelled")),
            )
        ).scalar_one()
    )
