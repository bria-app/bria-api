"""Purchases module — SQLAlchemy repository implementation (lines + documents)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.modules.products.infrastructure.persistence.models import ProductModel
from app.modules.purchases.domain.entities import Purchase
from app.modules.purchases.infrastructure.persistence.mappers import (
    purchase_to_entity,
    purchase_to_model,
)
from app.modules.purchases.infrastructure.persistence.models import PurchaseModel
from app.modules.suppliers.infrastructure.persistence.models import SupplierModel

# Document id: the batch uuid, or "<supplier_id>~<yyyy-mm-dd>~<document_number>" for
# legacy lines registered without a batch.
_LEGACY_SEP = "~"
# `||` (SQLAlchemy's .concat) instead of CONCAT(): it also runs on SQLite, used by the local
# stack and the tests. `||` propagates NULL, hence the coalesce on the optional number.
_DOC_KEY = func.coalesce(
    cast(PurchaseModel.import_batch_id, String),
    cast(PurchaseModel.supplier_id, String)
    .concat(literal(_LEGACY_SEP))
    .concat(cast(PurchaseModel.purchase_date, String))
    .concat(literal(_LEGACY_SEP))
    .concat(func.coalesce(PurchaseModel.document_number, "")),
)


def document_id_of(model: PurchaseModel) -> str:
    if model.import_batch_id:
        return str(model.import_batch_id)
    return _LEGACY_SEP.join([str(model.supplier_id), model.purchase_date.isoformat(), model.document_number or ""])


class SqlPurchaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, purchase_id: UUID) -> Purchase | None:
        model = self._session.get(PurchaseModel, purchase_id)
        return purchase_to_entity(model) if model else None

    def add(self, purchase: Purchase) -> Purchase:
        model = purchase_to_model(purchase)
        self._session.add(model)
        self._session.flush()
        return purchase_to_entity(model)

    # ─── reads ────────────────────────────────────────────────────────────

    def _filters(self, company_id: UUID, supplier_id: UUID | None, date_from: date | None, date_to: date | None) -> list[Any]:
        conds: list[Any] = [PurchaseModel.company_id == company_id]
        if supplier_id:
            conds.append(PurchaseModel.supplier_id == supplier_id)
        if date_from:
            conds.append(PurchaseModel.purchase_date >= date_from)
        if date_to:
            conds.append(PurchaseModel.purchase_date <= date_to)
        return conds

    def _line_rows(self, conds: list[Any], offset: int | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        stmt = (
            select(PurchaseModel, SupplierModel.business_name, SupplierModel.ruc, ProductModel.name, ProductModel.sku)
            .outerjoin(SupplierModel, SupplierModel.id == PurchaseModel.supplier_id)
            .outerjoin(ProductModel, ProductModel.id == PurchaseModel.product_id)
            .where(*conds)
            .order_by(PurchaseModel.purchase_date.desc(), PurchaseModel.created_at.desc())
        )
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        out = []
        for line, supplier_name, ruc, product_name, sku in self._session.execute(stmt).all():
            out.append(
                {
                    "id": line.id,
                    "company_id": line.company_id,
                    "supplier_id": line.supplier_id,
                    "supplier_name": supplier_name or "Proveedor eliminado",
                    "supplier_ruc": ruc or "",
                    "product_id": line.product_id,
                    "product_name": product_name or "Producto eliminado",
                    "sku": sku or "",
                    "purchase_date": line.purchase_date,
                    "quantity": line.quantity,
                    "unit_cost": Decimal(line.unit_cost),
                    "total_amount": Decimal(line.total_amount),
                    "currency": line.currency,
                    "document_number": line.document_number or "",
                    "notes": line.notes or "",
                    "import_batch_id": line.import_batch_id,
                    "document_id": document_id_of(line),
                    "created_at": line.created_at,
                    # business_name is NOT NULL: a missing name means the outer join found no supplier.
                    "supplier_deleted": supplier_name is None,
                }
            )
        return out

    def list_lines(
        self,
        company_id: UUID,
        *,
        supplier_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self._line_rows(self._filters(company_id, supplier_id, date_from, date_to), offset, limit)

    def list_documents(
        self,
        company_id: UUID,
        *,
        supplier_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        q: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        conds = self._filters(company_id, supplier_id, date_from, date_to)
        if q and q.strip():
            like = f"%{q.strip()}%"
            conds.append(or_(PurchaseModel.document_number.ilike(like), SupplierModel.business_name.ilike(like), SupplierModel.ruc.ilike(like)))

        doc_key = _DOC_KEY.label("document_id")
        grouped = (
            select(
                doc_key,
                PurchaseModel.supplier_id,
                PurchaseModel.document_number,
                PurchaseModel.purchase_date,
                func.max(SupplierModel.business_name).label("supplier_name"),
                func.max(SupplierModel.ruc).label("supplier_ruc"),
                func.max(PurchaseModel.notes).label("notes"),
                func.count(PurchaseModel.id).label("lines"),
                func.coalesce(func.sum(PurchaseModel.quantity), 0).label("units"),
                func.coalesce(func.sum(PurchaseModel.total_amount), 0).label("total"),
                func.max(PurchaseModel.created_at).label("created_at"),
            )
            .outerjoin(SupplierModel, SupplierModel.id == PurchaseModel.supplier_id)
            .where(*conds)
            .group_by(_DOC_KEY, PurchaseModel.supplier_id, PurchaseModel.document_number, PurchaseModel.purchase_date)
        )
        total = int(self._session.execute(select(func.count()).select_from(grouped.subquery())).scalar_one())
        rows = self._session.execute(
            grouped.order_by(PurchaseModel.purchase_date.desc(), func.max(PurchaseModel.created_at).desc())
            .offset(offset)
            .limit(limit)
        ).all()
        items = [
            {
                "document_id": r.document_id,
                "supplier_id": r.supplier_id,
                "supplier_name": r.supplier_name or "Proveedor eliminado",
                "supplier_ruc": r.supplier_ruc or "",
                "document_number": r.document_number or "",
                "purchase_date": r.purchase_date,
                "notes": r.notes or "",
                "lines": int(r.lines),
                "units": int(r.units),
                "total": Decimal(r.total),
                "created_at": r.created_at,
                "supplier_deleted": r.supplier_name is None,
            }
            for r in rows
        ]
        return items, total

    def get_document(self, company_id: UUID, document_id: str) -> dict[str, Any] | None:
        conds: list[Any] = [PurchaseModel.company_id == company_id]
        try:
            conds.append(PurchaseModel.import_batch_id == UUID(document_id))
        except ValueError:
            parts = document_id.split(_LEGACY_SEP, 2)
            if len(parts) != 3:
                return None
            try:
                supplier_id, day = UUID(parts[0]), date.fromisoformat(parts[1])
            except ValueError:
                return None
            conds += [
                PurchaseModel.import_batch_id.is_(None),
                PurchaseModel.supplier_id == supplier_id,
                PurchaseModel.purchase_date == day,
                PurchaseModel.document_number == parts[2],
            ]
        lines = self._line_rows(conds)
        if not lines:
            return None
        head = lines[-1]
        lines.reverse()  # registration order
        return {
            "document_id": document_id,
            "supplier_id": head["supplier_id"],
            "supplier_name": head["supplier_name"],
            "supplier_ruc": head["supplier_ruc"],
            "document_number": head["document_number"],
            "purchase_date": head["purchase_date"],
            "notes": next((line["notes"] for line in lines if line["notes"]), ""),
            "lines": lines,
            "units": sum(line["quantity"] for line in lines),
            "total": sum((line["total_amount"] for line in lines), Decimal("0")),
            "created_at": max(line["created_at"] for line in lines),
            "supplier_deleted": head["supplier_deleted"],
        }
