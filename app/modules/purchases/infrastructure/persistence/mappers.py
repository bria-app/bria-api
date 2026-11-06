"""Purchases module — mappers between ORM models and domain entities."""
from __future__ import annotations

from app.modules.purchases.domain.entities import Purchase
from app.modules.purchases.infrastructure.persistence.models import PurchaseModel
from app.shared.domain.value_objects import Money, Quantity


def purchase_to_entity(model: PurchaseModel) -> Purchase:
    return Purchase(
        id=model.id,
        company_id=model.company_id,
        supplier_id=model.supplier_id,
        product_id=model.product_id,
        purchase_date=model.purchase_date,
        quantity=Quantity(model.quantity),
        unit_cost=Money(model.unit_cost, model.currency),
        total_amount=Money(model.total_amount, model.currency),
        document_number=model.document_number or "",
        notes=model.notes or "",
        import_batch_id=model.import_batch_id,
    )


def purchase_to_model(entity: Purchase) -> PurchaseModel:
    return PurchaseModel(
        id=entity.id,
        company_id=entity.company_id,
        supplier_id=entity.supplier_id,
        product_id=entity.product_id,
        purchase_date=entity.purchase_date,
        quantity=entity.quantity.value,
        unit_cost=entity.unit_cost.amount,
        total_amount=entity.total_amount.amount,
        currency=entity.unit_cost.currency,
        document_number=entity.document_number,
        notes=entity.notes,
        import_batch_id=entity.import_batch_id,
    )
