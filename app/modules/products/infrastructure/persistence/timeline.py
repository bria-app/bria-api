"""Products module — "Product 360" read model.

Everything that ever happened to one product, merged into a single timeline: POS or
imported sale lines, supplier restocks, stock adjustments and lost sales (quiebres).
Plus the stats and series the product page charts. Read-only queries across the
sales, purchases, suppliers and inventory tables.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session

from app.modules.inventory.infrastructure.persistence.models import InventoryMovementModel
from app.modules.inventory.infrastructure.persistence.overview import forecast_daily_rates
from app.modules.products.application.dtos import (
    MonthlySalesPointDTO,
    ProductDTO,
    ProductTimelineDTO,
    StockPointDTO,
    TimelineEventDTO,
    TimelineStatsDTO,
    WeeklySalesPointDTO,
)
from app.modules.products.domain.exceptions import ProductNotFoundError
from app.modules.products.infrastructure.persistence.mappers import product_to_entity
from app.modules.products.infrastructure.persistence.models import CategoryModel, ProductModel
from app.modules.purchases.infrastructure.persistence.models import PurchaseModel
from app.modules.sales.infrastructure.persistence.models import (
    LostSaleModel,
    SaleModel,
    SalesOrderModel,
)
from app.modules.suppliers.infrastructure.persistence.models import SupplierModel
from app.shared.infrastructure.database.portable import greatest

LIMA = ZoneInfo("America/Lima")
STOCK_SERIES_DAYS = 180
MONTHLY_SERIES_MONTHS = 24  # two years, so each month can be read against the same month a year before
WEEKLY_SERIES_WEEKS = 25  # fits inside the stock series, so every week knows its stockout days
# Legacy movements written before reference_type existed; they duplicate a sale/purchase row.
_LEGACY_MIRROR_REASONS = ("Compra a proveedor", "Venta manual")


def _local_date(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LIMA).date()


def _aware(moment: datetime) -> datetime:
    """Stored timestamps are UTC; some backends (SQLite) hand them back without tzinfo."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _at(day: date, created_at: datetime | None) -> datetime:
    """Best timestamp for a dated document: its creation time when created that same day."""
    if created_at is not None:
        created = _aware(created_at)
        if _local_date(created) == day:
            return created
    return datetime.combine(day, time(12, 0), tzinfo=LIMA)


def category_path(session: Session, category_id: UUID | None) -> list[str]:
    path: list[str] = []
    seen: set[UUID] = set()
    while category_id is not None and category_id not in seen:
        seen.add(category_id)
        cat = session.get(CategoryModel, category_id)
        if cat is None:
            break
        path.insert(0, cat.name)
        category_id = cat.parent_id
    return path


