"""Suppliers module — presentation DI providers."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.modules.suppliers.infrastructure.persistence.queries import SqlSupplierStatsReader
from app.modules.suppliers.infrastructure.persistence.repositories import (
    SqlSupplierRepository,
)
from app.shared.infrastructure.database import get_db


def get_supplier_repository(db: Session = Depends(get_db, scope="function")) -> SqlSupplierRepository:
    return SqlSupplierRepository(db)


def get_supplier_stats_reader(db: Session = Depends(get_db, scope="function")) -> SqlSupplierStatsReader:
    return SqlSupplierStatsReader(db)
