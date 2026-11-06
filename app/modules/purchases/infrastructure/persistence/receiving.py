"""Purchases module — catalog + inventory side of receiving a purchase.

Cross-module writes live here (not in the use cases) so the application layer only
sees the InboundStockGateway port: product lookup/creation, the weighted-average cost
update (inventory's apply_inbound_cost) and the inbound movement with its valuation and
reference to the purchase document.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.inventory.domain.enums import MovementType
from app.modules.inventory.infrastructure.persistence.models import InventoryMovementModel
from app.modules.inventory.infrastructure.persistence.queries import (
    apply_inbound_cost,
    stock_on_hand,
    stock_on_hand_map,
)
from app.modules.products.infrastructure.persistence.codes import next_product_code
from app.modules.products.infrastructure.persistence.models import ProductModel
from app.modules.purchases.domain.entities import ProductRef, StockReceipt
from app.modules.suppliers.infrastructure.persistence.models import SupplierModel

REFERENCE_TYPE = "purchase"


def _ref(model: ProductModel) -> ProductRef:
    return ProductRef(id=model.id, sku=model.sku, name=model.name)


class SqlInboundStockGateway:
    def __init__(self, session: Session) -> None:
        self._session = session

    def savepoint(self) -> Any:
        return self._session.begin_nested()

    def supplier_exists(self, company_id: UUID, supplier_id: UUID) -> bool:
        model = self._session.get(SupplierModel, supplier_id)
        return model is not None and model.company_id == company_id

    def get_product(self, company_id: UUID, product_id: UUID) -> ProductRef | None:
        model = self._session.get(ProductModel, product_id)
        return _ref(model) if model and model.company_id == company_id else None

    def _first(self, *conds: Any) -> ProductModel | None:
        return self._session.execute(
            select(ProductModel).where(*conds).order_by(ProductModel.is_active.desc(), ProductModel.created_at)
        ).scalars().first()

    def find_product(
        self, company_id: UUID, *, code: str | None, barcode: str | None, name: str | None
    ) -> tuple[ProductRef, str] | None:
        scope = ProductModel.company_id == company_id
        if code and code.strip():
            m = self._first(scope, func.upper(ProductModel.sku) == code.strip().upper())
            if m:
                return _ref(m), "code"
        if barcode and barcode.strip():
            m = self._first(scope, ProductModel.barcode == barcode.strip())
            if m:
                return _ref(m), "barcode"
        if name and name.strip():
            m = self._first(scope, func.lower(ProductModel.name) == name.strip().lower())
            if m:
                return _ref(m), "name"
        return None

    def sku_taken(self, company_id: UUID, sku: str) -> bool:
        return self._first(ProductModel.company_id == company_id, func.upper(ProductModel.sku) == sku.strip().upper()) is not None

    def create_product(
        self,
        company_id: UUID,
        *,
        name: str,
        sku: str | None,
        barcode: str | None,
        unit_price: Decimal | None,
        category_id: UUID | None,
        custom_attributes: dict[str, Any] | None,
    ) -> ProductRef:
        code = sku.strip().upper() if sku and sku.strip() else next_product_code(self._session, company_id)
        model = ProductModel(
            company_id=company_id,
            sku=code,
            name=name.strip(),
            description="",
            category_id=category_id,
            unit_cost=Decimal("0"),  # set by apply_inbound_cost on receipt
            unit_price=Decimal(unit_price) if unit_price is not None else Decimal("0"),
            currency="PEN",
            barcode=barcode.strip() if barcode and barcode.strip() else None,
            custom_attributes=dict(custom_attributes or {}),
        )
        self._session.add(model)
        self._session.flush()
        return _ref(model)

    def update_product(
        self,
        company_id: UUID,
        product_id: UUID,
        *,
        unit_price: Decimal | None = None,
        custom_attributes: dict[str, Any] | None = None,
    ) -> None:
        model = self._session.get(ProductModel, product_id)
        if model is None or model.company_id != company_id:
            return
        if unit_price is not None and unit_price > 0:
            model.unit_price = Decimal(unit_price)
        if custom_attributes:
            model.custom_attributes = {**(model.custom_attributes or {}), **custom_attributes}
        self._session.flush()

    def receive(
        self,
        company_id: UUID,
        product_id: UUID,
        *,
        quantity: int,
        unit_cost: Decimal,
        reason: str,
        reference_id: UUID,
        occurred_at: datetime,
    ) -> StockReceipt:
        product = self._session.get(ProductModel, product_id)
        previous_avg = Decimal(product.unit_cost) if product else Decimal("0")
        on_hand = stock_on_hand(self._session, company_id, product_id)
        # Must run before the movement insert: it averages against current on-hand.
        apply_inbound_cost(self._session, company_id, product_id, quantity, unit_cost)
        self._session.add(
            InventoryMovementModel(
                company_id=company_id,
                product_id=product_id,
                movement_type=MovementType.INBOUND.value,
                quantity=quantity,
                reason=reason[:255],
                occurred_at=occurred_at,
                unit_cost=unit_cost,
                reference_type=REFERENCE_TYPE,
                reference_id=reference_id,
            )
        )
        self._session.flush()
        new_avg = Decimal(product.unit_cost) if product else Decimal(unit_cost)
        return StockReceipt(
            product_id=product_id,
            quantity=quantity,
            previous_stock=on_hand,
            new_stock=on_hand + quantity,
            previous_avg_cost=previous_avg,
            new_avg_cost=new_avg,
        )

    def catalog(self, company_id: UUID) -> list[dict[str, Any]]:
        stock = stock_on_hand_map(self._session, company_id)
        products = self._session.execute(
            select(ProductModel).where(ProductModel.company_id == company_id).order_by(ProductModel.name)
        ).scalars().all()
        return [
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "barcode": p.barcode,
                "category_id": p.category_id,
                "unit_cost": Decimal(p.unit_cost),
                "last_cost": Decimal(p.last_cost) if p.last_cost is not None else None,
                "unit_price": Decimal(p.unit_price),
                "stock_on_hand": stock.get(p.id, 0),
                "is_active": p.is_active,
            }
            for p in products
        ]
