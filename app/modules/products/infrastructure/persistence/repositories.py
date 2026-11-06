"""Products module — SQLAlchemy repository implementations."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.products.domain.entities import Category, Product
from app.modules.products.domain.exceptions import (
    CategoryNotFoundError,
    ProductNotFoundError,
)
from app.modules.products.infrastructure.persistence.mappers import (
    category_to_entity,
    category_to_model,
    product_to_entity,
    product_to_model,
)
from app.modules.products.infrastructure.persistence.models import (
    CategoryModel,
    ProductModel,
)


class SqlCategoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, category_id: UUID) -> Category | None:
        model = self._session.get(CategoryModel, category_id)
        return category_to_entity(model) if model else None

    def list_by_company(self, company_id: UUID) -> list[Category]:
        rows = self._session.execute(
            select(CategoryModel)
            .where(CategoryModel.company_id == company_id)
            .order_by(CategoryModel.name)
        ).scalars().all()
        return [category_to_entity(m) for m in rows]

    def add(self, category: Category) -> Category:
        model = category_to_model(category)
        self._session.add(model)
        self._session.flush()
        return category_to_entity(model)

    def update(self, category: Category) -> Category:
        model = self._session.get(CategoryModel, category.id)
        if model is None:
            raise CategoryNotFoundError(category.id)  # type: ignore[arg-type]
        model.name = category.name
        model.description = category.description
        model.parent_id = category.parent_id
        self._session.flush()
        return category_to_entity(model)

    def delete(self, category_id: UUID) -> bool:
        model = self._session.get(CategoryModel, category_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True

    def count_subcategories(self, category_id: UUID) -> int:
        return int(
            self._session.execute(
                select(func.count(CategoryModel.id)).where(CategoryModel.parent_id == category_id)
            ).scalar_one()
        )

    def count_products(self, category_id: UUID) -> int:
        return int(
            self._session.execute(
                select(func.count(ProductModel.id)).where(ProductModel.category_id == category_id)
            ).scalar_one()
        )


class SqlProductRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, product_id: UUID) -> Product | None:
        model = self._session.get(ProductModel, product_id)
        return product_to_entity(model) if model else None

    def get_by_sku(self, company_id: UUID, sku: str) -> Product | None:
        normalized = sku.strip().upper()
        model = self._session.execute(
            select(ProductModel).where(
                ProductModel.company_id == company_id,
                ProductModel.sku == normalized,
            )
        ).scalar_one_or_none()
        return product_to_entity(model) if model else None

    def get_by_barcode(self, company_id: UUID, barcode: str) -> Product | None:
        cleaned = barcode.strip()
        if not cleaned:
            return None
        model = self._session.execute(
            select(ProductModel)
            .where(ProductModel.company_id == company_id, ProductModel.barcode == cleaned)
            .limit(1)
        ).scalar_one_or_none()
        return product_to_entity(model) if model else None

    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[Product]:
        rows = self._session.execute(
            select(ProductModel)
            .where(ProductModel.company_id == company_id)
            .order_by(ProductModel.name)
            .offset(offset)
            .limit(limit)
        ).scalars().all()
        return [product_to_entity(m) for m in rows]

    def list_active(self, company_id: UUID) -> list[Product]:
        rows = self._session.execute(
            select(ProductModel)
            .where(ProductModel.company_id == company_id, ProductModel.is_active.is_(True))
            .order_by(ProductModel.name)
        ).scalars().all()
        return [product_to_entity(m) for m in rows]

    def add(self, product: Product) -> Product:
        model = product_to_model(product)
        self._session.add(model)
        self._session.flush()
        return product_to_entity(model)

    def update(self, product: Product) -> Product:
        model = self._session.get(ProductModel, product.id)
        if model is None:
            raise ProductNotFoundError(product.id)  # type: ignore[arg-type]
        model.sku = product.sku.value
        model.name = product.name
        model.description = product.description
        model.category_id = product.category_id
        model.unit_cost = product.unit_cost.amount
        model.unit_price = product.unit_price.amount
        model.currency = product.unit_cost.currency
        model.unit_of_measure = product.unit_of_measure
        model.lead_time_days = product.lead_time_days
        model.safety_stock = product.safety_stock
        model.reorder_point = product.reorder_point
        model.is_active = product.is_active
        model.barcode = product.barcode
        model.image_url = product.image_url
        model.custom_attributes = dict(product.custom_attributes or {})
        model.last_cost = product.last_cost.amount if product.last_cost else model.last_cost
        self._session.flush()
        return product_to_entity(model)

    def delete(self, product_id: UUID) -> bool:
        model = self._session.get(ProductModel, product_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True
