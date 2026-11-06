"""Sales module — use cases for the Sale aggregate."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from app.modules.sales.application.dtos import SaleDTO
from app.modules.sales.domain.entities import Sale
from app.modules.sales.domain.exceptions import SaleNotFoundError
from app.modules.sales.domain.repositories import SaleRepository
from app.shared.domain.value_objects import Money, Quantity


def _build_sale(
    company_id: UUID,
    *,
    product_id: UUID,
    sale_date: date,
    quantity: int,
    unit_price: Decimal,
    currency: str,
    batch_id: UUID | None,
) -> Sale:
    """Build a Sale, computing total_amount = unit_price * quantity (the invariant)."""
    qty = Quantity(quantity)
    price = Money(unit_price, currency)
    total = price * qty.value
    return Sale(
        company_id=company_id,
        product_id=product_id,
        sale_date=sale_date,
        quantity=qty,
        unit_price=price,
        total_amount=total,
        batch_id=batch_id,
    )


class CreateSale:
    def __init__(self, sales: SaleRepository) -> None:
        self._sales = sales

    def execute(
        self,
        company_id: UUID,
        *,
        product_id: UUID,
        sale_date: date,
        quantity: int,
        unit_price: Decimal,
        currency: str = "PEN",
        batch_id: UUID | None = None,
    ) -> SaleDTO:
        sale = _build_sale(
            company_id,
            product_id=product_id,
            sale_date=sale_date,
            quantity=quantity,
            unit_price=unit_price,
            currency=currency,
            batch_id=batch_id,
        )
        return SaleDTO.from_entity(self._sales.add(sale))


class CreateSalesBulk:
    def __init__(self, sales: SaleRepository) -> None:
        self._sales = sales

    def execute(
        self, company_id: UUID, *, items: list[dict[str, object]]
    ) -> list[SaleDTO]:
        built = [
            _build_sale(
                company_id,
                product_id=UUID(str(item["product_id"])),
                sale_date=date.fromisoformat(str(item["sale_date"])),
                quantity=int(str(item["quantity"])),
                unit_price=Decimal(str(item["unit_price"])),
                currency=str(item.get("currency", "PEN")),
                batch_id=(
                    UUID(str(item["batch_id"])) if item.get("batch_id") else None
                ),
            )
            for item in items
        ]
        return [SaleDTO.from_entity(s) for s in self._sales.add_bulk(built)]


def _owned(sales: SaleRepository, company_id: UUID, sale_id: UUID) -> Sale:
    """A sale of another company is reported as missing (never leak its existence)."""
    sale = sales.get_by_id(sale_id)
    if sale is None or sale.company_id != company_id:
        raise SaleNotFoundError(message="No encontramos esa venta. Actualiza la página e inténtalo de nuevo.")
    return sale


class GetSale:
    def __init__(self, sales: SaleRepository) -> None:
        self._sales = sales

    def execute(self, company_id: UUID, sale_id: UUID) -> SaleDTO:
        return SaleDTO.from_entity(_owned(self._sales, company_id, sale_id))


class ListSales:
    def __init__(self, sales: SaleRepository) -> None:
        self._sales = sales

    def execute(
        self, company_id: UUID, offset: int = 0, limit: int = 50, origin: str | None = None
    ) -> list[SaleDTO]:
        return [
            SaleDTO.from_entity(s)
            for s in self._sales.list_by_company(company_id, offset, limit, origin)
        ]


class ListSalesByProduct:
    def __init__(self, sales: SaleRepository) -> None:
        self._sales = sales

    def execute(
        self, company_id: UUID, product_id: UUID, *, start: date, end: date
    ) -> list[SaleDTO]:
        return [
            SaleDTO.from_entity(s)
            for s in self._sales.list_by_product_and_range(company_id, product_id, start, end)
        ]


class DeleteSale:
    def __init__(self, sales: SaleRepository) -> None:
        self._sales = sales

    def execute(self, company_id: UUID, sale_id: UUID) -> bool:
        _owned(self._sales, company_id, sale_id)
        if not self._sales.delete(sale_id):
            raise SaleNotFoundError(message="No encontramos esa venta. Actualiza la página e inténtalo de nuevo.")
        return True
