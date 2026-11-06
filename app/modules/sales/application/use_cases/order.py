"""Sales module — POS use cases: close a ticket, look it up, void it, summarize."""
from __future__ import annotations

import builtins
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.modules.sales.application.dtos import (
    CatalogProductDTO,
    LostSaleDTO,
    SalesOrderDTO,
    SalesOrderPageDTO,
    SalesSummaryDTO,
)
from app.modules.sales.domain.entities import LostSale, SalesOrder, SalesOrderLine
from app.modules.sales.domain.enums import ClientDocType, PaymentMethod, SalesDocumentType
from app.modules.sales.domain.exceptions import (
    InsufficientStockError,
    InvalidSalesOrderError,
    ProductNotFoundForSaleError,
    SalesOrderNotFoundError,
)
from app.modules.sales.domain.repositories import (
    InvoiceIssuer,
    LostSaleRepository,
    ProductCatalog,
    SalesOrderRepository,
    StockLedger,
)
from app.modules.sales.domain.services import lima_today


class SalesOrderReadModel(Protocol):
    def get_detail(
        self, company_id: UUID, order_id: UUID, seller_id: UUID | None = None
    ) -> SalesOrderDTO | None: ...
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
    ) -> SalesOrderPageDTO: ...
    def summary(
        self, company_id: UUID, *, date_from: date, date_to: date, seller_id: UUID | None
    ) -> SalesSummaryDTO: ...
    def list_lost_sales(
        self,
        company_id: UUID,
        *,
        product_id: UUID | None,
        date_from: date | None,
        date_to: date | None,
        limit: int = 500,
    ) -> builtins.list[LostSaleDTO]: ...


def _order_not_found(order_id: UUID) -> SalesOrderNotFoundError:
    return SalesOrderNotFoundError(
        message="No encontramos esa venta. Actualiza la página e inténtalo de nuevo.", details={"order_id": str(order_id)}
    )


class CreateSalesOrder:
    """Closes a POS ticket atomically: stock check → ticket + lines → outbound
    movements → comprobante (boleta/factura). Any failure rolls the whole request back."""

    def __init__(
        self,
        orders: SalesOrderRepository,
        catalog: ProductCatalog,
        stock: StockLedger,
        issuer: InvoiceIssuer,
        read: SalesOrderReadModel,
    ) -> None:
        self._orders = orders
        self._catalog = catalog
        self._stock = stock
        self._issuer = issuer
        self._read = read

    def execute(
        self,
        company_id: UUID,
        *,
        seller_id: UUID | None,
        seller_name: str,
        items: list[dict[str, object]],
        document_type: SalesDocumentType,
        client_doc_type: ClientDocType,
        client_doc_number: str = "",
        client_name: str = "",
        client_address: str = "",
        payment_method: PaymentMethod = PaymentMethod.EFECTIVO,
        amount_received: Decimal | None = None,
        notes: str = "",
    ) -> SalesOrderDTO:
        if not items:
            raise InvalidSalesOrderError(message="Agrega al menos un producto a la venta")

        product_ids = [UUID(str(it["product_id"])) for it in items]
        products = self._catalog.get_many(company_id, list(set(product_ids)))
        missing = [str(pid) for pid in product_ids if pid not in products]
        if missing:
            raise ProductNotFoundForSaleError(
                message="Uno o más productos ya no están en el catálogo. Quítalos de la venta.", details={"product_ids": missing}
            )

        lines: list[SalesOrderLine] = []
        for it, pid in zip(items, product_ids):
            product = products[pid]
            if not product.is_active:
                raise InvalidSalesOrderError(message=f"«{product.name}» está inactivo y no se puede vender")
            lines.append(
                SalesOrderLine(
                    product_id=pid,
                    quantity=int(str(it["quantity"])),
                    unit_price=Decimal(str(it["unit_price"])),
                    discount=Decimal(str(it.get("discount") or "0")),
                    unit_cost=product.unit_cost,
                    product_name=product.name,
                    sku=product.sku,
                )
            )

        now = datetime.now(timezone.utc)
        order = SalesOrder(
            company_id=company_id,
            order_number=0,
            document_type=document_type,
            client_doc_type=client_doc_type,
            client_doc_number=client_doc_number,
            client_name=client_name,
            client_address=client_address,
            payment_method=payment_method,
            amount_received=amount_received,
            lines=lines,
            sold_at=now,
            seller_id=seller_id,
            seller_name=seller_name,
            notes=notes.strip()[:500],
        )
        order.validate()

        requested: dict[UUID, int] = defaultdict(int)
        for line in lines:
            requested[line.product_id] += line.quantity
        shortages = []
        for pid, qty in requested.items():
            available = self._stock.on_hand(company_id, pid)
            if qty > available:
                shortages.append(
                    {
                        "product_id": str(pid),
                        "name": products[pid].name,
                        "sku": products[pid].sku,
                        "requested": qty,
                        "available": max(available, 0),
                    }
                )
        if shortages:
            raise InsufficientStockError(shortages)

        order.order_number = self._orders.next_order_number(company_id)
        saved = self._orders.add(order)
        assert saved.id is not None
        for line in saved.lines:
            self._stock.record(
                company_id,
                line.product_id,
                movement_type="outbound",
                quantity=line.quantity,
                unit_cost=line.unit_cost,
                reason=f"Venta ticket #{saved.order_number}",
                reference_type="sale",
                reference_id=saved.id,
                occurred_at=now,
            )

        if saved.issues_invoice:
            issued = self._issuer.issue(saved)
            saved.invoice_id = issued.id
            self._orders.update(saved)

        detail = self._read.get_detail(company_id, saved.id)
        assert detail is not None
        return detail


