"""Suppliers module — read-side queries over the purchases table.

A supplier "document" (factura) is a group of purchase lines: lines registered together
share an import_batch_id; legacy lines without one group by (document_number, date).
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.products.infrastructure.persistence.models import ProductModel
from app.modules.purchases.infrastructure.persistence.models import PurchaseModel


def _doc_key(line: PurchaseModel) -> str:
    if line.import_batch_id:
        return str(line.import_batch_id)
    return f"{line.document_number}|{line.purchase_date.isoformat()}"


class SqlSupplierStatsReader:
    def __init__(self, session: Session) -> None:
        self._session = session

    def totals_by_supplier(self, company_id: UUID) -> dict[UUID, dict[str, Any]]:
        rows = self._session.execute(
            select(
                PurchaseModel.supplier_id,
                func.coalesce(func.sum(PurchaseModel.total_amount), 0),
                func.count(PurchaseModel.id),
                func.max(PurchaseModel.purchase_date),
            )
            .where(PurchaseModel.company_id == company_id)
            .group_by(PurchaseModel.supplier_id)
        ).all()
        return {
            sid: {"total_purchased": Decimal(total), "purchase_lines": int(n), "last_purchase_date": last}
            for sid, total, n, last in rows
        }

    def summary(self, company_id: UUID, supplier_id: UUID) -> dict[str, Any]:
        lines = self._session.execute(
            select(PurchaseModel)
            .where(PurchaseModel.company_id == company_id, PurchaseModel.supplier_id == supplier_id)
            .order_by(PurchaseModel.purchase_date.desc(), PurchaseModel.created_at.desc())
        ).scalars().all()

        product_ids = {line.product_id for line in lines}
        products = (
            {
                p.id: p
                for p in self._session.execute(
                    select(ProductModel).where(ProductModel.id.in_(product_ids))
                ).scalars()
            }
            if product_ids
            else {}
        )

        by_product: dict[UUID, dict[str, Any]] = defaultdict(
            lambda: {"total_quantity": 0, "total_amount": Decimal("0"), "last_cost": None, "last_purchase_date": None}
        )
        docs: set[str] = set()
        total = Decimal("0")
        for line in lines:  # newest first
            docs.add(_doc_key(line))
            total += Decimal(line.total_amount)
            agg = by_product[line.product_id]
            agg["total_quantity"] += line.quantity
            agg["total_amount"] += Decimal(line.total_amount)
            if agg["last_cost"] is None:
                agg["last_cost"] = Decimal(line.unit_cost)
                agg["last_purchase_date"] = line.purchase_date

        supplied = []
        for pid, agg in by_product.items():
            product = products.get(pid)
            qty = agg["total_quantity"]
            supplied.append(
                {
                    "product_id": pid,
                    "sku": product.sku if product else "",
                    "name": product.name if product else "Producto eliminado",
                    "total_quantity": qty,
                    "total_amount": agg["total_amount"],
                    "avg_unit_cost": (agg["total_amount"] / qty).quantize(Decimal("0.01")) if qty else Decimal("0"),
                    "last_cost": agg["last_cost"],
                    "last_purchase_date": agg["last_purchase_date"],
                }
            )
        supplied.sort(key=lambda r: r["total_amount"], reverse=True)

        recent = [
            {
                "id": line.id,
                "document_id": _doc_key(line) if line.import_batch_id else None,
                "document_number": line.document_number,
                "purchase_date": line.purchase_date,
                "product_id": line.product_id,
                "product_name": products[line.product_id].name if line.product_id in products else "Producto eliminado",
                "sku": products[line.product_id].sku if line.product_id in products else "",
                "quantity": line.quantity,
                "unit_cost": Decimal(line.unit_cost),
                "total_amount": Decimal(line.total_amount),
            }
            for line in lines[:25]
        ]

        return {
            "total_purchased": total,
            "purchases_count": len(lines),
            "documents_count": len(docs),
            "last_purchase_date": lines[0].purchase_date if lines else None,
            "products_count": len(supplied),
            "products": supplied,
            "recent_lines": recent,
        }
