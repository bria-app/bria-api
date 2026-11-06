"""Products module — presentation DI providers."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.products.infrastructure.adapters.stock import (
    SqlProductCodeGenerator,
    SqlProductStockGateway,
    SqlUnitOfWork,
)
from app.modules.products.infrastructure.adapters.custom_attributes import (
    SqlCustomAttributeCaster,
    SqlProductAlertSource,
)
from app.modules.products.infrastructure.adapters.history import SqlProductHistory
from app.modules.products.infrastructure.persistence.repositories import (
    SqlCategoryRepository,
    SqlProductRepository,
)
from app.modules.products.infrastructure.persistence.timeline import SqlProductTimelineQuery
from app.shared.infrastructure.database import get_db


def get_product_repository(db: Session = Depends(get_db, scope="function")) -> SqlProductRepository:
    return SqlProductRepository(db)


def get_category_repository(db: Session = Depends(get_db, scope="function")) -> SqlCategoryRepository:
    return SqlCategoryRepository(db)


def get_code_generator(db: Session = Depends(get_db, scope="function")) -> SqlProductCodeGenerator:
    return SqlProductCodeGenerator(db)


def get_stock_gateway(db: Session = Depends(get_db, scope="function")) -> SqlProductStockGateway:
    return SqlProductStockGateway(db)


def get_unit_of_work(db: Session = Depends(get_db, scope="function")) -> SqlUnitOfWork:
    return SqlUnitOfWork(db)


def get_timeline_query(db: Session = Depends(get_db, scope="function")) -> SqlProductTimelineQuery:
    return SqlProductTimelineQuery(db)


def get_product_history(db: Session = Depends(get_db, scope="function")) -> SqlProductHistory:
    return SqlProductHistory(db)


def get_attribute_caster(db: Session = Depends(get_db, scope="function")) -> SqlCustomAttributeCaster:
    return SqlCustomAttributeCaster(db)


def get_alert_source(db: Session = Depends(get_db, scope="function")) -> SqlProductAlertSource:
    return SqlProductAlertSource(db)
