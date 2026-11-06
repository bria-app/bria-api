"""Sales module domain — pure helpers (time zone, numbering)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.modules.sales.domain.enums import SalesDocumentType

# Store business day is Peru time; timestamps are stored in UTC.
LIMA = ZoneInfo("America/Lima")


def lima_today() -> date:
    return datetime.now(LIMA).date()


def lima_date(moment: datetime) -> date:
    """Lima calendar day of a timestamp; a naive one is taken as UTC (how it is stored)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(LIMA).date()


def lima_day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """[start 00:00, end+1 00:00) in Lima time, as aware datetimes."""
    return (
        datetime.combine(start, time.min, tzinfo=LIMA),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=LIMA),
    )


def nota_venta_number(order_number: int) -> str:
    return f"NV-{order_number:06d}"


def document_number(
    document_type: str, order_number: int, series: str | None, correlativo: int | None
) -> str:
    """B001-00000012 / F001-00000003 for comprobantes, NV-000045 for internal tickets."""
    if document_type != SalesDocumentType.NOTA_VENTA and series and correlativo:
        return f"{series}-{correlativo:08d}"
    return nota_venta_number(order_number)
