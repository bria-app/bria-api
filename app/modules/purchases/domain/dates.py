"""Purchases module domain — purchase dates in Lima time.

The shop lives in Peru: "today" is the calendar day in America/Lima (UTC-5, no DST),
not the server's UTC day. A purchase cannot be dated after today, because its stock
would be counted at once for goods that have not arrived yet.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo

try:
    from zoneinfo import ZoneInfo

    LIMA: tzinfo = ZoneInfo("America/Lima")
except Exception:  # noqa: BLE001 — no tz database (e.g. Windows without tzdata)
    LIMA = timezone(timedelta(hours=-5), "America/Lima")


def lima_today(now: datetime | None = None) -> date:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(LIMA).date()


def is_future(day: date, now: datetime | None = None) -> bool:
    return day > lima_today(now)


def occurred_at(purchase_date: date, now: datetime | None = None) -> datetime:
    """Today's purchases happen now; back-dated ones are placed at noon (Lima) of that day."""
    moment = now or datetime.now(timezone.utc)
    if purchase_date >= lima_today(moment):
        return moment
    return datetime.combine(purchase_date, time(12, 0), tzinfo=LIMA).astimezone(timezone.utc)
