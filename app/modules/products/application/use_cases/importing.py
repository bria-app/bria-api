"""Products module — smart import of an inventory spreadsheet.

Each row is processed inside its own savepoint so a bad row never aborts the file:
the good rows are kept and the bad ones come back as `{row, message}`.

Rules:
- The file's code becomes the SKU; rows without a code get the company correlativo.
- With `update_existing`, a row matches an existing product by SKU first, then barcode.
- Categories are created on the fly by name. "Marca > Tipo" (also "›" or "/") builds
  the two-level tree used by the catalog.
- New products with stock get an inbound movement valued at the row's cost. For
  existing products the stock column is a physical count: the difference is posted.
- Own columns (custom_attributes) are typed by their field definition: numbers, Sí/No,
  dates and select options, then checked against the column's validation rules (max
  length, only digits, min/max, no future dates...). A value that does not fit is a row
  error naming the column; keys without a definition are kept as they came.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from app.modules.products.application.dtos import ImportProductsResultDTO, ImportRowError
from app.modules.products.application.ports import (
    CustomAttributeCaster,
    ProductCodeGenerator,
    ProductStockGateway,
    UnitOfWork,
)
from app.modules.products.domain.entities import Category, Product, normalize_barcode
from app.modules.products.domain.repositories import CategoryRepository, ProductRepository
from app.shared.domain.errors import DomainError
from app.shared.domain.value_objects import Money, Sku

IMPORT_STOCK_REASON = "Inventario inicial (importación)"
IMPORT_COUNT_REASON = "Ajuste por importación"
_CATEGORY_SPLIT = re.compile(r"\s*(?:>|›|/|»)\s*")


@dataclass
class ProductImportRow:
    name: str
    unit_price: Decimal | None
    sku: str | None = None
    barcode: str | None = None
    category: str | None = None
    unit_cost: Decimal | None = None
    initial_stock: int | None = None
    safety_stock: int | None = None
    reorder_point: int | None = None
    lead_time_days: int | None = None
    unit_of_measure: str | None = None
    custom_attributes: dict[str, Any] = field(default_factory=dict)
    row: int | None = None


class _RowError(Exception):
    pass


def _non_negative(value: Any, label: str, integer: bool = False) -> Any:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise _RowError(f"{label}: '{value}' no es un número válido") from exc
    if number < 0:
        raise _RowError(f"{label} no puede ser negativo")
    if integer:
        if number != number.to_integral_value():
            raise _RowError(f"{label} debe ser un número entero")
        return int(number)
    return number.quantize(Decimal("0.01"))


class ImportProducts:
    def __init__(
        self,
        *,
        products: ProductRepository,
        categories: CategoryRepository,
        codes: ProductCodeGenerator,
        stock: ProductStockGateway,
        uow: UnitOfWork,
        attributes: CustomAttributeCaster | None = None,
    ) -> None:
        self._products = products
        self._attributes = attributes
        self._categories = categories
        self._codes = codes
        self._stock = stock
        self._uow = uow
        self._category_cache: dict[tuple[UUID | None, str], UUID] = {}
        self._categories_created = 0

    # -- categories ---------------------------------------------------------
    def _load_categories(self, company_id: UUID) -> None:
        for c in self._categories.list_by_company(company_id):
            if c.id is not None:
                self._category_cache.setdefault((c.parent_id, c.name.strip().lower()), c.id)

    def _resolve_category(self, company_id: UUID, raw: str | None) -> UUID | None:
        if not raw or not raw.strip():
            return None
        parent: UUID | None = None
        for part in [p for p in _CATEGORY_SPLIT.split(raw.strip()) if p]:
            key = (parent, part.lower())
            found = self._category_cache.get(key)
            if found is None:
                created = self._categories.add(
                    Category(company_id=company_id, name=part[:255], parent_id=parent)
                )
                assert created.id is not None
                found = created.id
                self._category_cache[key] = found
                self._categories_created += 1
            parent = found
        return parent

    # -- rows ---------------------------------------------------------------
    def _find_existing(self, company_id: UUID, sku: str | None, barcode: str | None) -> Product | None:
        if sku:
            existing = self._products.get_by_sku(company_id, sku)
            if existing is not None:
                return existing
        if barcode:
            return self._products.get_by_barcode(company_id, barcode)
        return None

    def _process(self, company_id: UUID, row: ProductImportRow, update_existing: bool) -> str:
        name = (row.name or "").strip()
        sku = Sku(row.sku).value if row.sku and row.sku.strip() else None
        if sku and len(sku) > 64:
            raise _RowError("El código no puede superar 64 caracteres")
        barcode = normalize_barcode(row.barcode)
        unit_price = _non_negative(row.unit_price, "Precio")
        unit_cost = _non_negative(row.unit_cost, "Costo")
        initial_stock = _non_negative(row.initial_stock, "Stock", integer=True)
        safety = _non_negative(row.safety_stock, "Stock de seguridad", integer=True)
        reorder = _non_negative(row.reorder_point, "Punto de reorden", integer=True)
        lead = _non_negative(row.lead_time_days, "Tiempo de reposición", integer=True)
        uom = (row.unit_of_measure or "").strip()[:20] or None
        attrs = {
            k: v for k, v in (row.custom_attributes or {}).items()
            if v is not None and not (isinstance(v, str) and not v.strip())
        }
        existing = self._find_existing(company_id, sku, barcode)
        if existing is not None and not update_existing:
            label = f"código '{sku}'" if sku and existing.sku.value == sku else f"código de barras '{barcode}'"
            raise _RowError(f"Ya existe un producto con {label} ({existing.name})")
        if attrs and self._attributes is not None:
            # Values equal to the stored ones are not re-checked against the column rules.
            previous = dict(existing.custom_attributes or {}) if existing is not None else None
            attrs = self._attributes.cast(company_id, attrs, previous=previous)

        if existing is not None:
            return self._update(company_id, existing, name, barcode, row.category, unit_price, unit_cost,
                                initial_stock, safety, reorder, lead, uom, attrs)

        if not name:
            raise _RowError("El nombre del producto está vacío")
        if unit_price is None:
            raise _RowError("El precio de venta está vacío")
        if barcode:
            other = self._products.get_by_barcode(company_id, barcode)
            if other is not None:
                raise _RowError(f"El código de barras '{barcode}' ya pertenece a {other.name}")
        category_id = self._resolve_category(company_id, row.category)
        cost = unit_cost if unit_cost is not None else Decimal("0")
        product = Product(
            company_id=company_id,
            sku=Sku(sku or self._codes.next_code(company_id)),
            name=name[:255],
            unit_cost=Money(cost),
            unit_price=Money(unit_price),
            category_id=category_id,
            unit_of_measure=uom or "unit",
            lead_time_days=lead or 0,
            safety_stock=safety or 0,
            reorder_point=reorder or 0,
            barcode=barcode,
            custom_attributes=attrs,
        )
        saved = self._products.add(product)
        assert saved.id is not None
        if initial_stock:
            self._stock.receive(
                company_id, saved.id, initial_stock, cost,
                reason=IMPORT_STOCK_REASON, reference_type="import",
            )
        return "created"

    def _update(
        self, company_id: UUID, product: Product, name: str, barcode: str | None, category: str | None,
        unit_price: Decimal | None, unit_cost: Decimal | None, counted: int | None,
        safety: int | None, reorder: int | None, lead: int | None, uom: str | None, attrs: dict[str, Any],
    ) -> str:
        assert product.id is not None
        currency = product.unit_price.currency
        if name:
            product.name = name[:255]
        if barcode and barcode != product.barcode:
            other = self._products.get_by_barcode(company_id, barcode)
            if other is not None and other.id != product.id:
                raise _RowError(f"El código de barras '{barcode}' ya pertenece a {other.name}")
            product.barcode = barcode
        if category and category.strip():
            product.category_id = self._resolve_category(company_id, category)
        if unit_price is not None:
            product.unit_price = Money(unit_price, currency)
        if safety is not None:
            product.safety_stock = safety
        if reorder is not None:
            product.reorder_point = reorder
        if lead is not None:
            product.lead_time_days = lead
        if uom:
            product.unit_of_measure = uom
        if attrs:
            product.custom_attributes = {**(product.custom_attributes or {}), **attrs}

        delta = 0
        if counted is not None:
            delta = counted - self._stock.on_hand(company_id, product.id)
        if unit_cost is not None and delta <= 0:
            # No receipt to average against: the file's cost is the reference cost.
            product.unit_cost = Money(unit_cost, currency)
        self._products.update(product)

        if delta > 0:
            self._stock.receive(
                company_id, product.id, delta, unit_cost,
                reason=IMPORT_COUNT_REASON, reference_type="import",
            )
        elif delta < 0:
            self._stock.remove(
                company_id, product.id, -delta,
                reason=IMPORT_COUNT_REASON, reference_type="import",
            )
        return "updated"

    def execute(
        self, company_id: UUID, rows: list[ProductImportRow], update_existing: bool = False
    ) -> ImportProductsResultDTO:
        self._load_categories(company_id)
        created = updated = 0
        errors: list[ImportRowError] = []
        for index, row in enumerate(rows, start=1):
            row_number = row.row or index
            cache_before = dict(self._category_cache)
            categories_before = self._categories_created
            try:
                with self._uow.savepoint():
                    outcome = self._process(company_id, row, update_existing)
                if outcome == "created":
                    created += 1
                else:
                    updated += 1
            except _RowError as exc:
                errors.append(ImportRowError(row=row_number, message=str(exc)))
            except DomainError as exc:
                errors.append(ImportRowError(row=row_number, message=exc.message))
            except Exception as exc:  # noqa: BLE001 — a DB error must not abort the whole file
                errors.append(ImportRowError(row=row_number, message=f"No se pudo guardar la fila ({type(exc).__name__}). Revisa sus datos e inténtalo de nuevo."))
            else:
                continue
            # The savepoint rolled back: forget categories created inside it.
            self._category_cache = cache_before
            self._categories_created = categories_before
        return ImportProductsResultDTO(
            created=created, updated=updated, errors=errors, categories_created=self._categories_created
        )
