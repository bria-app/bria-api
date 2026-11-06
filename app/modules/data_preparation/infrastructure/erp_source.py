"""Data preparation — read-side ERP source for FTGM scopes (SQLAlchemy queries).

Resolves a forecast *scope* to products and loads each product's demand history from the
ERP tables (sales incl. POS lines and legacy rows, lost sales, inventory movements,
purchases). Dates of timestamped rows are taken in Lima time (UTC-5, no DST).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.modules.companies.infrastructure.persistence.models import UserModel
from app.modules.data_preparation.domain.erp_analysis import ProductHistory
from app.modules.forecasting.infrastructure.persistence.models import (
    ForecastResultModel,
    ForecastRunModel,
)
from app.modules.inventory.infrastructure.persistence.models import InventoryMovementModel
from app.modules.inventory.infrastructure.persistence.queries import stock_on_hand_map
from app.modules.products.infrastructure.persistence.models import CategoryModel, ProductModel
from app.modules.purchases.infrastructure.persistence.models import PurchaseModel
from app.modules.sales.infrastructure.persistence.models import LostSaleModel, SaleModel
from app.modules.suppliers.infrastructure.persistence.models import SupplierModel
from app.shared.domain.errors import ValidationError
from app.shared.infrastructure.database.portable import greatest, lima_date

LIMA = timezone(timedelta(hours=-5))


def lima_today() -> date:
    return datetime.now(LIMA).date()


class ErpDataSource:
    def __init__(self, session: Session) -> None:
        self._s = session

    # ------------------------------------------------------------------ scope
    def resolve_scope(self, company_id: UUID, scope: dict[str, Any], as_of: date) -> list[ProductModel]:
        kind = scope.get("type")
        base = select(ProductModel).where(ProductModel.company_id == company_id, ProductModel.is_active.is_(True))
        if kind == "all":
            stmt = base
        elif kind == "products":
            ids = [UUID(str(i)) for i in scope.get("product_ids") or []]
            if not ids:
                raise ValidationError(message="Elige al menos un producto.")
            stmt = base.where(ProductModel.id.in_(ids))
        elif kind == "recent_sales":
            months = int(scope.get("months") or 0)
            if months < 1 or months > 120:
                raise ValidationError(message="Los meses deben estar entre 1 y 120.")
            since = as_of - timedelta(days=round(months * 30.4375))
            sold = select(SaleModel.product_id).where(
                SaleModel.company_id == company_id, SaleModel.sale_date >= since, SaleModel.sale_date < as_of
            )
            stmt = base.where(ProductModel.id.in_(sold))
        elif kind == "supplier":
            supplier_id = self._uuid(scope.get("supplier_id"), "proveedor")
            bought = select(PurchaseModel.product_id).where(
                PurchaseModel.company_id == company_id, PurchaseModel.supplier_id == supplier_id
            )
            stmt = base.where(ProductModel.id.in_(bought))
        elif kind == "seller":
            seller_id = self._uuid(scope.get("seller_id"), "vendedor")
            sold = select(SaleModel.product_id).where(
                SaleModel.company_id == company_id, SaleModel.seller_id == seller_id
            )
            stmt = base.where(ProductModel.id.in_(sold))
        elif kind == "category":
            category_id = self._uuid(scope.get("category_id"), "categoría")
            stmt = base.where(ProductModel.category_id.in_(self._category_tree(company_id, category_id)))
        else:
            raise ValidationError(message=f"Tipo de alcance no soportado: '{kind}'.")
        return list(self._s.execute(stmt.order_by(ProductModel.name)).scalars().all())

    @staticmethod
    def _uuid(value: Any, label: str) -> UUID:
        try:
            return UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise ValidationError(message=f"Elige un {label} válido.") from exc

    def _category_tree(self, company_id: UUID, root: UUID) -> list[UUID]:
        rows = self._s.execute(
            select(CategoryModel.id, CategoryModel.parent_id).where(CategoryModel.company_id == company_id)
        ).all()
        children: dict[UUID | None, list[UUID]] = {}
        for cid, parent in rows:
            children.setdefault(parent, []).append(cid)
        out, stack = [], [root]
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.append(cur)
            stack.extend(children.get(cur, []))
        return out

    def describe(self, company_id: UUID, scope: dict[str, Any], product_count: int) -> str:
        kind = scope.get("type")
        if kind == "all":
            return "Todo el inventario"
        if kind == "recent_sales":
            return f"Productos vendidos en los últimos {scope.get('months')} meses"
        if kind == "products":
            ids = scope.get("product_ids") or []
            if len(ids) == 1:
                p = self._s.get(ProductModel, UUID(str(ids[0])))
                return f"Producto: {p.name}" if p else "1 producto"
            return f"{len(ids)} productos específicos"
        if kind == "supplier":
            sup = self._s.get(SupplierModel, UUID(str(scope.get("supplier_id"))))
            return f"Proveedor: {sup.business_name}" if sup else "Por proveedor"
        if kind == "seller":
            user = self._s.get(UserModel, UUID(str(scope.get("seller_id"))))
            return f"Vendedor: {user.full_name or user.username or user.email}" if user else "Por vendedor"
        if kind == "category":
            cat = self._s.get(CategoryModel, UUID(str(scope.get("category_id"))))
            return f"Categoría: {cat.name}" if cat else "Por categoría"
        if kind == "dataset":
            return "Dataset preparado (CSV)"
        return f"{product_count} productos"

    # ------------------------------------------------------------------ history
    def load_histories(
        self, company_id: UUID, products: list[ProductModel], as_of: date
    ) -> list[ProductHistory]:
        ids = [p.id for p in products]
        histories = {
            p.id: ProductHistory(
                product_id=p.id, sku=p.sku, name=p.name, unit_cost=p.unit_cost or Decimal("0")
            )
            for p in products
        }
        if not ids:
            return []
        end = as_of + timedelta(days=1)

        for pid, day, units, lines in self._s.execute(
            select(SaleModel.product_id, SaleModel.sale_date, func.sum(SaleModel.quantity), func.count())
            .where(SaleModel.company_id == company_id, SaleModel.product_id.in_(ids), SaleModel.sale_date < end)
            .group_by(SaleModel.product_id, SaleModel.sale_date)
        ).all():
            h = histories[pid]
            h.sales[day] = int(units or 0)
            h.sales_count += int(lines)

        lost_day = lima_date(LostSaleModel.occurred_at)
        for pid, day, attempts, units in self._s.execute(
            select(
                LostSaleModel.product_id,
                lost_day,
                func.count(),
                func.sum(greatest(LostSaleModel.requested_quantity - LostSaleModel.available_quantity, 0)),
            )
            .where(LostSaleModel.company_id == company_id, LostSaleModel.product_id.in_(ids))
            .group_by(LostSaleModel.product_id, lost_day)
        ).all():
            histories[pid].lost[day] = (int(attempts), int(units or 0))

        move_day = lima_date(InventoryMovementModel.occurred_at)
        signed = case(
            (InventoryMovementModel.movement_type == "outbound", -InventoryMovementModel.quantity),
            else_=InventoryMovementModel.quantity,
        )
        for pid, day, net, n in self._s.execute(
            select(InventoryMovementModel.product_id, move_day, func.sum(signed), func.count())
            .where(InventoryMovementModel.company_id == company_id, InventoryMovementModel.product_id.in_(ids))
            .group_by(InventoryMovementModel.product_id, move_day)
        ).all():
            h = histories[pid]
            h.moves[day] = h.moves.get(day, 0) + int(net or 0)
            h.moves_count += int(n)

        for pid, day, qty in self._s.execute(
            select(PurchaseModel.product_id, PurchaseModel.purchase_date, func.sum(PurchaseModel.quantity))
            .where(PurchaseModel.company_id == company_id, PurchaseModel.product_id.in_(ids))
            .group_by(PurchaseModel.product_id, PurchaseModel.purchase_date)
            .order_by(PurchaseModel.purchase_date)
        ).all():
            histories[pid].purchases.append((day, int(qty or 0)))

        on_hand = stock_on_hand_map(self._s, company_id)
        for pid, h in histories.items():
            h.on_hand = on_hand.get(pid, 0)
        return [histories[p.id] for p in products]

    def sales_by_day(
        self, company_id: UUID, product_ids: list[UUID], start: date, end_exclusive: date
    ) -> dict[UUID, dict[date, int]]:
        out: dict[UUID, dict[date, int]] = {pid: {} for pid in product_ids}
        if not product_ids:
            return out
        for pid, day, units in self._s.execute(
            select(SaleModel.product_id, SaleModel.sale_date, func.sum(SaleModel.quantity))
            .where(
                SaleModel.company_id == company_id,
                SaleModel.product_id.in_(product_ids),
                SaleModel.sale_date >= start,
                SaleModel.sale_date < end_exclusive,
            )
            .group_by(SaleModel.product_id, SaleModel.sale_date)
        ).all():
            out.setdefault(pid, {})[day] = int(units or 0)
        return out

    def latest_runs(self, company_id: UUID, product_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
        """Most recent successful run that forecast each product."""
        if not product_ids:
            return {}
        rows = self._s.execute(
            select(ForecastResultModel.product_id, ForecastRunModel.id, ForecastRunModel.created_at)
            .join(ForecastRunModel, ForecastRunModel.id == ForecastResultModel.run_id)
            .where(
                ForecastRunModel.company_id == company_id,
                ForecastRunModel.status == "success",
                ForecastResultModel.product_id.in_(product_ids),
            )
            .order_by(ForecastRunModel.created_at.desc())
        ).all()
        out: dict[UUID, dict[str, Any]] = {}
        for pid, run_id, created in rows:
            if pid not in out:
                out[pid] = {"run_id": str(run_id), "created_at": created.isoformat() if created else None}
        return out

    def run_ids_for_product(self, company_id: UUID, product_id: UUID, limit: int = 20) -> list[UUID]:
        rows = self._s.execute(
            select(ForecastRunModel.id)
            .join(ForecastResultModel, ForecastResultModel.run_id == ForecastRunModel.id)
            .where(ForecastRunModel.company_id == company_id, ForecastResultModel.product_id == product_id)
            .order_by(ForecastRunModel.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return list(rows)

    def products_by_ids(self, company_id: UUID, ids: list[UUID]) -> dict[UUID, ProductModel]:
        if not ids:
            return {}
        rows = self._s.execute(
            select(ProductModel).where(ProductModel.company_id == company_id, ProductModel.id.in_(ids))
        ).scalars().all()
        return {p.id: p for p in rows}

    def stock_map(self, company_id: UUID) -> dict[UUID, int]:
        return stock_on_hand_map(self._s, company_id)
