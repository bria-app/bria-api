"""Sales module — presentation DI providers.

Every provider depends on the same request-scoped session, so a POS checkout
(ticket, lines, movements, comprobante) commits or rolls back as one unit.
"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.companies.infrastructure.persistence.repositories import SqlUserRepository
from app.modules.sales.infrastructure.adapters.catalog import SqlProductCatalog
from app.modules.sales.infrastructure.adapters.invoicing import InvoicingModuleIssuer
from app.modules.sales.infrastructure.adapters.stock import SqlStockLedger
from app.modules.sales.infrastructure.persistence.queries import SqlSalesOrderReadModel
from app.modules.sales.infrastructure.persistence.repositories import (
    SqlLostSaleRepository,
    SqlSaleRepository,
    SqlSalesBatchRepository,
    SqlSalesOrderRepository,
)
from app.shared.infrastructure.database import get_db


def get_sale_repository(db: Session = Depends(get_db, scope="function")) -> SqlSaleRepository:
    return SqlSaleRepository(db)


def get_sales_batch_repository(db: Session = Depends(get_db, scope="function")) -> SqlSalesBatchRepository:
    return SqlSalesBatchRepository(db)


def get_sales_order_repository(db: Session = Depends(get_db, scope="function")) -> SqlSalesOrderRepository:
    return SqlSalesOrderRepository(db)


def get_sales_order_read_model(db: Session = Depends(get_db, scope="function")) -> SqlSalesOrderReadModel:
    return SqlSalesOrderReadModel(db)


def get_lost_sale_repository(db: Session = Depends(get_db, scope="function")) -> SqlLostSaleRepository:
    return SqlLostSaleRepository(db)


def get_product_catalog(db: Session = Depends(get_db, scope="function")) -> SqlProductCatalog:
    return SqlProductCatalog(db)


def get_stock_ledger(db: Session = Depends(get_db, scope="function")) -> SqlStockLedger:
    return SqlStockLedger(db)


def get_invoice_issuer(db: Session = Depends(get_db, scope="function")) -> InvoicingModuleIssuer:
    return InvoicingModuleIssuer(db)


def get_seller_directory(db: Session = Depends(get_db, scope="function")) -> SqlUserRepository:
    return SqlUserRepository(db)
