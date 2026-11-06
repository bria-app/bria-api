"""Sales module — read-only product catalog adapter (products + categories + stock).

The till reads products without going through the products module's use cases:
it only needs a lookup/search view with stock on hand.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.inventory.infrastructure.persistence.queries import stock_on_hand_map
from app.modules.products.infrastructure.persistence.models import CategoryModel, ProductModel
from app.modules.sales.domain.entities import CatalogProduct


def _to_catalog(p: ProductModel, category_name: str | None, stock: int) -> CatalogProduct:
    return CatalogProduct(
        id=p.id,
        sku=p.sku,
        name=p.name,
        description=p.description or "",
        unit_price=p.unit_price,
        unit_cost=p.unit_cost,
        currency=p.currency,
        is_active=p.is_active,
        stock_on_hand=stock,
        barcode=p.barcode,
        image_url=p.image_url,
        unit_of_measure=p.unit_of_measure,
        category_id=p.category_id,
        category_name=category_name,
        reorder_point=p.reorder_point,
        safety_stock=p.safety_stock,
        custom_attributes=dict(p.custom_attributes or {}),
    )


class SqlProductCatalog:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _base(self, company_id: UUID):  # type: ignore[no-untyped-def]
        return (
            select(ProductModel, CategoryModel.name)
            .outerjoin(CategoryModel, CategoryModel.id == ProductModel.category_id)
            .where(ProductModel.company_id == company_id)
        )

    def get_many(self, company_id: UUID, product_ids: list[UUID]) -> dict[UUID, CatalogProduct]:
        if not product_ids:
            return {}
        rows = self._session.execute(
            self._base(company_id).where(ProductModel.id.in_(product_ids))
        ).all()
        stock = stock_on_hand_map(self._session, company_id)
        return {p.id: _to_catalog(p, cat, stock.get(p.id, 0)) for p, cat in rows}

    def lookup(self, company_id: UUID, code: str) -> CatalogProduct | None:
        normalized = code.strip().lower()
        if not normalized:
            return None
        row = self._session.execute(
            self._base(company_id)
            .where(
                ProductModel.is_active.is_(True),
                or_(
                    func.lower(ProductModel.barcode) == normalized,
                    func.lower(ProductModel.sku) == normalized,
                ),
            )
            .order_by(ProductModel.name)
            .limit(1)
        ).first()
        if row is None:
            return None
        p, cat = row
        stock = stock_on_hand_map(self._session, company_id)
        return _to_catalog(p, cat, stock.get(p.id, 0))

    def search(self, company_id: UUID, query: str, limit: int) -> list[CatalogProduct]:
        stmt = self._base(company_id).where(ProductModel.is_active.is_(True))
        term = query.strip()
        if term:
            like = f"%{term}%"
            stmt = stmt.where(
                or_(
                    ProductModel.name.ilike(like),
                    ProductModel.sku.ilike(like),
                    ProductModel.barcode.ilike(like),
                    CategoryModel.name.ilike(like),
                )
            )
        rows = self._session.execute(stmt.order_by(ProductModel.name).limit(limit)).all()
        stock = stock_on_hand_map(self._session, company_id)
        return [_to_catalog(p, cat, stock.get(p.id, 0)) for p, cat in rows]
