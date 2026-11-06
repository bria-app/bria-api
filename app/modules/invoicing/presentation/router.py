"""Invoicing module — HTTP router wired to use cases."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.invoicing.application.dtos import InvoiceDTO
from app.modules.invoicing.application.use_cases.invoice import (
    CreateInvoice,
    GetInvoice,
    ListInvoices,
    VoidInvoice,
)
from app.modules.invoicing.domain.repositories import InvoiceRepository
from app.modules.invoicing.presentation.dependencies import get_invoice_repository
from app.modules.invoicing.presentation.schemas import CreateInvoiceRequest
from app.shared.presentation.deps import AuthenticatedUser, require_company_access

router = APIRouter()


@router.get("", response_model=list[InvoiceDTO])
def list_invoices(
    company_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: InvoiceRepository = Depends(get_invoice_repository),
) -> list[InvoiceDTO]:
    return ListInvoices(repo).execute(company_id)


@router.post("", response_model=InvoiceDTO, status_code=201)
def create_invoice(
    company_id: UUID,
    request: CreateInvoiceRequest,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: InvoiceRepository = Depends(get_invoice_repository),
) -> InvoiceDTO:
    return CreateInvoice(repo).execute(
        company_id,
        document_type=request.document_type,
        client_doc_type=request.client_doc_type,
        client_doc_number=request.client_doc_number,
        client_name=request.client_name,
        items=[item.model_dump(mode="json") for item in request.items],
        currency=request.currency,
        sale_id=request.sale_id,
        prices_include_igv=request.prices_include_igv,
        client_address=request.client_address,
    )


@router.get("/{invoice_id}", response_model=InvoiceDTO)
def get_invoice(
    company_id: UUID,
    invoice_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: InvoiceRepository = Depends(get_invoice_repository),
) -> InvoiceDTO:
    return GetInvoice(repo).execute(company_id, invoice_id)


@router.post("/{invoice_id}/void", response_model=InvoiceDTO)
def void_invoice(
    company_id: UUID,
    invoice_id: UUID,
    _: AuthenticatedUser = Depends(require_company_access),
    repo: InvoiceRepository = Depends(get_invoice_repository),
) -> InvoiceDTO:
    return VoidInvoice(repo).execute(company_id, invoice_id)
