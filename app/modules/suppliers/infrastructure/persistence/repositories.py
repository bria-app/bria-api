"""Suppliers module — SQLAlchemy repository implementation."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.suppliers.domain.entities import Supplier
from app.modules.suppliers.domain.exceptions import SupplierNotFoundError
from app.modules.suppliers.infrastructure.persistence.mappers import (
    supplier_to_entity,
    supplier_to_model,
)
from app.modules.suppliers.infrastructure.persistence.models import SupplierModel


class SqlSupplierRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def savepoint(self) -> Any:
        return self._session.begin_nested()

    def get_by_id(self, supplier_id: UUID) -> Supplier | None:
        model = self._session.get(SupplierModel, supplier_id)
        return supplier_to_entity(model) if model else None

    def get_by_ruc(self, company_id: UUID, ruc: str) -> Supplier | None:
        model = self._session.execute(
            select(SupplierModel).where(
                SupplierModel.company_id == company_id, SupplierModel.ruc == ruc
            )
        ).scalars().first()
        return supplier_to_entity(model) if model else None

    def list_by_company(self, company_id: UUID) -> list[Supplier]:
        rows = self._session.execute(
            select(SupplierModel)
            .where(SupplierModel.company_id == company_id)
            .order_by(SupplierModel.business_name)
        ).scalars().all()
        return [supplier_to_entity(m) for m in rows]

    def add(self, supplier: Supplier) -> Supplier:
        model = supplier_to_model(supplier)
        self._session.add(model)
        self._session.flush()
        return supplier_to_entity(model)

    def update(self, supplier: Supplier) -> Supplier:
        model = self._session.get(SupplierModel, supplier.id)
        if model is None:
            raise SupplierNotFoundError(supplier.id)  # type: ignore[arg-type]
        model.business_name = supplier.business_name
        model.contact_name = supplier.contact_name
        model.phone = supplier.phone
        model.email = supplier.email
        model.address = supplier.address
        model.is_active = supplier.is_active
        # Reassign a fresh dict so SQLAlchemy detects the JSON change.
        model.custom_attributes = dict(supplier.custom_attributes or {})
        self._session.flush()
        return supplier_to_entity(model)

    def delete(self, supplier_id: UUID) -> bool:
        model = self._session.get(SupplierModel, supplier_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True