class VoidSalesOrder:
    """Anula un ticket: returns the units to stock and voids its comprobante."""

    def __init__(
        self,
        orders: SalesOrderRepository,
        stock: StockLedger,
        issuer: InvoiceIssuer,
        read: SalesOrderReadModel,
    ) -> None:
        self._orders = orders
        self._stock = stock
        self._issuer = issuer
        self._read = read

    def execute(
        self, company_id: UUID, order_id: UUID, *, voided_by: str, reason: str = ""
    ) -> SalesOrderDTO:
        order = self._orders.get(company_id, order_id)
        if order is None:
            raise _order_not_found(order_id)
        order.void()
        now = datetime.now(timezone.utc)
        note = f"Anulada por {voided_by or 'administrador'}" + (f": {reason.strip()}" if reason.strip() else "")
        order.notes = f"{order.notes} · {note}" if order.notes else note
        self._orders.update(order)
        # Only give back what the sale really took out: imported history (affect_stock=False)
        # never moved stock, so voiding it must not add units to the inventory.
        to_return = self._stock.units_taken_out(company_id, order_id)
        for line in order.lines:
            quantity = min(line.quantity, to_return.get(line.product_id, 0))
            if quantity <= 0:
                continue
            to_return[line.product_id] -= quantity
            self._stock.record(
                company_id,
                line.product_id,
                movement_type="inbound",
                quantity=quantity,
                unit_cost=line.unit_cost,
                reason=f"Anulación ticket #{order.order_number}",
                reference_type="sale_void",
                reference_id=order_id,
                occurred_at=now,
            )
        if order.invoice_id:
            self._issuer.void(company_id, order.invoice_id)
        detail = self._read.get_detail(company_id, order_id)
        assert detail is not None
        return detail


class GetSalesOrder:
    def __init__(self, read: SalesOrderReadModel) -> None:
        self._read = read

    def execute(self, company_id: UUID, order_id: UUID, seller_id: UUID | None = None) -> SalesOrderDTO:
        detail = self._read.get_detail(company_id, order_id, seller_id)
        if detail is None:
            raise _order_not_found(order_id)
        return detail


class ListSalesOrders:
    def __init__(self, read: SalesOrderReadModel) -> None:
        self._read = read

    def execute(
        self,
        company_id: UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        seller_id: UUID | None = None,
        document_type: str | None = None,
        status: str | None = None,
        q: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> SalesOrderPageDTO:
        return self._read.list(
            company_id,
            date_from=date_from,
            date_to=date_to,
            seller_id=seller_id,
            document_type=document_type,
            status=status,
            q=q,
            page=page,
            size=size,
        )


class GetSalesSummary:
    def __init__(self, read: SalesOrderReadModel) -> None:
        self._read = read

    def execute(
        self,
        company_id: UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        seller_id: UUID | None = None,
    ) -> SalesSummaryDTO:
        end = date_to or lima_today()
        start = date_from or (end - timedelta(days=29))
        if start > end:
            raise InvalidSalesOrderError(message="La fecha inicial no puede ser posterior a la final")
        return self._read.summary(company_id, date_from=start, date_to=end, seller_id=seller_id)


# --- Catalog for the till --------------------------------------------------------
class LookupProductByCode:
    def __init__(self, catalog: ProductCatalog) -> None:
        self._catalog = catalog

    def execute(self, company_id: UUID, code: str) -> CatalogProductDTO:
        product = self._catalog.lookup(company_id, code)
        if product is None:
            raise ProductNotFoundForSaleError(
                message=f"No hay un producto con el código «{code.strip()}»", details={"code": code}
            )
        return CatalogProductDTO.from_entity(product)


class SearchCatalog:
    def __init__(self, catalog: ProductCatalog) -> None:
        self._catalog = catalog

    def execute(self, company_id: UUID, q: str = "", limit: int = 20) -> list[CatalogProductDTO]:
        limit = max(1, min(limit, 200))
        return [CatalogProductDTO.from_entity(p) for p in self._catalog.search(company_id, q, limit)]


# --- Lost sales (quiebres) --------------------------------------------------------
class RecordLostSale:
    def __init__(self, lost_sales: LostSaleRepository, catalog: ProductCatalog) -> None:
        self._lost_sales = lost_sales
        self._catalog = catalog

    def execute(
        self,
        company_id: UUID,
        *,
        product_id: UUID,
        requested_quantity: int,
        available_quantity: int,
        seller_id: UUID | None,
        seller_name: str,
        source: str = "pos",
    ) -> LostSaleDTO:
        product = self._catalog.get_many(company_id, [product_id]).get(product_id)
        if product is None:
            raise ProductNotFoundForSaleError(message="No encontramos ese producto. Actualiza la página e inténtalo de nuevo.", details={"product_id": str(product_id)})
        saved = self._lost_sales.add(
            LostSale(
                company_id=company_id,
                product_id=product_id,
                requested_quantity=requested_quantity,
                available_quantity=available_quantity,
                occurred_at=datetime.now(timezone.utc),
                seller_id=seller_id,
                seller_name=seller_name,
                source=(source or "pos")[:20],
            )
        )
        return LostSaleDTO.from_entity(saved, product.name, product.sku)


class ListLostSales:
    def __init__(self, read: SalesOrderReadModel) -> None:
        self._read = read

    def execute(
        self,
        company_id: UUID,
        *,
        product_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[LostSaleDTO]:
        return self._read.list_lost_sales(
            company_id, product_id=product_id, date_from=date_from, date_to=date_to
        )
