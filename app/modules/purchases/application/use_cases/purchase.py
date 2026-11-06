"""Purchases module — use cases.

Registering a purchase is a cross-module write: it records the document lines, updates
each product's weighted-average cost and pushes stock in via an inbound inventory
movement that references the document (reference_type "purchase", reference_id = the
document's batch id) — the mirror image of what a Sale does with an outbound movement.

Costs are stored NET of IGV (see domain.tax).
"""
from __future__ import annotations

import math
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from app.modules.purchases.application.dtos import (
    ImportErrorDTO,
    NewProductDTO,
    PurchaseBatchResultDTO,
    PurchaseCatalogItemDTO,
    PurchaseDocumentDetailDTO,
    PurchaseDocumentDTO,
    PurchaseDocumentPageDTO,
    PurchaseDTO,
    PurchaseImportResultDTO,
    PurchaseLineDTO,
    StockChangeDTO,
)
from app.modules.purchases.domain.dates import is_future, occurred_at
from app.modules.purchases.domain.entities import ProductRef, Purchase
from app.modules.purchases.domain.exceptions import (
    DuplicateProductCodeError,
    FuturePurchaseDateError,
    InvalidPurchaseError,
    PurchaseDocumentNotFoundError,
    PurchaseProductNotFoundError,
    PurchaseSupplierNotFoundError,
)
from app.modules.purchases.domain.repositories import InboundStockGateway, PurchaseRepository
from app.modules.purchases.domain.tax import igv_of, money, net_of_igv
from app.shared.domain.errors import DomainError
from app.shared.domain.value_objects import Money, Quantity


# Column limits: quantities are INTEGER and amounts NUMERIC(14, 2) in the database.
MAX_QUANTITY = 1_000_000
MAX_AMOUNT = Decimal("999999999999.99")
CURRENCY = "PEN"


def _check_date(purchase_date: date) -> date:
    """A purchase cannot be dated after today in Lima: its stock would enter at once."""
    if is_future(purchase_date):
        raise FuturePurchaseDateError(purchase_date)
    return purchase_date


def _reason(document_number: str) -> str:
    return f"Compra {document_number}" if document_number else "Compra a proveedor"


def _decimal(value: Any, label: str) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise InvalidPurchaseError(message=f"{label} no es un número válido")
    if not d.is_finite():
        raise InvalidPurchaseError(message=f"{label} no es un número válido")
    return d


def _quantity(value: Any) -> int:
    d = _decimal(value, "La cantidad")
    if d <= 0 or d != d.to_integral_value():
        raise InvalidPurchaseError(message="La cantidad debe ser un número entero mayor que 0")
    if d > MAX_QUANTITY:
        raise InvalidPurchaseError(message="La cantidad es demasiado grande (máximo 1 000 000 por línea)")
    return int(d)


def _unit_cost(value: Any, include_igv: bool) -> Decimal:
    d = _decimal(value, "El costo unitario")
    if d < 0:
        raise InvalidPurchaseError(message="El costo unitario no puede ser negativo")
    if d > MAX_AMOUNT:
        raise InvalidPurchaseError(message="El costo unitario es demasiado grande. Revísalo")
    return net_of_igv(d) if include_igv else money(d)


def _line_total(value: Any, quantity: int, include_igv: bool) -> Decimal:
    """Net total of a line.

    With IGV-inclusive costs the total comes from the gross amount (cost x quantity / 1.18),
    not from the rounded net unit cost x quantity, so subtotal + IGV matches the invoice.
    """
    d = _decimal(value, "El costo unitario")
    total = net_of_igv(money(d) * quantity) if include_igv else money(money(d) * quantity)
    if total > MAX_AMOUNT:
        raise InvalidPurchaseError(message="El total de la línea es demasiado grande. Revisa la cantidad y el costo")
    return total


