"""Sales module — bulk sales from a spreadsheet, in two modes.

* **History** (``affect_stock=False``): a business moving onto the ERP brings its past
  sales (an export of its old system or its Excel). They do NOT move stock — the current
  stock already reflects them (it comes from the inventory import).
* **Bulk sales** (``affect_stock=True``): day-to-day sales registered in bulk (another
  channel, a market day, an online store export). Each line also takes stock out at the
  weighted-average cost; a row that would leave the product below zero is rejected.

Either way the rows become real **tickets**: lines sharing a comprobante number
(B001-00004338, F001-00000139…) are grouped into one sales order with its client, payment
method and seller, and boletas/facturas get their comprobante record — so imported sales
show up in Ventas › Tickets, the dashboard, the product 360 view and the FTGM engine
exactly like sales rung up at the till. Rows without a comprobante become one ticket each.

Each row is matched to a product by code (SKU), then barcode, then exact name. Invalid
rows are reported and skipped; the rest is imported. Re-uploading the same file is
detected and refused, so sales never double.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.inventory.infrastructure.persistence.models import InventoryMovementModel
from app.modules.inventory.infrastructure.persistence.queries import stock_on_hand_map
from app.modules.invoicing.infrastructure.persistence.models import InvoiceModel
from app.modules.products.infrastructure.persistence.models import ProductModel
from app.modules.sales.infrastructure.persistence.models import SaleModel, SalesBatchModel, SalesOrderModel
from app.shared.domain.errors import ConflictError, ValidationError

LIMA = timezone(timedelta(hours=-5))
TWO = Decimal("0.01")
IGV = Decimal("1.18")
COMPROBANTE = re.compile(r"^\s*([BF][A-Z0-9]{3})\s*-\s*0*(\d{1,8})\s*$", re.IGNORECASE)
PAYMENTS = {
    "efectivo": "efectivo", "cash": "efectivo", "contado": "efectivo",
    "tarjeta": "tarjeta", "credito": "tarjeta", "debito": "tarjeta", "pos": "tarjeta", "visa": "tarjeta",
    "yape": "yape", "plin": "plin",
    "transferencia": "transferencia", "deposito": "transferencia", "banco": "transferencia",
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _plain(value: Any) -> str:
    return unicodedata.normalize("NFKD", _norm(value)).encode("ascii", "ignore").decode()


def _payment(value: Any) -> str:
    text = _plain(value)
    for key, method in PAYMENTS.items():
        if key in text:
            return method
    return "efectivo"


def _client_doc(value: Any) -> tuple[str, str]:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11:
        return "ruc", digits
    if len(digits) == 8:
        return "dni", digits
    return "none", ""


@dataclass
class _Line:
    row: int
    product: ProductModel
    sale_date: date
    qty: int
    price: Decimal
    seller: str
    document: str
    payment: str
    client_name: str
    client_doc: str


def import_sales_history(
    session: Session,
    company_id: UUID,
    rows: list[dict[str, Any]],
    *,
    allow_duplicates: bool = False,
    affect_stock: bool = False,
) -> dict[str, Any]:
    if not rows:
        raise ValidationError(message="El archivo no tiene filas de ventas.")

    products = session.execute(
        select(ProductModel).where(ProductModel.company_id == company_id)
    ).scalars().all()
    by_sku = {_norm(p.sku): p for p in products}
    by_barcode = {_norm(p.barcode): p for p in products if p.barcode}
    by_name = {_norm(p.name): p for p in products}

    today = datetime.now(LIMA).date()
    errors: list[dict[str, Any]] = []
    valid: list[_Line] = []

    for i, row in enumerate(rows, start=1):
        n = int(row.get("row") or i)
        code, barcode, name = _norm(row.get("code")), _norm(row.get("barcode")), _norm(row.get("name"))
        product = (
            (by_sku.get(code) if code else None)
            or (by_barcode.get(code) if code else None)
            or (by_barcode.get(barcode) if barcode else None)
            or (by_name.get(name) if name else None)
        )
        if product is None:
            label = row.get("code") or row.get("barcode") or row.get("name") or "sin identificar"
            errors.append({"row": n, "message": f"Producto «{label}» no existe en tu inventario. Impórtalo primero."})
            continue

        try:
            sale_date = date.fromisoformat(str(row.get("sale_date") or "")[:10])
        except ValueError:
            errors.append({"row": n, "message": "Fecha inválida o vacía."})
            continue
        if sale_date > today:
            errors.append({"row": n, "message": f"La fecha {sale_date:%d/%m/%Y} está en el futuro."})
            continue

        try:
            qty_dec = Decimal(str(row.get("quantity")))
        except Exception:  # noqa: BLE001
            errors.append({"row": n, "message": "Cantidad inválida."})
            continue
        if qty_dec <= 0 or qty_dec != qty_dec.to_integral_value():
            errors.append({"row": n, "message": "La cantidad debe ser un entero mayor que 0."})
            continue

        raw_price = row.get("unit_price")
        try:
            price = (Decimal(str(raw_price)) if raw_price not in (None, "") else Decimal(product.unit_price)).quantize(
                TWO, rounding=ROUND_HALF_UP
            )
        except Exception:  # noqa: BLE001
            errors.append({"row": n, "message": "Precio unitario inválido."})
            continue
        if price < 0:
            errors.append({"row": n, "message": "El precio no puede ser negativo."})
            continue

        valid.append(_Line(
            row=n, product=product, sale_date=sale_date, qty=int(qty_dec), price=price,
            seller=str(row.get("seller_name") or "").strip()[:255],
            document=str(row.get("document_number") or "").strip().upper()[:40],
            payment=_payment(row.get("payment_method")),
            client_name=str(row.get("client_name") or "").strip()[:255],
            client_doc=str(row.get("client_doc") or "").strip(),
        ))

    # Old sales must never discount stock: the current stock already reflects them, so
    # discounting again would empty the inventory and reject most rows on the way.
    if affect_stock and valid:
        old_rows = sum(1 for v in valid if (today - v.sale_date).days > 60)
        if old_rows > len(valid) / 2:
            raise ValidationError(
                message="La mayoría de estas ventas tienen más de 2 meses. Impórtalas como ventas pasadas "
                "(con «Descontar del stock» apagado): tu stock actual ya las refleja, y si las descuentas "
                "de nuevo te quedarías sin stock en el sistema."
            )

    # Bulk sales take real stock out: walk the rows in date order and refuse any line
    # that asks for more units than are left at that point.
    if affect_stock and valid:
        on_hand = stock_on_hand_map(session, company_id)
        accepted: list[_Line] = []
        for line in sorted(valid, key=lambda v: (v.sale_date, v.row)):
            available = on_hand.get(line.product.id, 0)
            if line.qty > available:
                errors.append({
                    "row": line.row,
                    "message": f"Stock insuficiente de «{line.product.name}»: pediste {line.qty}, quedan {max(available, 0)}.",
                })
                continue
            on_hand[line.product.id] = available - line.qty
            accepted.append(line)
        valid = accepted

    errors.sort(key=lambda e: e["row"])
    empty = {"batch_id": None, "created": 0, "tickets": 0, "units": 0, "revenue": Decimal("0"),
             "period_start": None, "period_end": None, "products": 0, "errors": errors}
    if not valid:
        return empty

    start = min(v.sale_date for v in valid)
    end = max(v.sale_date for v in valid)

    # Same file uploaded twice? Compare against sales loaded by earlier imports.
    if not allow_duplicates:
        existing = Counter(
            (pid, d, q, Decimal(pr).quantize(TWO))
            for pid, d, q, pr in session.execute(
                select(SaleModel.product_id, SaleModel.sale_date, SaleModel.quantity, SaleModel.unit_price).where(
                    SaleModel.company_id == company_id,
                    SaleModel.batch_id.is_not(None),
                    SaleModel.sale_date >= start,
                    SaleModel.sale_date <= end,
                )
            ).all()
        )
        incoming = Counter((v.product.id, v.sale_date, v.qty, v.price) for v in valid)
        repeated = sum(min(c, existing[k]) for k, c in incoming.items())
        if repeated >= max(1, int(len(valid) * 0.9)):
            raise ConflictError(
                message="Estas ventas ya fueron cargadas antes (mismas fechas, productos, cantidades y precios). "
                "No se volvieron a cargar para no duplicarlas."
            )

    label = "Carga masiva de ventas" if affect_stock else "Importación de ventas"
    batch = SalesBatchModel(
        id=uuid4(),
        company_id=company_id,
        source_file=f"{label} {datetime.now(LIMA):%d/%m/%Y %H:%M}",
        status="completed",
        row_count=len(valid),
        period_start=start,
        period_end=end,
    )
    session.add(batch)

    # ---- group lines into tickets (by comprobante; rows without one are a ticket each)
    groups: dict[str, list[_Line]] = {}
    for line in sorted(valid, key=lambda v: (v.sale_date, v.document or "~", v.row)):
        key = f"doc:{line.document}" if line.document else f"row:{line.row}"
        groups.setdefault(key, []).append(line)

    next_number = (
        session.execute(
            select(func.coalesce(func.max(SalesOrderModel.order_number), 0)).where(
                SalesOrderModel.company_id == company_id
            )
        ).scalar_one()
        + 1
    )
    taken_invoices = {
        (s, c)
        for s, c in session.execute(
            select(InvoiceModel.series, InvoiceModel.correlativo).where(InvoiceModel.company_id == company_id)
        ).all()
    }

    units = 0
    revenue = Decimal("0")
    for lines in groups.values():
        head = lines[0]
        sold_at = datetime.combine(head.sale_date, time(12, 0), LIMA)
        match = COMPROBANTE.match(head.document) if head.document else None
        doc_type = "nota_venta"
        series = correlativo = None
        if match:
            series, correlativo = match.group(1).upper(), int(match.group(2))
            doc_type = "factura" if series.startswith("F") else "boleta"
        client_doc_type, client_doc_number = _client_doc(head.client_doc)
        client_name = head.client_name or ("Clientes varios" if doc_type != "factura" else "")

        total = sum(((ln.price * ln.qty).quantize(TWO, rounding=ROUND_HALF_UP) for ln in lines), Decimal("0"))
        subtotal = (total / IGV).quantize(TWO, rounding=ROUND_HALF_UP)
        order_id = uuid4()

        invoice_id = None
        if series and correlativo is not None and (series, correlativo) not in taken_invoices:
            taken_invoices.add((series, correlativo))
            invoice_id = uuid4()
            session.add(InvoiceModel(
                id=invoice_id,
                company_id=company_id,
                document_type=doc_type,
                series=series,
                correlativo=correlativo,
                client_doc_type=client_doc_type,
                client_doc_number=client_doc_number,
                client_name=client_name or "Público en general",
                client_address="",
                items=[{
                    "description": ln.product.name,
                    "quantity": ln.qty,
                    "unit_price": str(ln.price),
                    "discount": "0",
                    "product_id": str(ln.product.id),
                } for ln in lines],
                subtotal=subtotal,
                igv=total - subtotal,
                total=total,
                currency=head.product.currency or "PEN",
                status="emitida",
                issued_at=sold_at,
                sale_id=order_id,
            ))

        session.add(SalesOrderModel(
            id=order_id,
            company_id=company_id,
            order_number=next_number,
            seller_id=None,
            seller_name=head.seller,
            document_type=doc_type if invoice_id or doc_type == "nota_venta" else "nota_venta",
            client_doc_type=client_doc_type,
            client_doc_number=client_doc_number,
            client_name=client_name,
            client_address="",
            payment_method=head.payment,
            amount_received=None,
            discount_total=Decimal("0"),
            subtotal=subtotal,
            igv=total - subtotal,
            total=total,
            currency=head.product.currency or "PEN",
            status="completed",
            invoice_id=invoice_id,
            notes=label,
            sold_at=sold_at,
        ))
        next_number += 1

        for ln in lines:
            line_total = (ln.price * ln.qty).quantize(TWO, rounding=ROUND_HALF_UP)
            session.add(SaleModel(
                company_id=company_id,
                product_id=ln.product.id,
                batch_id=batch.id,
                order_id=order_id,
                sale_date=ln.sale_date,
                quantity=ln.qty,
                unit_price=ln.price,
                total_amount=line_total,
                currency=ln.product.currency or "PEN",
                seller_name=ln.seller,
                unit_cost=ln.product.unit_cost,
            ))
            if affect_stock:
                session.add(InventoryMovementModel(
                    company_id=company_id,
                    product_id=ln.product.id,
                    movement_type="outbound",
                    quantity=ln.qty,
                    reason="Venta (carga masiva)",
                    occurred_at=sold_at,
                    unit_cost=ln.product.unit_cost,
                    reference_type="sale",
                    reference_id=order_id,
                ))
            units += ln.qty
            revenue += line_total
    session.flush()

    return {
        "batch_id": batch.id,
        "created": len(valid),
        "tickets": len(groups),
        "units": units,
        "revenue": revenue,
        "period_start": start,
        "period_end": end,
        "products": len({v.product.id for v in valid}),
        "errors": errors,
    }
