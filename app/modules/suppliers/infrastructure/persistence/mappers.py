"""Suppliers module — mappers between ORM models and domain entities."""
from __future__ import annotations

from app.modules.suppliers.domain.entities import Supplier
from app.modules.suppliers.infrastructure.persistence.models import SupplierModel


def supplier_to_entity(model: SupplierModel) -> Supplier:
    return Supplier(
        id=model.id,
        company_id=model.company_id,
        ruc=model.ruc,
        business_name=model.business_name,
        contact_name=model.contact_name,
        phone=model.phone,
        email=model.email,
        address=model.address,
        is_active=model.is_active,
        custom_attributes=dict(model.custom_attributes or {}),
    )


def supplier_to_model(entity: Supplier) -> SupplierModel:
    return SupplierModel(
        id=entity.id,
        company_id=entity.company_id,
        ruc=entity.ruc,
        business_name=entity.business_name,
        contact_name=entity.contact_name,
        phone=entity.phone,
        email=entity.email,
        address=entity.address,
        is_active=entity.is_active,
        custom_attributes=dict(entity.custom_attributes or {}),
    )