class SqlProductTimelineQuery:
    def __init__(self, session: Session) -> None:
        self._s = session

    def execute(self, company_id: UUID, product_id: UUID, limit: int = 150) -> ProductTimelineDTO:
        s = self._s
        model = s.get(ProductModel, product_id)
        if model is None or model.company_id != company_id:
            raise ProductNotFoundError(product_id)
        avg_cost = Decimal(model.unit_cost)
        today = datetime.now(LIMA).date()
        truncated = False
        events: list[TimelineEventDTO] = []

        # --- Sales ----------------------------------------------------------
        sale_rows = s.execute(
            select(SaleModel, SalesOrderModel.order_number, SalesOrderModel.sold_at)
            .outerjoin(SalesOrderModel, SalesOrderModel.id == SaleModel.order_id)
            .where(SaleModel.company_id == company_id, SaleModel.product_id == product_id)
            .order_by(SaleModel.sale_date.desc(), SaleModel.created_at.desc())
            .limit(limit + 1)
        ).all()
        truncated |= len(sale_rows) > limit
        for sale, order_number, sold_at in sale_rows[:limit]:
            events.append(
                TimelineEventDTO(
                    id=sale.id,
                    kind="sale",
                    occurred_at=_aware(sold_at) if sold_at else _at(sale.sale_date, sale.created_at),
                    quantity=sale.quantity,
                    unit_price=sale.unit_price,
                    total=sale.total_amount,
                    unit_cost=sale.unit_cost,
                    order_id=sale.order_id,
                    order_number=order_number,
                    batch_id=sale.batch_id,
                    seller_name=sale.seller_name or None,
                )
            )

        # --- Restocks (purchases) --------------------------------------------
        purchase_rows = s.execute(
            select(PurchaseModel, SupplierModel.business_name)
            .outerjoin(SupplierModel, SupplierModel.id == PurchaseModel.supplier_id)
            .where(PurchaseModel.company_id == company_id, PurchaseModel.product_id == product_id)
            .order_by(PurchaseModel.purchase_date.desc(), PurchaseModel.created_at.desc())
            .limit(limit + 1)
        ).all()
        truncated |= len(purchase_rows) > limit
        for purchase, supplier_name in purchase_rows[:limit]:
            events.append(
                TimelineEventDTO(
                    id=purchase.id,
                    kind="restock",
                    occurred_at=_at(purchase.purchase_date, purchase.created_at),
                    quantity=purchase.quantity,
                    unit_cost=purchase.unit_cost,
                    total=purchase.total_amount,
                    supplier_id=purchase.supplier_id,
                    supplier_name=supplier_name,
                    document_number=purchase.document_number or None,
                    purchase_id=purchase.id,
                )
            )
        restock_count, last_restock = s.execute(
            select(func.count(PurchaseModel.id), func.max(PurchaseModel.purchase_date)).where(
                PurchaseModel.company_id == company_id, PurchaseModel.product_id == product_id
            )
        ).one()

        # --- Other movements (adjustments, initial stock, imports, voids) ----
        mirror_filter = or_(
            InventoryMovementModel.reference_type.is_(None),
            InventoryMovementModel.reference_type.notin_(("sale", "purchase")),
        )
        legacy_filter = not_(
            and_(
                InventoryMovementModel.reference_type.is_(None),
                InventoryMovementModel.reason.in_(_LEGACY_MIRROR_REASONS),
            )
        )
        movement_rows = s.execute(
            select(InventoryMovementModel)
            .where(
                InventoryMovementModel.company_id == company_id,
                InventoryMovementModel.product_id == product_id,
                mirror_filter,
                legacy_filter,
            )
            .order_by(InventoryMovementModel.occurred_at.desc())
            .limit(limit + 1)
        ).scalars().all()
        truncated |= len(movement_rows) > limit
        for mv in movement_rows[:limit]:
            events.append(
                TimelineEventDTO(
                    id=mv.id,
                    kind="adjustment",
                    occurred_at=_aware(mv.occurred_at),
                    quantity=mv.quantity,
                    signed_quantity=-mv.quantity if mv.movement_type == "outbound" else mv.quantity,
                    movement_type=mv.movement_type,
                    unit_cost=mv.unit_cost,
                    reason=mv.reason or None,
                    reference_type=mv.reference_type,
                    reference_id=mv.reference_id,
                )
            )

        # --- Lost sales (quiebres) ------------------------------------------
        lost_by_day: dict[date, int] = defaultdict(int)
        for occurred_at, requested, available in s.execute(
            select(LostSaleModel.occurred_at, LostSaleModel.requested_quantity, LostSaleModel.available_quantity).where(
                LostSaleModel.company_id == company_id,
                LostSaleModel.product_id == product_id,
                LostSaleModel.occurred_at >= datetime.combine(today - timedelta(days=MONTHLY_SERIES_MONTHS * 31), time.min, tzinfo=LIMA),
            )
        ).all():
            lost_by_day[_local_date(occurred_at)] += max(requested - available, 0)

        lost_rows = s.execute(
            select(LostSaleModel)
            .where(LostSaleModel.company_id == company_id, LostSaleModel.product_id == product_id)
            .order_by(LostSaleModel.occurred_at.desc())
            .limit(limit + 1)
        ).scalars().all()
        truncated |= len(lost_rows) > limit
        for ls in lost_rows[:limit]:
            events.append(
                TimelineEventDTO(
                    id=ls.id,
                    kind="lost_sale",
                    occurred_at=_aware(ls.occurred_at),
                    quantity=max(ls.requested_quantity - ls.available_quantity, 0),
                    requested_quantity=ls.requested_quantity,
                    available_quantity=ls.available_quantity,
                    seller_name=ls.seller_name or None,
                    source=ls.source,
                )
            )
        since_30 = datetime.combine(today - timedelta(days=30), time.min, tzinfo=LIMA)
        lost_attempts, lost_units, lost_30 = s.execute(
            select(
                func.count(LostSaleModel.id),
                func.coalesce(
                    func.sum(
                        greatest(LostSaleModel.requested_quantity - LostSaleModel.available_quantity, 0)
                    ),
                    0,
                ),
                func.count(LostSaleModel.id).filter(LostSaleModel.occurred_at >= since_30),
            ).where(LostSaleModel.company_id == company_id, LostSaleModel.product_id == product_id)
        ).one()

        events.sort(key=lambda e: e.occurred_at, reverse=True)

        # --- Sales stats + monthly series ------------------------------------
        first_month = date(today.year, today.month, 1)
        for _ in range(MONTHLY_SERIES_MONTHS - 1):
            first_month = (first_month - timedelta(days=1)).replace(day=1)
        window_start = min(first_month, today - timedelta(days=365))
        window = s.execute(
            select(SaleModel.sale_date, SaleModel.quantity, SaleModel.total_amount, SaleModel.unit_cost).where(
                SaleModel.company_id == company_id,
                SaleModel.product_id == product_id,
                SaleModel.sale_date >= window_start,
            )
        ).all()
        units = {30: 0, 90: 0, 365: 0}
        revenue_365 = Decimal("0")
        cost_365 = Decimal("0")
        monthly_units: dict[str, int] = defaultdict(int)
        monthly_revenue: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        daily_units: dict[date, int] = defaultdict(int)
        daily_revenue: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
        for sale_date, qty, total, unit_cost in window:
            daily_units[sale_date] += qty
            daily_revenue[sale_date] += Decimal(total)
            age = (today - sale_date).days
            for days in units:
                if 0 <= age < days:
                    units[days] += qty
            if 0 <= age < 365:
                revenue_365 += Decimal(total)
                cost_365 += Decimal(unit_cost if unit_cost is not None else avg_cost) * qty
            if sale_date >= first_month:
                key = sale_date.strftime("%Y-%m")
                monthly_units[key] += qty
                monthly_revenue[key] += Decimal(total)
        monthly: list[MonthlySalesPointDTO] = []
        cursor = first_month
        while cursor <= today:
            key = cursor.strftime("%Y-%m")
            lost = sum(v for d, v in lost_by_day.items() if d.strftime("%Y-%m") == key)
            monthly.append(MonthlySalesPointDTO(month=key, units=monthly_units[key], revenue=monthly_revenue[key], lost_units=lost))
            cursor = (cursor + timedelta(days=32)).replace(day=1)
        last_sale_at = s.execute(
            select(func.max(SaleModel.sale_date)).where(
                SaleModel.company_id == company_id, SaleModel.product_id == product_id
            )
        ).scalar_one()

        # --- Stock series (running balance of the ledger) ---------------------
        series_start = today - timedelta(days=STOCK_SERIES_DAYS - 1)
        start_dt = datetime.combine(series_start, time.min, tzinfo=LIMA)
        opening_rows = s.execute(
            select(InventoryMovementModel.movement_type, func.coalesce(func.sum(InventoryMovementModel.quantity), 0))
            .where(
                InventoryMovementModel.company_id == company_id,
                InventoryMovementModel.product_id == product_id,
                InventoryMovementModel.occurred_at < start_dt,
            )
            .group_by(InventoryMovementModel.movement_type)
        ).all()
        balance = sum(-int(q) if t == "outbound" else int(q) for t, q in opening_rows)
        daily_in: dict[date, int] = defaultdict(int)
        daily_out: dict[date, int] = defaultdict(int)
        for occurred_at, mtype, qty in s.execute(
            select(InventoryMovementModel.occurred_at, InventoryMovementModel.movement_type, InventoryMovementModel.quantity).where(
                InventoryMovementModel.company_id == company_id,
                InventoryMovementModel.product_id == product_id,
                InventoryMovementModel.occurred_at >= start_dt,
            )
        ).all():
            day = _local_date(occurred_at)
            if mtype == "outbound":
                daily_out[day] += qty
            else:
                daily_in[day] += qty
        series: list[StockPointDTO] = []
        for i in range(STOCK_SERIES_DAYS):
            day = series_start + timedelta(days=i)
            balance += daily_in[day] - daily_out[day]
            series.append(StockPointDTO(date=day, stock=balance, inbound=daily_in[day], outbound=daily_out[day]))
        stock_by_day = {p.date: p.stock for p in series}

        # --- Weekly series: sales, days without stock and unmet demand ---------
        week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=WEEKLY_SERIES_WEEKS - 1)
        weekly: list[WeeklySalesPointDTO] = []
        weekday_units = [0] * 7
        for w in range(WEEKLY_SERIES_WEEKS):
            days = [week_start + timedelta(days=w * 7 + i) for i in range(7)]
            days = [d for d in days if d <= today]
            for d in days:
                weekday_units[d.weekday()] += daily_units[d]
            weekly.append(
                WeeklySalesPointDTO(
                    week_start=days[0],
                    units=sum(daily_units[d] for d in days),
                    revenue=sum((daily_revenue[d] for d in days), Decimal("0")),
                    stockout_days=sum(1 for d in days if d in stock_by_day and stock_by_day[d] <= 0),
                    lost_units=sum(lost_by_day[d] for d in days),
                )
            )

        # Movements dated in the future (rare) still count toward today's balance.
        future = sum(v for d, v in daily_in.items() if d > today) - sum(v for d, v in daily_out.items() if d > today)
        on_hand = balance + future

        avg_price = (revenue_365 / units[365]).quantize(Decimal("0.01")) if units[365] else None
        margin = float(((revenue_365 - cost_365) / revenue_365) * 100) if revenue_365 > 0 else None
        # Same pace rule as the inventory overview: the latest forecast when there is
        # one, else the last 30 days — so every screen quotes the same coverage.
        forecast_rate = forecast_daily_rates(s, company_id).get(product_id)
        daily_rate = forecast_rate if forecast_rate else (units[30] / 30 if units[30] > 0 else None)
        coverage = round(on_hand / daily_rate, 1) if daily_rate else None

        stats = TimelineStatsDTO(
            stock_on_hand=on_hand,
            units_sold_30d=units[30],
            units_sold_90d=units[90],
            units_sold_365d=units[365],
            revenue_365d=revenue_365.quantize(Decimal("0.01")),
            avg_price_365d=avg_price,
            gross_margin_pct=round(margin, 1) if margin is not None else None,
            coverage_days=max(coverage, 0.0) if coverage is not None else None,
            lost_sale_attempts=int(lost_attempts or 0),
            lost_units=int(lost_units or 0),
            lost_sale_attempts_30d=int(lost_30 or 0),
            restock_count=int(restock_count or 0),
            last_restock_at=last_restock,
            last_sale_at=last_sale_at,
        )
        return ProductTimelineDTO(
            product=ProductDTO.from_entity(product_to_entity(model)),
            category_path=category_path(s, model.category_id),
            stats=stats,
            events=events,
            events_truncated=truncated,
            stock_series=series,
            monthly_sales=monthly,
            weekly_sales=weekly,
            weekday_units=weekday_units,
        )
