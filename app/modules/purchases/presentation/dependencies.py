"""Purchases module — presentation DI providers."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.purchases.infrastructure.persistence.receiving import SqlInboundStockGateway
from app.modules.purchases.infrastructure.persistence.repositories import (
    SqlPurchaseRepository,
)
from app.shared.infrastructure.database import get_db


def get_purchase_repository(db: Session = Depends(get_db, scope="function")) -> SqlPurchaseRepository:
    return SqlPurchaseRepository(db)


def get_inbound_stock_gateway(db: Session = Depends(get_db, scope="function")) -> SqlInboundStockGateway:
    return SqlInboundStockGateway(db)
