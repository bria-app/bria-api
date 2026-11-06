"""Invoicing module — SQLAlchemy repository implementation."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.invoicing.domain.entities import Invoice
from app.modules.invoicing.domain.exceptions import InvoiceNotFoundError
from app.modules.invoicing.infrastructure.persistence.mappers import (
    invoice_to_entity,
    invoice_to_model,
)
from app.modules.invoicing.infrastructure.persistence.models import InvoiceModel


class SqlInvoiceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, invoice_id: UUID) -> Invoice | None:
        model = self._session.get(InvoiceModel, invoice_id)
        return invoice_to_entity(model) if model else None

    def list_by_company(self, company_id: UUID) -> list[Invoice]:
        rows = self._session.execute(
            select(InvoiceModel)
            .where(InvoiceModel.company_id == company_id)
            .order_by(InvoiceModel.issued_at.desc())
        ).scalars().all()
        return [invoice_to_entity(m) for m in rows]

    def next_correlativo(self, company_id: UUID, series: str) -> int:
        current_max = self._session.execute(
            select(func.max(InvoiceModel.correlativo)).where(
                InvoiceModel.company_id == company_id,
                InvoiceModel.series == series,
            )
        ).scalar_one()
        return (current_max or 0) + 1

    def add(self, invoice: Invoice) -> Invoice:
        model = invoice_to_model(invoice)
        self._session.add(model)
        self._session.flush()
        return invoice_to_entity(model)

    def update(self, invoice: Invoice) -> Invoice:
        model = self._session.get(InvoiceModel, invoice.id)
        if model is None:
            raise InvoiceNotFoundError(invoice.id)  # type: ignore[arg-type]
        model.status = invoice.status.value
        self._session.flush()
        return invoice_to_entity(model)
