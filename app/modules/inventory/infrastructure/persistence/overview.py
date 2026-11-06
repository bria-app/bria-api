"""Inventory module — read models for the inventory table and its valuation.

One pass over the catalog joined with aggregated ledger, sales and lost-sales data,
so the main inventory screen needs a single request.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.forecasting.infrastructure.persistence.models import (
    ForecastResultModel,
    ForecastRunModel,
)
from app.modules.inventory.application.dtos import (
    InventoryOverviewDTO,
    InventoryOverviewItemDTO,
    InventoryTotalsDTO,
    InventoryValuationDTO,
    StatusCountsDTO,
    ValuationGroupDTO,
)
from app.modules.inventory.infrastructure.persistence.models import InventoryMovementModel
from app.modules.inventory.infrastructure.persistence.queries import stock_on_hand_map
from app.modules.products.infrastructure.persistence.models import CategoryModel, ProductModel
from app.modules.recommendations.domain.services import SAFETY_MARGIN_DAYS, effective_lead_time
from app.modules.sales.infrastructure.persistence.models import LostSaleModel, SaleModel

LIMA = ZoneInfo("America/Lima")
_CENT = Decimal("0.01")


_MONTH_DAYS = 30.4375


def stock_status(on_hand: int, safety_stock: int, reorder_point: int) -> str:
    if on_hand <= 0:
        return "sin_stock"
    if on_hand <= safety_stock:
        return "critico"
    if on_hand <= reorder_point:
        return "reordenar"
    return "ok"


def forecast_daily_rates(session: Session, company_id: UUID, runs: int = 20) -> dict[UUID, float]:
    """Expected units per day from the newest successful forecast that covers each product.

    Inventory, "Mis números", "Qué comprar" and the forecast's action plan then all judge
    "how long will it last" with the same number (the forecast), not two different paces.
    """
    rates: dict[UUID, float] = {}
    run_rows = session.execute(
        select(ForecastRunModel.id, ForecastRunModel.frequency)
        .where(ForecastRunModel.company_id == company_id, ForecastRunModel.status == "success")
        .order_by(ForecastRunModel.created_at.desc())
        .limit(runs)
    ).all()
    for run_id, frequency in run_rows:
        results = session.execute(
            select(ForecastResultModel.product_id, ForecastResultModel.points).where(
                ForecastResultModel.run_id == run_id
            )
        ).all()
        for product_id, points in results:
            if product_id in rates or not points:
                continue
            if len(points) >= 2:
                gap = (date.fromisoformat(points[1]["period_date"]) - date.fromisoformat(points[0]["period_date"])).days
                days = 7.0 if gap <= 8 else _MONTH_DAYS
            else:
                days = 7.0 if frequency == "weekly" else _MONTH_DAYS
            rates[product_id] = max(0.0, float(points[0]["predicted_demand"])) / days
    return rates


class SqlInventoryOverviewQuery:
    def __init__(self, session: Session) -> None:
        self._s = session

    def _category_paths(self, company_id: UUID) -> dict[UUID, list[str]]:
        cats = {
            c.id: c
            for c in self._s.execute(
                select(CategoryModel).where(CategoryModel.company_id == company_id)
            ).scalars()
        }
        paths: dict[UUID, list[str]] = {}
        for cid in cats:
            path: list[str] = []
            cursor: UUID | None = cid
            seen: set[UUID] = set()
            while cursor is not None and cursor in cats and cursor not in seen:
                seen.add(cursor)
                path.insert(0, cats[cursor].name)
                cursor = cats[cursor].parent_id
            paths[cid] = path
        return paths

    def overview(self, company_id: UUID, include_inactive: bool = False) -> InventoryOverviewDTO:
        s = self._s
        stmt = select(ProductModel).where(ProductModel.company_id == company_id)
        if not include_inactive:
            stmt = stmt.where(ProductModel.is_active.is_(True))
        products = s.execute(stmt.order_by(ProductModel.name)).scalars().all()

        paths = self._category_paths(company_id)
        on_hand = stock_on_hand_map(s, company_id)
        last_move: dict[UUID, datetime] = {
            product_id: occurred_at
            for product_id, occurred_at in s.execute(
                select(InventoryMovementModel.product_id, func.max(InventoryMovementModel.occurred_at))
                .where(InventoryMovementModel.company_id == company_id)
                .group_by(InventoryMovementModel.product_id)
            ).all()
        }
        today = datetime.now(LIMA).date()
        since = today - timedelta(days=29)
        sold_30 = {
            pid: int(q or 0)
            for pid, q in s.execute(
                select(SaleModel.product_id, func.sum(SaleModel.quantity))
                .where(SaleModel.company_id == company_id, SaleModel.sale_date >= since)
                .group_by(SaleModel.product_id)
            ).all()
        }
        since_dt = datetime.combine(since, time.min, tzinfo=LIMA)
        lost_30 = {
            pid: int(n or 0)
            for pid, n in s.execute(
                select(LostSaleModel.product_id, func.count(LostSaleModel.id))
                .where(LostSaleModel.company_id == company_id, LostSaleModel.occurred_at >= since_dt)
                .group_by(LostSaleModel.product_id)
            ).all()
        }

        forecast_rates = forecast_daily_rates(s, company_id)

        items: list[InventoryOverviewItemDTO] = []
        counts: dict[str, int] = defaultdict(int)
        units_total = 0
        value_cost = Decimal("0")
        value_retail = Decimal("0")
        for p in products:
            qty = on_hand.get(p.id, 0)
            positive = max(qty, 0)
            cost = Decimal(p.unit_cost)
            price = Decimal(p.unit_price)
            stock_value = (cost * positive).quantize(_CENT)
            retail_value = (price * positive).quantize(_CENT)
            status = stock_status(qty, p.safety_stock, p.reorder_point)
            sold = sold_30.get(p.id, 0)
            # Pace: the latest forecast when there is one, else the last 30 days of sales.
            daily = forecast_rates.get(p.id, sold / 30)
            coverage = round(positive / daily, 1) if daily > 0 else None
            # Owners rarely set reorder points: also flag products whose stock won't last
            # the supplier's wait plus two weeks (plus their minimum stock).
            window = effective_lead_time(p.lead_time_days) + SAFETY_MARGIN_DAYS
            if status == "ok" and daily > 0 and positive < daily * window + p.safety_stock:
                status = "reordenar"
            path = paths.get(p.category_id, []) if p.category_id else []
            last = last_move.get(p.id)
            if last is not None and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            items.append(
                InventoryOverviewItemDTO(
                    id=p.id,
                    sku=p.sku,
                    name=p.name,
                    description=p.description,
                    barcode=p.barcode,
                    image_url=p.image_url,
                    category_id=p.category_id,
                    category_name=path[-1] if path else None,
                    category_path=path,
                    unit_cost=cost,
                    last_cost=p.last_cost,
                    unit_price=price,
                    currency=p.currency,
                    unit_of_measure=p.unit_of_measure,
                    lead_time_days=p.lead_time_days,
                    safety_stock=p.safety_stock,
                    reorder_point=p.reorder_point,
                    is_active=p.is_active,
                    custom_attributes=dict(p.custom_attributes or {}),
                    stock_on_hand=qty,
                    stock_value=stock_value,
                    retail_value=retail_value,
                    status=status,  # type: ignore[arg-type]
                    last_movement_at=last,
                    units_sold_30d=sold,
                    coverage_days=coverage,
                    lost_sales_30d=lost_30.get(p.id, 0),
                )
            )
            counts[status] += 1
            units_total += positive
            value_cost += stock_value
            value_retail += retail_value

        totals = InventoryTotalsDTO(
            products=len(items),
            units_on_hand=units_total,
            inventory_value_cost=value_cost.quantize(_CENT),
            inventory_value_retail=value_retail.quantize(_CENT),
            potential_margin=(value_retail - value_cost).quantize(_CENT),
            status_counts=StatusCountsDTO(**counts),
        )
        return InventoryOverviewDTO(items=items, totals=totals, generated_at=datetime.now(timezone.utc))

    def valuation(self, company_id: UUID) -> InventoryValuationDTO:
        data = self.overview(company_id)
        total_cost = data.totals.inventory_value_cost or Decimal("0")

        def group(key_fn) -> list[ValuationGroupDTO]:  # type: ignore[no-untyped-def]
            buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
            for item in data.items:
                key, cid, path = key_fn(item)
                b = buckets.setdefault(
                    key,
                    {"category_id": cid, "path": path, "products": 0, "units": 0,
                     "value_cost": Decimal("0"), "value_retail": Decimal("0")},
                )
                b["products"] += 1
                b["units"] += max(item.stock_on_hand, 0)
                b["value_cost"] += item.stock_value or Decimal("0")
                b["value_retail"] += item.retail_value
            out = [
                ValuationGroupDTO(
                    category_id=b["category_id"],
                    name=b["path"][-1] if b["path"] else "Sin categoría",
                    path=b["path"],
                    products=b["products"],
                    units=b["units"],
                    value_cost=b["value_cost"].quantize(_CENT),
                    value_retail=b["value_retail"].quantize(_CENT),
                    share_pct=round(float(b["value_cost"] / total_cost * 100), 1) if total_cost > 0 else 0.0,
                )
                for b in buckets.values()
            ]
            return sorted(out, key=lambda g: g.value_cost or Decimal("0"), reverse=True)

        def by_leaf(item: InventoryOverviewItemDTO):  # type: ignore[no-untyped-def]
            return (item.category_id,), item.category_id, item.category_path

        roots: dict[str, UUID | None] = {}
        for c in self._s.execute(
            select(CategoryModel).where(CategoryModel.company_id == company_id, CategoryModel.parent_id.is_(None))
        ).scalars():
            roots[c.name] = c.id

        def by_root(item: InventoryOverviewItemDTO):  # type: ignore[no-untyped-def]
            root = item.category_path[0] if item.category_path else None
            return (root,), roots.get(root) if root else None, [root] if root else []

        return InventoryValuationDTO(totals=data.totals, by_category=group(by_leaf), by_brand=group(by_root))