def _sale_price(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    d = _decimal(value, "El precio de venta")
    if d < 0:
        raise InvalidPurchaseError(message="El precio de venta no puede ser negativo")
    if d > MAX_AMOUNT:
        raise InvalidPurchaseError(message="El precio de venta es demasiado grande. Revísalo")
    return d


def _check_length(value: str, limit: int, label: str) -> str:
    if len(value) > limit:
        raise InvalidPurchaseError(message=f"{label} es muy largo (máximo {limit} caracteres)")
    return value


def _currency(value: str | None) -> str:
    code = (value or CURRENCY).strip().upper() or CURRENCY
    if code != CURRENCY:
        raise InvalidPurchaseError(message="Por ahora las compras se registran solo en soles (PEN)")
    return code


class _Receiver:
    """Shared by single, batch and import: store one line + receive its stock."""

    def __init__(self, purchases: PurchaseRepository, stock: InboundStockGateway) -> None:
        self.purchases = purchases
        self.stock = stock

    def ensure_supplier(self, company_id: UUID, supplier_id: UUID) -> None:
        if not self.stock.supplier_exists(company_id, supplier_id):
            raise PurchaseSupplierNotFoundError(supplier_id)

    def line(
        self,
        company_id: UUID,
        *,
        supplier_id: UUID,
        product: ProductRef,
        purchase_date: date,
        quantity: int,
        net_unit_cost: Decimal,
        line_total: Decimal | None = None,
        document_number: str,
        notes: str,
        batch_id: UUID,
        currency: str = CURRENCY,
    ) -> tuple[PurchaseDTO, StockChangeDTO]:
        cost = Money(net_unit_cost, currency)
        total = line_total if line_total is not None else money(net_unit_cost * quantity)
        receipt = self.stock.receive(
            company_id,
            product.id,
            quantity=quantity,
            unit_cost=net_unit_cost,
            reason=_reason(document_number),
            reference_id=batch_id,
            occurred_at=occurred_at(purchase_date),
        )
        saved = self.purchases.add(
            Purchase(
                company_id=company_id,
                supplier_id=supplier_id,
                product_id=product.id,
                purchase_date=purchase_date,
                quantity=Quantity(quantity),
                unit_cost=cost,
                total_amount=Money(total, currency),
                document_number=document_number,
                notes=notes,
                import_batch_id=batch_id,
            )
        )
        return PurchaseDTO.from_entity(saved), StockChangeDTO.build(receipt, product.sku, product.name)


class CreatePurchase:
    """Single-line purchase (kept for API compatibility); it is its own document."""

    def __init__(self, purchases: PurchaseRepository, stock: InboundStockGateway) -> None:
        self._r = _Receiver(purchases, stock)

    def execute(
        self,
        company_id: UUID,
        *,
        supplier_id: UUID,
        product_id: UUID,
        purchase_date: date,
        quantity: int,
        unit_cost: Decimal,
        currency: str = "PEN",
        document_number: str = "",
        notes: str = "",
        costs_include_igv: bool = False,
    ) -> PurchaseDTO:
        _check_date(purchase_date)
        code = _currency(currency)
        self._r.ensure_supplier(company_id, supplier_id)
        product = self._r.stock.get_product(company_id, product_id)
        if product is None:
            raise PurchaseProductNotFoundError(product_id)
        qty = _quantity(quantity)
        dto, _ = self._r.line(
            company_id,
            supplier_id=supplier_id,
            product=product,
            purchase_date=purchase_date,
            quantity=qty,
            net_unit_cost=_unit_cost(unit_cost, costs_include_igv),
            line_total=_line_total(unit_cost, qty, costs_include_igv),
            document_number=document_number.strip(),
            notes=notes.strip(),
            batch_id=uuid4(),
            currency=code,
        )
        return dto


class RegisterPurchaseDocument:
    """A supplier document with many lines, all-or-nothing."""

    def __init__(self, purchases: PurchaseRepository, stock: InboundStockGateway) -> None:
        self._r = _Receiver(purchases, stock)

    def execute(
        self,
        company_id: UUID,
        *,
        supplier_id: UUID,
        purchase_date: date,
        document_number: str = "",
        notes: str = "",
        costs_include_igv: bool = False,
        items: list[dict[str, Any]],
    ) -> PurchaseBatchResultDTO:
        if not items:
            raise InvalidPurchaseError(message="Agrega al menos un producto a la compra")
        _check_date(purchase_date)
        self._r.ensure_supplier(company_id, supplier_id)
        stock = self._r.stock
        batch_id = uuid4()
        doc = document_number.strip()
        lines: list[PurchaseDTO] = []
        changes: list[StockChangeDTO] = []
        new_products: list[NewProductDTO] = []

        for n, item in enumerate(items, start=1):
            try:
                quantity = _quantity(item.get("quantity"))
                net_cost = _unit_cost(item.get("unit_cost"), costs_include_igv)
                total = _line_total(item.get("unit_cost"), quantity, costs_include_igv)
                new = item.get("new_product")
                if item.get("product_id"):
                    product = stock.get_product(company_id, UUID(str(item["product_id"])))
                    if product is None:
                        raise InvalidPurchaseError(message="ese producto ya no existe; elige otro")
                elif new and str(new.get("name") or "").strip():
                    sku = str(new.get("sku") or "").strip()
                    if sku and stock.sku_taken(company_id, sku):
                        raise DuplicateProductCodeError(sku.upper())
                    product = stock.create_product(
                        company_id,
                        name=_check_length(str(new["name"]).strip(), 255, "El nombre del producto"),
                        sku=sku or None,
                        barcode=new.get("barcode"),
                        unit_price=_sale_price(new.get("unit_price")),
                        category_id=UUID(str(new["category_id"])) if new.get("category_id") else None,
                        custom_attributes=new.get("custom_attributes"),
                    )
                    new_products.append(NewProductDTO(row=n, product_id=product.id, name=product.name, sku=product.sku))
                else:
                    raise InvalidPurchaseError(message="elige un producto o escribe el nombre del producto nuevo")
            except DomainError as exc:
                exc.message = f"Línea {n}: {exc.message[0].lower()}{exc.message[1:]}" if exc.message else f"Línea {n}"
                raise

            line, change = self._r.line(
                company_id,
                supplier_id=supplier_id,
                product=product,
                purchase_date=purchase_date,
                quantity=quantity,
                net_unit_cost=net_cost,
                line_total=total,
                document_number=doc,
                notes=notes.strip(),
                batch_id=batch_id,
            )
            lines.append(line)
            changes.append(change)

        subtotal = sum((line.total_amount for line in lines), Decimal("0"))
        igv = igv_of(subtotal)
        return PurchaseBatchResultDTO(
            batch_id=batch_id,
            document_number=doc,
            purchase_date=purchase_date,
            costs_include_igv=costs_include_igv,
            lines=lines,
            new_products=new_products,
            stock_changes=changes,
            units=sum(line.quantity for line in lines),
            subtotal=subtotal,
            igv=igv,
            total=subtotal + igv,
        )


class ImportPurchases:
    """Bulk purchase lines from a spreadsheet, one savepoint per row.

    Product matching: code (SKU, case-insensitive) → barcode → exact name. Unknown
    products are created when allowed, using the file's code as SKU or the company's
    correlativo (P-000123) when the row has no code. Rows whose own date / document
    number differ from the defaults become separate documents (one batch id each).
    """

    def __init__(self, purchases: PurchaseRepository, stock: InboundStockGateway) -> None:
        self._r = _Receiver(purchases, stock)

    def execute(
        self,
        company_id: UUID,
        *,
        supplier_id: UUID,
        purchase_date: date,
        document_number: str = "",
        create_missing_products: bool = True,
        costs_include_igv: bool = False,
        notes: str = "",
        rows: list[dict[str, Any]],
    ) -> PurchaseImportResultDTO:
        self._r.ensure_supplier(company_id, supplier_id)
        stock = self._r.stock
        batches: dict[tuple[date, str], UUID] = {}
        used: list[UUID] = []  # batches with at least one saved row, in order
        created = matched = units = 0
        subtotal = Decimal("0")
        new_products: list[NewProductDTO] = []
        errors: list[ImportErrorDTO] = []

        for index, row in enumerate(rows, start=1):
            row_no = int(row.get("row") or index)
            try:
                with stock.savepoint():
                    day = purchase_date
                    if row.get("purchase_date"):
                        try:
                            day = date.fromisoformat(str(row["purchase_date"])[:10])
                        except ValueError:
                            raise InvalidPurchaseError(message=f"La fecha «{row['purchase_date']}» no es válida. Usa el formato AAAA-MM-DD.")
                    _check_date(day)
                    quantity = _quantity(row.get("quantity"))
                    net_cost = _unit_cost(row.get("unit_cost"), costs_include_igv)
                    total = _line_total(row.get("unit_cost"), quantity, costs_include_igv)
                    code = _check_length(str(row.get("code") or "").strip(), 64, "El código del producto")
                    barcode = _check_length(str(row.get("barcode") or "").strip(), 64, "El código de barras")
                    name = _check_length(str(row.get("name") or "").strip(), 255, "El nombre del producto")
                    if not (code or barcode or name):
                        raise InvalidPurchaseError(message="La fila no tiene código, código de barras ni nombre de producto")
                    price = _sale_price(row.get("unit_price"))
                    custom = {k: v for k, v in (row.get("custom_attributes") or {}).items() if v not in (None, "")}

                    found = stock.find_product(company_id, code=code, barcode=barcode, name=name)
                    created_product: NewProductDTO | None = None
                    if found is not None:
                        product = found[0]
                        stock.update_product(company_id, product.id, unit_price=price, custom_attributes=custom)
                    elif not create_missing_products:
                        raise InvalidPurchaseError(message=f"No encontramos el producto {code or barcode or name}")
                    elif not name:
                        raise InvalidPurchaseError(
                            message=f"El producto {code or barcode} no existe y la fila no trae su nombre para crearlo"
                        )
                    else:
                        product = stock.create_product(
                            company_id,
                            name=name,
                            sku=code or None,
                            barcode=barcode or None,
                            unit_price=price,
                            category_id=None,
                            custom_attributes=custom,
                        )
                        created_product = NewProductDTO(row=row_no, product_id=product.id, name=product.name, sku=product.sku)

                    doc = str(row.get("document_number") or "").strip() or document_number.strip()
                    batch_id = batches.setdefault((day, doc), uuid4())

                    line, _ = self._r.line(
                        company_id,
                        supplier_id=supplier_id,
                        product=product,
                        purchase_date=day,
                        quantity=quantity,
                        net_unit_cost=net_cost,
                        line_total=total,
                        document_number=doc,
                        notes=notes.strip(),
                        batch_id=batch_id,
                    )
                # Savepoint committed: count the row.
                if batch_id not in used:
                    used.append(batch_id)
                created += 1
                units += line.quantity
                subtotal += line.total_amount
                if created_product:
                    new_products.append(created_product)
                else:
                    matched += 1
            except DomainError as exc:
                errors.append(ImportErrorDTO(row=row_no, message=exc.message))
            except Exception as exc:  # noqa: BLE001 — report the row, keep importing
                errors.append(ImportErrorDTO(row=row_no, message=f"No se pudo guardar la fila ({type(exc).__name__}). Revisa sus datos e inténtalo de nuevo."))

        # Batches whose every row failed were rolled back: only `used` is reported.
        igv = igv_of(subtotal)
        return PurchaseImportResultDTO(
            batch_id=used[0] if used else None,
            batch_ids=used,
            created_lines=created,
            matched=matched,
            new_products=new_products,
            errors=errors,
            units=units,
            subtotal=subtotal,
            igv=igv,
            total=subtotal + igv,
        )


class ListPurchases:
    def __init__(self, purchases: PurchaseRepository) -> None:
        self._purchases = purchases

    def execute(
        self,
        company_id: UUID,
        *,
        supplier_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[PurchaseLineDTO]:
        rows = self._purchases.list_lines(
            company_id, supplier_id=supplier_id, date_from=date_from, date_to=date_to, offset=offset, limit=limit
        )
        return [PurchaseLineDTO(**r) for r in rows]


class ListPurchaseDocuments:
    def __init__(self, purchases: PurchaseRepository) -> None:
        self._purchases = purchases

    def execute(
        self,
        company_id: UUID,
        *,
        supplier_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        q: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> PurchaseDocumentPageDTO:
        items, total = self._purchases.list_documents(
            company_id,
            supplier_id=supplier_id,
            date_from=date_from,
            date_to=date_to,
            q=q,
            offset=(page - 1) * size,
            limit=size,
        )
        return PurchaseDocumentPageDTO(
            items=[PurchaseDocumentDTO(**i) for i in items],
            total=total,
            page=page,
            size=size,
            pages=max(1, math.ceil(total / size)) if size else 1,
        )


class GetPurchaseDocument:
    def __init__(self, purchases: PurchaseRepository) -> None:
        self._purchases = purchases

    def execute(self, company_id: UUID, document_id: str) -> PurchaseDocumentDetailDTO:
        doc = self._purchases.get_document(company_id, document_id)
        if doc is None:
            raise PurchaseDocumentNotFoundError(document_id)
        return PurchaseDocumentDetailDTO(**{**doc, "lines": [PurchaseLineDTO(**line) for line in doc["lines"]]})


class GetPurchaseCatalog:
    def __init__(self, stock: InboundStockGateway) -> None:
        self._stock = stock

    def execute(self, company_id: UUID) -> list[PurchaseCatalogItemDTO]:
        return [PurchaseCatalogItemDTO(**p) for p in self._stock.catalog(company_id)]
