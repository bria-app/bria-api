"""Dashboard — ERP summary read model (works without any FTGM run).

Revenue comes from the ``sales`` table, which holds both POS ticket lines and legacy /
imported rows; lines of voided tickets are excluded. Tickets come from ``sales_orders``.
Stock is derived from the movement ledger. Dates are Lima dates (UTC-5).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.modules.forecasting.infrastructure.persistence.models import ForecastRunModel
from app.modules.inventory.infrastructure.persistence.queries import stock_on_hand_map
from app.modules.products.infrastructure.persistence.models import ProductModel
from app.modules.purchases.infrastructure.persistence.models import PurchaseModel
from app.modules.sales.domain.enums import OrderStatus
from app.modules.sales.infrastructure.persistence.models import (
    LostSaleModel,
    SaleModel,
    SalesOrderModel,
)
from app.shared.infrastructure.database.portable import greatest, lima_date

_LIMA = timezone(timedelta(hours=-5))


def _f(value: Any) -> float:
    return float(value or 0)


class SqlErpSummaryReader:
    def __init__(self, session: Session) -> None:
        self._s = session

    def _valid_sales(self, company_id: UUID, start: date, end_exclusive: date) -> Any:
        """Sales lines in [start, end) that do not belong to a voided ticket."""
        return (
            select(SaleModel)
            .outerjoin(SalesOrderModel, SalesOrderModel.id == SaleModel.order_id)
            .where(
                SaleModel.company_id == company_id,
                SaleModel.sale_date >= start,
                SaleModel.sale_date < end_exclusive,
                or_(SalesOrderModel.id.is_(None), SalesOrderModel.status != OrderStatus.VOIDED.value),
            )
        )

    def _revenue(self, company_id: UUID, start: date, end_exclusive: date) -> tuple[float, int]:
        sub = self._valid_sales(company_id, start, end_exclusive).subquery()
        total, units = self._s.execute(
            select(func.coalesce(func.sum(sub.c.total_amount), 0), func.coalesce(func.sum(sub.c.quantity), 0))
        ).one()
        return _f(total), int(units or 0)

    def summary(self, company_id: UUID) -> dict[str, Any]:
        today = datetime.now(_LIMA).date()
        tomorrow = today + timedelta(days=1)
        d7 = today - timedelta(days=6)
        d30 = today - timedelta(days=29)
        prev30 = d30 - timedelta(days=30)

        rev_today, units_today = self._revenue(company_id, today, tomorrow)
        rev_7, _ = self._revenue(company_id, d7, tomorrow)
        rev_30, units_30 = self._revenue(company_id, d30, tomorrow)
        rev_prev_30, _ = self._revenue(company_id, prev30, d30)

        order_day = lima_date(SalesOrderModel.sold_at)
        completed = and_(
            SalesOrderModel.company_id == company_id,
            SalesOrderModel.status != OrderStatus.VOIDED.value,
        )
        tickets_30, tickets_total_30 = self._s.execute(
            select(func.count(), func.coalesce(func.sum(SalesOrderModel.total), 0)).where(
                completed, order_day >= d30
            )
        ).one()
        tickets_today = int(
            self._s.execute(select(func.count()).where(completed, order_day == today)).scalar_one()
        )

        # Sales by day (30d): revenue + units from sales lines, tickets from orders.
        sub = self._valid_sales(company_id, d30, tomorrow).subquery()
        by_day_rows = self._s.execute(
            select(sub.c.sale_date, func.sum(sub.c.total_amount), func.sum(sub.c.quantity)).group_by(sub.c.sale_date)
        ).all()
        tickets_by_day: dict[Any, int] = {
            day: int(count)
            for day, count in self._s.execute(
                select(order_day, func.count()).where(completed, order_day >= d30).group_by(order_day)
            ).all()
        }
        by_day = {d: (_f(r), int(u or 0)) for d, r, u in by_day_rows}
        sales_by_day = []
        for i in range(30):
            d = d30 + timedelta(days=i)
            r, u = by_day.get(d, (0.0, 0))
            sales_by_day.append(
                {"date": d.isoformat(), "revenue": round(r, 2), "units": u, "tickets": int(tickets_by_day.get(d, 0))}
            )

        # Per-product sales (30d): feeds the top AND bottom rankings.
        per_product = self._s.execute(
            select(sub.c.product_id, func.sum(sub.c.total_amount).label("rev"), func.sum(sub.c.quantity))
            .group_by(sub.c.product_id)
            .order_by(func.sum(sub.c.total_amount).desc())
        ).all()
        top_rows = per_product[:6]

        # Gross margin (30d): what was sold minus what those units cost.
        cost_30 = _f(
            self._s.execute(
                select(func.coalesce(func.sum(func.coalesce(sub.c.unit_cost, 0) * sub.c.quantity), 0))
            ).scalar_one()
        )
        gross_margin_30 = rev_30 - cost_30

        products = {
            p.id: p
            for p in self._s.execute(
                select(ProductModel).where(ProductModel.company_id == company_id, ProductModel.is_active.is_(True))
            ).scalars().all()
        }
        top_products = [
            {
                "product_id": str(pid),
                "sku": products[pid].sku if pid in products else "",
                "name": products[pid].name if pid in products else "Producto inactivo",
                "revenue": round(_f(rev), 2),
                "units": int(units or 0),
            }
            for pid, rev, units in top_rows
        ]

        stock = stock_on_hand_map(self._s, company_id)
        inventory_value = Decimal("0")
        low_stock: list[dict[str, Any]] = []
        out_of_stock = 0
        for pid, p in products.items():
            on_hand = stock.get(pid, 0)
            if on_hand > 0:
                inventory_value += Decimal(on_hand) * (p.unit_cost or Decimal("0"))
            else:
                out_of_stock += 1
            if on_hand <= p.safety_stock:
                low_stock.append(
                    {
                        "product_id": str(pid),
                        "sku": p.sku,
                        "name": p.name,
                        "on_hand": on_hand,
                        "safety_stock": p.safety_stock,
                        "reorder_point": p.reorder_point,
                    }
                )
        low_stock.sort(key=lambda r: (r["on_hand"] - r["safety_stock"], r["on_hand"]))

        # Bottom products (30d): active, with stock on hand, fewest units sold — the
        # money sitting on the shelf. Products never sold in the window count as 0.
        sold_units = {pid: int(u or 0) for pid, _, u in per_product}
        sold_rev = {pid: _f(r) for pid, r, _ in per_product}
        shelf: list[dict[str, Any]] = [
                {
                    "product_id": str(pid),
                    "sku": p.sku,
                    "name": p.name,
                    "revenue": round(sold_rev.get(pid, 0.0), 2),
                    "units": sold_units.get(pid, 0),
                    "on_hand": stock.get(pid, 0),
                }
                for pid, p in products.items()
                if stock.get(pid, 0) > 0
        ]
        bottom_products = sorted(shelf, key=lambda r: (r["units"], -r["on_hand"]))[:6]

        month_start = today.replace(day=1)
        purchases_total, purchases_count = self._s.execute(
            select(func.coalesce(func.sum(PurchaseModel.total_amount), 0), func.count()).where(
                PurchaseModel.company_id == company_id, PurchaseModel.purchase_date >= month_start
            )
        ).one()

        lost_day = lima_date(LostSaleModel.occurred_at)
        lost_attempts, lost_units = self._s.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(greatest(LostSaleModel.requested_quantity - LostSaleModel.available_quantity, 0)), 0
                ),
            ).where(LostSaleModel.company_id == company_id, lost_day >= d30)
        ).one()

        latest_run = self._s.execute(
            select(ForecastRunModel)
            .where(ForecastRunModel.company_id == company_id)
            .order_by(ForecastRunModel.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        tickets_30 = int(tickets_30 or 0)
        return {
            "today": today.isoformat(),
            "revenue_today": round(rev_today, 2),
            "units_today": units_today,
            "revenue_7d": round(rev_7, 2),
            "revenue_30d": round(rev_30, 2),
            "units_30d": units_30,
            "revenue_prev_30d": round(rev_prev_30, 2),
            "revenue_change_pct": round((rev_30 - rev_prev_30) / rev_prev_30 * 100, 1) if rev_prev_30 > 0 else None,
            "tickets_today": tickets_today,
            "tickets_30d": tickets_30,
            "avg_ticket_30d": round(_f(tickets_total_30) / tickets_30, 2) if tickets_30 else None,
            "active_products": len(products),
            "low_stock_count": len(low_stock),
            "out_of_stock_count": out_of_stock,
            "low_stock": low_stock[:8],
            "inventory_value": round(float(inventory_value), 2),
            "purchases_month_total": round(_f(purchases_total), 2),
            "purchases_month_count": int(purchases_count or 0),
            "lost_sales_30d_attempts": int(lost_attempts or 0),
            "lost_sales_30d_units": int(lost_units or 0),
            "top_products": top_products,
            "bottom_products": bottom_products,
            "gross_margin_30d": round(gross_margin_30, 2),
            "margin_pct_30d": round(gross_margin_30 / rev_30 * 100, 1) if rev_30 > 0 else None,
            "sales_by_day": sales_by_day,
            "has_forecast": latest_run is not None,
        }
