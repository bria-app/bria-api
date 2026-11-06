"""Sales module — read model (ticket detail, listing, period summary, lost sales).

Queries go straight to the tables and return application DTOs; nothing here writes.
"""
from __future__ import annotations

import builtins
import math
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import String, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.modules.invoicing.infrastructure.persistence.models import InvoiceModel
from app.modules.products.infrastructure.persistence.models import ProductModel
from app.modules.sales.application.dtos import (
    DailySalesDTO,
    DocumentTypeBreakdownDTO,
    LostSaleDTO,
    PaymentMethodBreakdownDTO,
    SalesOrderDTO,
    SalesOrderLineDTO,
    SalesOrderPageDTO,
    SalesOrderRowDTO,
    SalesSummaryDTO,
    SellerBreakdownDTO,
    TopProductDTO,
)
from app.modules.sales.domain.services import document_number, lima_day_bounds
from app.modules.sales.infrastructure.persistence.mappers import lost_sale_to_entity
from app.modules.sales.infrastructure.persistence.models import (
    LostSaleModel,
    SaleModel,
    SalesOrderModel,
)
from app.shared.infrastructure.database.portable import lima_date, zero_pad

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def _dec(value: object) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(CENT, rounding=ROUND_HALF_UP)


class SqlSalesOrderReadModel:
    def __init__(self, session: Session) -> None:
        self._session = session

    # --- detail ------------------------------------------------------------------
    def get_detail(
        self, company_id: UUID, order_id: UUID, seller_id: UUID | None = None
    ) -> SalesOrderDTO | None:
        o = self._session.get(SalesOrderModel, order_id)
        if o is None or o.company_id != company_id:
            return None
        if seller_id is not None and o.seller_id != seller_id:
            return None
        inv = self._session.get(InvoiceModel, o.invoice_id) if o.invoice_id else None
        rows = self._session.execute(
            select(SaleModel, ProductModel.name, ProductModel.sku)
            .outerjoin(ProductModel, ProductModel.id == SaleModel.product_id)
            .where(SaleModel.order_id == o.id)
            .order_by(ProductModel.name)
        ).all()
        lines: list[SalesOrderLineDTO] = []
        cost_total = ZERO
        units = 0
        for s, name, sku in rows:
            gross = s.unit_price * s.quantity
            lines.append(
                SalesOrderLineDTO(
                    id=s.id,
                    product_id=s.product_id,
                    product_name=name or "Producto eliminado",
                    sku=sku or "",
                    quantity=s.quantity,
                    unit_price=_dec(s.unit_price),
                    discount=_dec(gross - s.total_amount),
                    line_total=_dec(s.total_amount),
                    unit_cost=s.unit_cost,
                )
            )
            cost_total += (s.unit_cost or ZERO) * s.quantity
            units += s.quantity
        change = None
        if o.payment_method == "efectivo" and o.amount_received is not None:
            change = _dec(o.amount_received - o.total)
        return SalesOrderDTO(
            id=o.id,
            company_id=o.company_id,
            order_number=o.order_number,
            document_type=o.document_type,
            document_number=document_number(
                o.document_type, o.order_number, inv.series if inv else None, inv.correlativo if inv else None
            ),
            invoice_id=o.invoice_id,
            invoice_status=inv.status if inv else None,
            client_doc_type=o.client_doc_type,
            client_doc_number=o.client_doc_number,
            client_name=o.client_name,
            client_address=o.client_address,
            seller_id=o.seller_id,
            seller_name=o.seller_name,
            payment_method=o.payment_method,
            amount_received=o.amount_received,
            change=change,
            discount_total=_dec(o.discount_total),
            subtotal=_dec(o.subtotal),
            igv=_dec(o.igv),
            total=_dec(o.total),
            currency=o.currency,
            items_count=len(lines),
            units=units,
            cost_total=_dec(cost_total),
            gross_margin=_dec(o.subtotal - cost_total),
            status=o.status,
            notes=o.notes,
            sold_at=o.sold_at,
            lines=lines,
        )

    # --- listing -----------------------------------------------------------------
    def list(
        self,
        company_id: UUID,
        *,
        date_from: date | None,
        date_to: date | None,
        seller_id: UUID | None,
        document_type: str | None,
        status: str | None,
        q: str | None,
        page: int,
        size: int,
    ) -> SalesOrderPageDTO:
        lines_sq = (
            select(
                SaleModel.order_id.label("order_id"),
                func.count(SaleModel.id).label("n_items"),
                func.coalesce(func.sum(SaleModel.quantity), 0).label("units"),
                func.coalesce(
                    func.sum(SaleModel.quantity * func.coalesce(SaleModel.unit_cost, 0)), 0
                ).label("cost"),
            )
            .where(SaleModel.company_id == company_id, SaleModel.order_id.is_not(None))
            .group_by(SaleModel.order_id)
            .subquery()
        )
        stmt = (
            select(
                SalesOrderModel,
                InvoiceModel.series,
                InvoiceModel.correlativo,
                InvoiceModel.status,
                # Label is n_items: `.c.items` would resolve to ColumnCollection.items().
                lines_sq.c.n_items,
                lines_sq.c.units,
                lines_sq.c.cost,
            )
            .outerjoin(InvoiceModel, InvoiceModel.id == SalesOrderModel.invoice_id)
            .outerjoin(lines_sq, lines_sq.c.order_id == SalesOrderModel.id)
            .where(SalesOrderModel.company_id == company_id)
        )
        if date_from or date_to:
            start, end = lima_day_bounds(date_from or date(2000, 1, 1), date_to or date(2100, 1, 1))
            stmt = stmt.where(SalesOrderModel.sold_at >= start, SalesOrderModel.sold_at < end)
        if seller_id:
            stmt = stmt.where(SalesOrderModel.seller_id == seller_id)
        if document_type:
            stmt = stmt.where(SalesOrderModel.document_type == document_type)
        if status:
            stmt = stmt.where(SalesOrderModel.status == status)
        if q and q.strip():
            term = f"%{q.strip()}%"
            # `||` and zero_pad instead of CONCAT()/LPAD(), which SQLite lacks. CONCAT skipped
            # NULLs; `||` propagates them, hence the coalesce on the invoice parts.
            invoice_number = (
                func.coalesce(InvoiceModel.series, "")
                .concat("-")
                .concat(func.coalesce(zero_pad(InvoiceModel.correlativo, 8), ""))
            )
            nv_number = literal("NV-").concat(zero_pad(SalesOrderModel.order_number, 6))
            stmt = stmt.where(
                or_(
                    SalesOrderModel.client_name.ilike(term),
                    SalesOrderModel.client_doc_number.ilike(term),
                    SalesOrderModel.seller_name.ilike(term),
                    cast(SalesOrderModel.order_number, String) == q.strip().lstrip("#"),
                    invoice_number.ilike(term),
                    nv_number.ilike(term),
                )
            )

        total = int(
            self._session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        )
        rows = self._session.execute(
            stmt.order_by(SalesOrderModel.sold_at.desc()).offset((page - 1) * size).limit(size)
        ).all()
        items = []
        for o, series, correlativo, inv_status, n_items, units, cost in rows:
            cost_dec = _dec(cost)
            items.append(
                SalesOrderRowDTO(
                    id=o.id,
                    order_number=o.order_number,
                    sold_at=o.sold_at,
                    document_type=o.document_type,
                    document_number=document_number(o.document_type, o.order_number, series, correlativo),
                    invoice_status=inv_status,
                    client_doc_type=o.client_doc_type,
                    client_doc_number=o.client_doc_number,
                    client_name=o.client_name,
                    seller_id=o.seller_id,
                    seller_name=o.seller_name,
                    payment_method=o.payment_method,
                    items_count=int(n_items or 0),
                    units=int(units or 0),
                    subtotal=_dec(o.subtotal),
                    igv=_dec(o.igv),
                    total=_dec(o.total),
                    cost_total=cost_dec,
                    margin=_dec(o.subtotal - cost_dec),
                    status=o.status,
                )
            )
        return SalesOrderPageDTO(
            items=items, total=total, page=page, size=size, pages=max(1, math.ceil(total / size))
        )

    # --- summary -----------------------------------------------------------------
    def summary(
        self, company_id: UUID, *, date_from: date, date_to: date, seller_id: UUID | None
    ) -> SalesSummaryDTO:
        start, end = lima_day_bounds(date_from, date_to)
        base = [
            SalesOrderModel.company_id == company_id,
            SalesOrderModel.sold_at >= start,
            SalesOrderModel.sold_at < end,
        ]
        if seller_id:
            base.append(SalesOrderModel.seller_id == seller_id)
        completed = [*base, SalesOrderModel.status == "completed"]

        orders, revenue, revenue_net, igv = self._session.execute(
            select(
                func.count(SalesOrderModel.id),
                func.coalesce(func.sum(SalesOrderModel.total), 0),
                func.coalesce(func.sum(SalesOrderModel.subtotal), 0),
                func.coalesce(func.sum(SalesOrderModel.igv), 0),
            ).where(*completed)
        ).one()
        voided = self._session.execute(
            select(func.count(SalesOrderModel.id)).where(*base, SalesOrderModel.status == "voided")
        ).scalar_one()

        units, cost = self._session.execute(
            select(
                func.coalesce(func.sum(SaleModel.quantity), 0),
                func.coalesce(func.sum(SaleModel.quantity * func.coalesce(SaleModel.unit_cost, 0)), 0),
            )
            .join(SalesOrderModel, SalesOrderModel.id == SaleModel.order_id)
            .where(*completed)
        ).one()

        by_payment = [
            PaymentMethodBreakdownDTO(payment_method=m, orders=int(n), total=_dec(t))
            for m, n, t in self._session.execute(
                select(
                    SalesOrderModel.payment_method,
                    func.count(SalesOrderModel.id),
                    func.sum(SalesOrderModel.total),
                )
                .where(*completed)
                .group_by(SalesOrderModel.payment_method)
                .order_by(func.sum(SalesOrderModel.total).desc())
            ).all()
        ]

        seller_units: dict[UUID | None, int] = {
            seller_id: int(units or 0)
            for seller_id, units in self._session.execute(
                select(SalesOrderModel.seller_id, func.sum(SaleModel.quantity))
                .join(SalesOrderModel, SalesOrderModel.id == SaleModel.order_id)
                .where(*completed)
                .group_by(SalesOrderModel.seller_id)
            ).all()
        }
        by_seller = [
            SellerBreakdownDTO(
                seller_id=sid, seller_name=name or "Sin vendedor", orders=int(n),
                units=int(seller_units.get(sid) or 0), total=_dec(t),
            )
            for sid, name, n, t in self._session.execute(
                select(
                    SalesOrderModel.seller_id,
                    func.max(SalesOrderModel.seller_name),
                    func.count(SalesOrderModel.id),
                    func.sum(SalesOrderModel.total),
                )
                .where(*completed)
                .group_by(SalesOrderModel.seller_id)
                .order_by(func.sum(SalesOrderModel.total).desc())
            ).all()
        ]

        by_doc = [
            DocumentTypeBreakdownDTO(document_type=d, orders=int(n), total=_dec(t))
            for d, n, t in self._session.execute(
                select(
                    SalesOrderModel.document_type,
                    func.count(SalesOrderModel.id),
                    func.sum(SalesOrderModel.total),
                )
                .where(*completed)
                .group_by(SalesOrderModel.document_type)
            ).all()
        ]

        local_day = lima_date(SalesOrderModel.sold_at)
        per_day = {
            d: (int(n), _dec(t))
            for d, n, t in self._session.execute(
                select(local_day, func.count(SalesOrderModel.id), func.sum(SalesOrderModel.total))
                .where(*completed)
                .group_by(local_day)
            ).all()
        }
        by_day: list[DailySalesDTO] = []
        span = min((date_to - date_from).days, 366)
        for i in range(span + 1):
            d = date_from + timedelta(days=i)
            n, t = per_day.get(d, (0, ZERO))
            by_day.append(DailySalesDTO(date=d, orders=n, total=t))

        top = [
            TopProductDTO(product_id=pid, name=name or "Producto eliminado", sku=sku or "", units=int(u), total=_dec(t))
            for pid, name, sku, u, t in self._session.execute(
                select(
                    SaleModel.product_id,
                    func.max(ProductModel.name),
                    func.max(ProductModel.sku),
                    func.sum(SaleModel.quantity),
                    func.sum(SaleModel.total_amount),
                )
                .join(SalesOrderModel, SalesOrderModel.id == SaleModel.order_id)
                .outerjoin(ProductModel, ProductModel.id == SaleModel.product_id)
                .where(*completed)
                .group_by(SaleModel.product_id)
                .order_by(func.sum(SaleModel.total_amount).desc())
                .limit(10)
            ).all()
        ]

        revenue_d = _dec(revenue)
        revenue_net_d = _dec(revenue_net)
        cost_d = _dec(cost)
        margin = revenue_net_d - cost_d
        n_orders = int(orders)
        return SalesSummaryDTO(
            date_from=date_from,
            date_to=date_to,
            revenue=revenue_d,
            revenue_net=revenue_net_d,
            igv=_dec(igv),
            orders=n_orders,
            avg_ticket=_dec(revenue_d / n_orders) if n_orders else ZERO,
            units=int(units),
            cost_total=cost_d,
            gross_margin=margin,
            margin_pct=_dec(margin * 100 / revenue_net_d) if revenue_net_d else ZERO,
            voided_orders=int(voided),
            by_payment_method=by_payment,
            by_seller=by_seller,
            by_document_type=by_doc,
            by_day=by_day,
            top_products=top,
        )

    # --- lost sales ----------------------------------------------------------------
    def list_lost_sales(
        self,
        company_id: UUID,
        *,
        product_id: UUID | None,
        date_from: date | None,
        date_to: date | None,
        limit: int = 500,
    ) -> builtins.list[LostSaleDTO]:
        stmt = (
            select(LostSaleModel, ProductModel.name, ProductModel.sku)
            .outerjoin(ProductModel, ProductModel.id == LostSaleModel.product_id)
            .where(LostSaleModel.company_id == company_id)
        )
        if product_id:
            stmt = stmt.where(LostSaleModel.product_id == product_id)
        if date_from or date_to:
            start, end = lima_day_bounds(date_from or date(2000, 1, 1), date_to or date(2100, 1, 1))
            stmt = stmt.where(LostSaleModel.occurred_at >= start, LostSaleModel.occurred_at < end)
        rows = self._session.execute(
            stmt.order_by(LostSaleModel.occurred_at.desc()).limit(limit)
        ).all()
        return [
            LostSaleDTO.from_entity(lost_sale_to_entity(m), name or "", sku or "")
            for m, name, sku in rows
        ]
