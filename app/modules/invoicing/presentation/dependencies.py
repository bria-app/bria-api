"""Invoicing module — presentation DI providers."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.invoicing.infrastructure.persistence.repositories import (
    SqlInvoiceRepository,
)
from app.shared.infrastructure.database import get_db


def get_invoice_repository(db: Session = Depends(get_db, scope="function")) -> SqlInvoiceRepository:
    return SqlInvoiceRepository(db)
