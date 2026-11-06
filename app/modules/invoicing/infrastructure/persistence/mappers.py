"""Invoicing module — mappers between ORM models and domain entities."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.modules.invoicing.domain.entities import Invoice, InvoiceItem
from app.modules.invoicing.domain.enums import ClientDocType, DocumentType, InvoiceStatus
from app.modules.invoicing.infrastructure.persistence.models import InvoiceModel


def invoice_to_entity(model: InvoiceModel) -> Invoice:
    return Invoice(
        id=model.id,
        company_id=model.company_id,
        document_type=DocumentType(model.document_type),
        series=model.series,
        correlativo=model.correlativo,
        client_doc_type=ClientDocType(model.client_doc_type),
        client_doc_number=model.client_doc_number,
        client_name=model.client_name,
        client_address=model.client_address or "",
        items=[
            InvoiceItem(
                description=it["description"],
                quantity=int(it["quantity"]),
                unit_price=Decimal(str(it["unit_price"])),
                product_id=UUID(it["product_id"]) if it.get("product_id") else None,
                discount=Decimal(str(it.get("discount") or "0")),
            )
            for it in model.items
        ],
        subtotal=model.subtotal,
        igv=model.igv,
        total=model.total,
        currency=model.currency,
        status=InvoiceStatus(model.status),
        issued_at=model.issued_at,
        sale_id=model.sale_id,
    )


def invoice_to_model(entity: Invoice) -> InvoiceModel:
    return InvoiceModel(
        id=entity.id,
        company_id=entity.company_id,
        document_type=entity.document_type.value,
        series=entity.series,
        correlativo=entity.correlativo,
        client_doc_type=entity.client_doc_type.value,
        client_doc_number=entity.client_doc_number,
        client_name=entity.client_name,
        client_address=entity.client_address,
        items=[
            {
                "description": it.description,
                "quantity": it.quantity,
                "unit_price": str(it.unit_price),
                "discount": str(it.discount),
                "product_id": str(it.product_id) if it.product_id else None,
            }
            for it in entity.items
        ],
        subtotal=entity.subtotal,
        igv=entity.igv,
        total=entity.total,
        currency=entity.currency,
        status=entity.status.value,
        issued_at=entity.issued_at,
        sale_id=entity.sale_id,
    )
