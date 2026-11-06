"""Products module — use cases for the Product aggregate."""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.products.application.dtos import ProductDTO
from app.modules.products.application.ports import (
    CustomAttributeCaster,
    ProductCodeGenerator,
    ProductHistory,
    ProductStockGateway,
)
from app.modules.products.domain.entities import (
    Product,
    normalize_barcode,
    normalize_image_url,
)
from app.modules.products.domain.exceptions import (
    BarcodeAlreadyExistsError,
    InvalidProductError,
    ProductAlreadyExistsError,
    ProductHasHistoryError,
    ProductNotFoundError,
)
from app.modules.products.domain.repositories import ProductRepository
from app.shared.domain.value_objects import Money, Sku

INITIAL_STOCK_REASON = "Inventario inicial"


def ensure_unique_barcode(
    products: ProductRepository, company_id: UUID, barcode: str | None, exclude_id: UUID | None = None
) -> None:
    if not barcode:
        return
    other = products.get_by_barcode(company_id, barcode)
    if other is not None and other.id != exclude_id:
        raise BarcodeAlreadyExistsError(barcode, other.name)


def _custom_attributes(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise InvalidProductError(message="Los atributos personalizados deben ser un objeto.")
    return dict(raw)


def _get_owned(products: ProductRepository, company_id: UUID, product_id: UUID) -> Product:
    product = products.get_by_id(product_id)
    if product is None or product.company_id != company_id:
        raise ProductNotFoundError(product_id)
    return product


class CreateProduct:
    def __init__(
        self,
        products: ProductRepository,
        codes: ProductCodeGenerator | None = None,
        stock: ProductStockGateway | None = None,
        attributes: CustomAttributeCaster | None = None,
    ) -> None:
        self._products = products
        self._codes = codes
        self._stock = stock
        self._attributes = attributes

    def execute(
        self,
        company_id: UUID,
        *,
        sku: str | None,
        name: str,
        unit_cost: Decimal,
        unit_price: Decimal,
        currency: str = "PEN",
        description: str = "",
        category_id: UUID | None = None,
        unit_of_measure: str = "unit",
        lead_time_days: int = 0,
        safety_stock: int = 0,
        reorder_point: int = 0,
        barcode: str | None = None,
        image_url: str | None = None,
        custom_attributes: dict[str, Any] | None = None,
        initial_stock: int = 0,
    ) -> ProductDTO:
        if initial_stock < 0:
            raise InvalidProductError(message="El stock inicial no puede ser negativo.")
        if sku and sku.strip():
            sku_vo = Sku(sku)
            if self._products.get_by_sku(company_id, sku_vo.value) is not None:
                raise ProductAlreadyExistsError(sku_vo.value)
        else:
            if self._codes is None:
                raise InvalidProductError(message="El código del producto es obligatorio.")
            sku_vo = Sku(self._codes.next_code(company_id))
        clean_barcode = normalize_barcode(barcode)
        ensure_unique_barcode(self._products, company_id, clean_barcode)
        attrs = _custom_attributes(custom_attributes)
        if attrs and self._attributes is not None:
            attrs = self._attributes.cast(company_id, attrs)

        product = Product(
            company_id=company_id,
            sku=sku_vo,
            name=name.strip(),
            unit_cost=Money(unit_cost, currency),
            unit_price=Money(unit_price, currency),
            description=description,
            category_id=category_id,
            unit_of_measure=unit_of_measure,
            lead_time_days=lead_time_days,
            safety_stock=safety_stock,
            reorder_point=reorder_point,
            barcode=clean_barcode,
            image_url=image_url,
            custom_attributes=attrs,
        )
        saved = self._products.add(product)
        if initial_stock > 0 and self._stock is not None and saved.id is not None:
            self._stock.receive(
                company_id,
                saved.id,
                initial_stock,
                unit_cost,
                reason=INITIAL_STOCK_REASON,
                reference_type="initial",
            )
            refreshed = self._products.get_by_id(saved.id)
            if refreshed is not None:
                saved = refreshed
        return ProductDTO.from_entity(saved)


class GetProduct:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    def execute(self, product_id: UUID, company_id: UUID | None = None) -> ProductDTO:
        product = self._products.get_by_id(product_id)
        if product is None or (company_id is not None and product.company_id != company_id):
            raise ProductNotFoundError(product_id)
        return ProductDTO.from_entity(product)


class ListProducts:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    def execute(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[ProductDTO]:
        return [
            ProductDTO.from_entity(p)
            for p in self._products.list_by_company(company_id, offset, limit)
        ]


_UPDATABLE = {
    "sku", "name", "description", "category_id", "unit_cost", "unit_price", "unit_of_measure",
    "lead_time_days", "safety_stock", "reorder_point", "is_active", "barcode", "image_url",
    "custom_attributes",
}


class UpdateProduct:
    """Partial update: only the keys present in `changes` are applied (null clears
    nullable fields such as category, barcode or image)."""

    def __init__(
        self, products: ProductRepository, attributes: CustomAttributeCaster | None = None
    ) -> None:
        self._products = products
        self._attributes = attributes

    def execute(self, company_id: UUID, product_id: UUID, changes: dict[str, Any]) -> ProductDTO:
        product = _get_owned(self._products, company_id, product_id)
        currency = product.unit_cost.currency
        unknown = set(changes) - _UPDATABLE
        if unknown:
            raise InvalidProductError(message=f"Campos no editables: {', '.join(sorted(unknown))}")

        if "sku" in changes and changes["sku"] is not None and str(changes["sku"]).strip():
            new_sku = Sku(str(changes["sku"]))
            if new_sku.value != product.sku.value:
                if self._products.get_by_sku(company_id, new_sku.value) is not None:
                    raise ProductAlreadyExistsError(new_sku.value)
                product.sku = new_sku
        if "name" in changes and changes["name"] is not None:
            if not str(changes["name"]).strip():
                raise InvalidProductError(message="El nombre del producto es obligatorio.")
            product.name = str(changes["name"]).strip()
        if "description" in changes:
            product.description = changes["description"] or ""
        if "category_id" in changes:
            product.category_id = changes["category_id"]
        if changes.get("unit_cost") is not None:
            product.unit_cost = Money(Decimal(changes["unit_cost"]), currency)
        if changes.get("unit_price") is not None:
            product.unit_price = Money(Decimal(changes["unit_price"]), currency)
        if changes.get("unit_of_measure"):
            product.unit_of_measure = changes["unit_of_measure"]
        for key in ("lead_time_days", "safety_stock", "reorder_point"):
            if changes.get(key) is not None:
                if int(changes[key]) < 0:
                    raise InvalidProductError(message="Los valores de stock no pueden ser negativos.")
                setattr(product, key, int(changes[key]))
        if changes.get("is_active") is not None:
            product.is_active = bool(changes["is_active"])
        if "barcode" in changes:
            barcode = normalize_barcode(changes["barcode"])
            ensure_unique_barcode(self._products, company_id, barcode, exclude_id=product.id)
            product.barcode = barcode
        if "image_url" in changes:
            product.image_url = normalize_image_url(changes["image_url"])
        if "custom_attributes" in changes:
            attrs = _custom_attributes(changes["custom_attributes"] or {})
            if attrs and self._attributes is not None:
                # Only values that changed are checked against the column rules.
                attrs = self._attributes.cast(
                    company_id, attrs, previous=dict(product.custom_attributes or {})
                )
            product.custom_attributes = attrs
        return ProductDTO.from_entity(self._products.update(product))


class DeleteProduct:
    """Deletes a product only while nothing references it.

    A product with sales, purchases, stock movements, lost sales, recommendations or
    forecasts is part of the shop's history: deleting it would orphan those records, so
    it must be paused (is_active = false) instead.
    """

    def __init__(self, products: ProductRepository, history: ProductHistory | None = None) -> None:
        self._products = products
        self._history = history

    def execute(self, product_id: UUID, company_id: UUID | None = None) -> bool:
        product = self._products.get_by_id(product_id)
        if product is None or (company_id is not None and product.company_id != company_id):
            raise ProductNotFoundError(product_id)
        if self._history is not None and self._history.has_history(product.company_id, product_id):
            raise ProductHasHistoryError(product_id)
        if not self._products.delete(product_id):
            raise ProductNotFoundError(product_id)
        return True
