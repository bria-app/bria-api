"""Sales module — SQLAlchemy repository implementations."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.modules.products.infrastructure.persistence.models import ProductModel
from app.modules.sales.domain.entities import LostSale, Sale, SalesBatch, SalesOrder
from app.modules.sales.domain.exceptions import (
    SalesBatchNotFoundError,
    SalesOrderNotFoundError,
)
from app.modules.sales.infrastructure.persistence.mappers import (
    batch_to_entity,
    batch_to_model,
    line_to_entity,
    lost_sale_to_entity,
    lost_sale_to_model,
    order_line_to_model,
    order_to_entity,
    order_to_model,
    sale_to_entity,
    sale_to_model,
)
from app.modules.sales.infrastructure.persistence.models import (
    SaleModel,
    SalesBatchModel,
    SalesOrderModel,
)


class SqlSaleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _labelled(self, stmt) -> list[Sale]:  # type: ignore[no-untyped-def]
        """Run a SaleModel query joined to its product, so each sale carries name and SKU."""
        rows = self._session.execute(
            stmt.add_columns(ProductModel.name, ProductModel.sku).outerjoin(
                ProductModel, ProductModel.id == SaleModel.product_id
            )
        ).all()
        return [
            sale_to_entity(m, name if name is not None else "Producto eliminado", sku or "")
            for m, name, sku in rows
        ]

    def get_by_id(self, sale_id: UUID) -> Sale | None:
        found = self._labelled(select(SaleModel).where(SaleModel.id == sale_id))
        return found[0] if found else None

    def list_by_product_and_range(
        self, company_id: UUID, product_id: UUID, start: date, end: date
    ) -> list[Sale]:
        return self._labelled(
            select(SaleModel)
            .where(
                SaleModel.company_id == company_id,
                SaleModel.product_id == product_id,
                SaleModel.sale_date >= start,
                SaleModel.sale_date <= end,
            )
            .order_by(SaleModel.sale_date)
        )

    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50, origin: str | None = None
    ) -> list[Sale]:
        """origin: "pos" (rung up in the app), "imported" (loaded from a spreadsheet) or None (all)."""
        stmt = select(SaleModel).where(SaleModel.company_id == company_id)
        if origin == "pos":
            stmt = stmt.where(SaleModel.batch_id.is_(None))
        elif origin == "imported":
            stmt = stmt.where(SaleModel.batch_id.is_not(None))
        return self._labelled(
            stmt.order_by(SaleModel.sale_date.desc(), SaleModel.id).offset(offset).limit(limit)
        )

    def add(self, sale: Sale) -> Sale:
        model = sale_to_model(sale)
        self._session.add(model)
        self._session.flush()
        return sale_to_entity(model)

    def add_bulk(self, sales: list[Sale]) -> list[Sale]:
        models = [sale_to_model(s) for s in sales]
        self._session.add_all(models)
        self._session.flush()
        return [sale_to_entity(m) for m in models]

    def delete(self, sale_id: UUID) -> bool:
        model = self._session.get(SaleModel, sale_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True

    def delete_by_batch(self, company_id: UUID, batch_id: UUID) -> int:
        """Remove all sales linked to an ingestion batch (idempotent re-prepare)."""
        result = self._session.execute(
            delete(SaleModel).where(
                SaleModel.company_id == company_id,
                SaleModel.batch_id == batch_id,
            )
        )
        self._session.flush()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


class SqlSalesBatchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, batch_id: UUID) -> SalesBatch | None:
        model = self._session.get(SalesBatchModel, batch_id)
        return batch_to_entity(model) if model else None

    def list_by_company(self, company_id: UUID) -> list[SalesBatch]:
        rows = self._session.execute(
            select(SalesBatchModel)
            .where(SalesBatchModel.company_id == company_id)
            .order_by(SalesBatchModel.created_at.desc())
        ).scalars().all()
        return [batch_to_entity(m) for m in rows]

    def add(self, batch: SalesBatch) -> SalesBatch:
        model = batch_to_model(batch)
        self._session.add(model)
        self._session.flush()
        return batch_to_entity(model)

    def update(self, batch: SalesBatch) -> SalesBatch:
        model = self._session.get(SalesBatchModel, batch.id)
        if model is None:
            raise SalesBatchNotFoundError(message="No encontramos esa carga de ventas. Actualiza la página e inténtalo de nuevo.")
        model.source_file = batch.source_file
        model.status = batch.status.value
        model.row_count = batch.row_count
        model.period_start = batch.period.start if batch.period else None
        model.period_end = batch.period.end if batch.period else None
        self._session.flush()
        return batch_to_entity(model)


class SqlSalesOrderRepository:
    """POS tickets: the header in sales_orders, each product line as a `sales` row."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def next_order_number(self, company_id: UUID) -> int:
        current = self._session.execute(
            select(func.max(SalesOrderModel.order_number)).where(
                SalesOrderModel.company_id == company_id
            )
        ).scalar_one()
        return int(current or 0) + 1

    def add(self, order: SalesOrder) -> SalesOrder:
        model = order_to_model(order)
        self._session.add(model)
        self._session.flush()
        order.id = model.id
        line_models = [order_line_to_model(order, line) for line in order.lines]
        self._session.add_all(line_models)
        self._session.flush()
        lines = [
            line_to_entity(m, line.product_name, line.sku)
            for m, line in zip(line_models, order.lines)
        ]
        return order_to_entity(model, lines)

    def get(self, company_id: UUID, order_id: UUID) -> SalesOrder | None:
        model = self._session.get(SalesOrderModel, order_id)
        if model is None or model.company_id != company_id:
            return None
        rows = self._session.execute(
            select(SaleModel, ProductModel.name, ProductModel.sku)
            .outerjoin(ProductModel, ProductModel.id == SaleModel.product_id)
            .where(SaleModel.order_id == order_id)
            .order_by(ProductModel.name)
        ).all()
        lines = [line_to_entity(m, name or "", sku or "") for m, name, sku in rows]
        return order_to_entity(model, lines)

    def update(self, order: SalesOrder) -> SalesOrder:
        model = self._session.get(SalesOrderModel, order.id)
        if model is None:
            raise SalesOrderNotFoundError(message="No encontramos esa venta. Actualiza la página e inténtalo de nuevo.")
        model.status = order.status.value
        model.invoice_id = order.invoice_id
        model.notes = order.notes[:500]
        self._session.flush()
        return order


class SqlLostSaleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, lost_sale: LostSale) -> LostSale:
        model = lost_sale_to_model(lost_sale)
        self._session.add(model)
        self._session.flush()
        return lost_sale_to_entity(model)
