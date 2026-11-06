"""Products module — mappers between ORM models and domain entities."""
from __future__ import annotations

from app.modules.products.domain.entities import Category, Product
from app.modules.products.infrastructure.persistence.models import (
    CategoryModel,
    ProductModel,
)
from app.shared.domain.value_objects import Money, Sku


def category_to_entity(model: CategoryModel) -> Category:
    return Category(
        id=model.id,
        company_id=model.company_id,
        name=model.name,
        description=model.description,
        parent_id=model.parent_id,
    )


def category_to_model(entity: Category) -> CategoryModel:
    return CategoryModel(
        id=entity.id,
        company_id=entity.company_id,
        name=entity.name,
        description=entity.description,
        parent_id=entity.parent_id,
    )


def product_to_entity(model: ProductModel) -> Product:
    return Product(
        id=model.id,
        company_id=model.company_id,
        sku=Sku(model.sku),
        name=model.name,
        unit_cost=Money(model.unit_cost, model.currency),
        unit_price=Money(model.unit_price, model.currency),
        description=model.description,
        category_id=model.category_id,
        unit_of_measure=model.unit_of_measure,
        lead_time_days=model.lead_time_days,
        safety_stock=model.safety_stock,
        reorder_point=model.reorder_point,
        is_active=model.is_active,
        barcode=model.barcode,
        image_url=model.image_url,
        custom_attributes=dict(model.custom_attributes or {}),
        last_cost=Money(model.last_cost, model.currency) if model.last_cost is not None else None,
    )


def product_to_model(entity: Product) -> ProductModel:
    return ProductModel(
        id=entity.id,
        company_id=entity.company_id,
        sku=entity.sku.value,
        name=entity.name,
        description=entity.description,
        category_id=entity.category_id,
        unit_cost=entity.unit_cost.amount,
        unit_price=entity.unit_price.amount,
        currency=entity.unit_cost.currency,
        unit_of_measure=entity.unit_of_measure,
        lead_time_days=entity.lead_time_days,
        safety_stock=entity.safety_stock,
        reorder_point=entity.reorder_point,
        is_active=entity.is_active,
        barcode=entity.barcode,
        image_url=entity.image_url,
        custom_attributes=dict(entity.custom_attributes or {}),
        last_cost=entity.last_cost.amount if entity.last_cost else None,
    )
