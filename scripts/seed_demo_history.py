"""Seed realistic ERP history for the PetHouse demo so the FTGM engine has data.

Run inside the api container (idempotent — re-running replaces the seeded rows):

    docker compose exec -T api python scripts/seed_demo_history.py [--company-email demo@pethouse.pe]

What it generates (everything tagged so it can be removed and regenerated):

* daily sales from the day after the latest non-seed sale (or 26 months ago) up to
  yesterday, for products that already sell — continuing their observed level and
  seasonal profile with a mild trend, weekday effect and Poisson noise;
* a few catalog products without sales get a shorter history (~10 months → weekly) and a
  couple get sporadic sales (intermittent demand → Croston);
* a stock simulation per product: an opening balance, periodic purchases from 3
  suppliers (2 created with valid RUCs if missing) with inbound movements, one outbound
  movement per sale, and occasional late deliveries that cause real stock-outs with
  ``lost_sales`` rows at the till;
* POS tickets (``sales_orders``) grouping the last 60 days of seeded lines, assigned to
  the company's users (sellers when they exist).

Tags: sales/lost-sales via the "seed_demo_history" sales batch / source="seed";
purchases via notes="seed_demo_history"; movements via reason suffix "(seed)";
orders via notes="seed_demo_history".
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, or_, select  # noqa: E402

import app.bootstrap.routers  # noqa: E402,F401  (registers every ORM model)
from app.modules.companies.infrastructure.persistence.models import CompanyModel, UserModel  # noqa: E402
from app.modules.inventory.infrastructure.persistence.models import InventoryMovementModel  # noqa: E402
from app.modules.products.infrastructure.persistence.models import ProductModel  # noqa: E402
from app.modules.purchases.infrastructure.persistence.models import PurchaseModel  # noqa: E402
from app.modules.sales.infrastructure.persistence.models import (  # noqa: E402
    LostSaleModel,
    SaleModel,
    SalesBatchModel,
    SalesOrderModel,
)
from app.modules.suppliers.domain.ruc import ruc_check_digit  # noqa: E402
from app.modules.suppliers.infrastructure.persistence.models import SupplierModel  # noqa: E402
from app.shared.infrastructure.database import SessionLocal  # noqa: E402

TAG = "seed_demo_history"
LIMA = timezone(timedelta(hours=-5))
IGV = Decimal("0.18")
TWO = Decimal("0.01")

SUPPLIERS = [
    ("2060123456", "Importaciones Mascotas del Perú S.A.C.", "Jorge Salazar", "ventas@mascotasperu.pe"),
    ("2055566677", "Distribuidora Veterinaria Lima E.I.R.L.", "Lucía Ramos", "pedidos@vetlima.pe"),
]
WEEKDAY = [0.85, 0.9, 0.95, 1.0, 1.15, 1.35, 1.1]  # Mon..Sun


def money(v: float | Decimal) -> Decimal:
    return Decimal(str(v)).quantize(TWO, rounding=ROUND_HALF_UP)


def valid_ruc(first_ten: str) -> str:
    return first_ten + str(ruc_check_digit(first_ten))


def at_lima(d: date, hour: int = 12) -> datetime:
    return datetime.combine(d, time(hour, 0), tzinfo=LIMA)


def clean(session, company_id: UUID, batch_id: UUID | None) -> None:
    if batch_id is not None:
        session.execute(delete(SaleModel).where(SaleModel.company_id == company_id, SaleModel.batch_id == batch_id))
    session.execute(delete(SalesOrderModel).where(SalesOrderModel.company_id == company_id, SalesOrderModel.notes == TAG))
    session.execute(delete(LostSaleModel).where(LostSaleModel.company_id == company_id, LostSaleModel.source == "seed"))
    session.execute(delete(PurchaseModel).where(PurchaseModel.company_id == company_id, PurchaseModel.notes == TAG))
    session.execute(
        delete(InventoryMovementModel).where(
            InventoryMovementModel.company_id == company_id, InventoryMovementModel.reason.like("%(seed)")
        )
    )
    session.flush()


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    threshold, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-email", default="demo@pethouse.pe")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    session = SessionLocal()
    try:
        owner = session.execute(select(UserModel).where(UserModel.email == args.company_email)).scalar_one_or_none()
        if owner is None:
            sys.exit(f"No user with email {args.company_email}")
        company_id = owner.company_id
        company = session.get(CompanyModel, company_id)
        today = datetime.now(LIMA).date()
        end = today - timedelta(days=1)  # through yesterday

        batch = session.execute(
            select(SalesBatchModel).where(SalesBatchModel.company_id == company_id, SalesBatchModel.source_file == TAG)
        ).scalar_one_or_none()
        clean(session, company_id, batch.id if batch else None)
        if batch is None:
            batch = SalesBatchModel(company_id=company_id, source_file=TAG, status="completed", row_count=0)
            session.add(batch)
            session.flush()

        # ---------------------------------------------------------------- suppliers
        suppliers = list(
            session.execute(select(SupplierModel).where(SupplierModel.company_id == company_id)).scalars().all()
        )
        existing_rucs = {s.ruc for s in suppliers}
        for first_ten, name, contact, email in SUPPLIERS:
            if len(suppliers) >= 3:
                break
            ruc = valid_ruc(first_ten)
            if ruc in existing_rucs:
                continue
            sup = SupplierModel(
                company_id=company_id, ruc=ruc, business_name=name, contact_name=contact, email=email,
                phone="01 " + str(rng.randint(4000000, 7999999)), address="Lima, Perú", custom_attributes={},
            )
            session.add(sup)
            suppliers.append(sup)
        session.flush()

        # ---------------------------------------------------------------- products + base levels
        products = list(
            session.execute(
                select(ProductModel)
                .where(ProductModel.company_id == company_id, ProductModel.is_active.is_(True))
                .order_by(ProductModel.sku)
            ).scalars().all()
        )
        if not products:
            sys.exit("Company has no active products")

        monthly = defaultdict(lambda: defaultdict(int))  # pid -> (y, m) -> units
        last_sale: dict[UUID, date] = {}
        for pid, d, qty in session.execute(
            select(SaleModel.product_id, SaleModel.sale_date, SaleModel.quantity).where(
                SaleModel.company_id == company_id,
                or_(SaleModel.batch_id.is_(None), SaleModel.batch_id != batch.id),
                SaleModel.order_id.is_(None),  # legacy/imported history only; keep POS tickets aside
            )
        ).all():
            monthly[pid][(d.year, d.month)] += qty
            last_sale[pid] = max(last_sale.get(pid, d), d)

        users = list(
            session.execute(
                select(UserModel).where(UserModel.company_id == company_id, UserModel.status != "deleted")
            ).scalars().all()
        )
        sellers = [u for u in users if u.role == "seller"] or users

        default_start = date(today.year - 2, today.month, 1) - timedelta(days=62)
        plans = []
        no_sales = [p for p in products if p.id not in monthly]
        for p in products:
            hist = monthly.get(p.id)
            if hist:
                # Level = mean of the last 12 observed months; seasonal index per month.
                keys = sorted(hist)
                recent = [hist[k] for k in keys[-12:]]
                level = max(1.0, sum(recent) / len(recent))
                by_month = defaultdict(list)
                for (y, m), u in hist.items():
                    by_month[m].append(u)
                overall = sum(hist.values()) / len(hist)
                season = {m: (sum(v) / len(v)) / overall if overall else 1.0 for m, v in by_month.items()}
                start = max(last_sale[p.id] + timedelta(days=1), default_start)
                plans.append((p, start, level, season, "regular"))
        for i, p in enumerate(no_sales):
            if i < 4:  # ~10 months of history -> weekly frequency in auto mode
                level = rng.choice([35, 50, 70, 90])
                season = {m: 1.0 + 0.2 * math.sin(2 * math.pi * (m - 3) / 12) for m in range(1, 13)}
                plans.append((p, today - timedelta(days=305), float(level), season, "regular"))
            elif i < 6:  # sporadic -> intermittent demand
                plans.append((p, today - timedelta(days=700), 1.5, {m: 1.0 for m in range(1, 13)}, "intermittent"))

        # ---------------------------------------------------------------- simulate
        sale_rows: list[SaleModel] = []
        move_rows: list[InventoryMovementModel] = []
        purchase_rows: list[PurchaseModel] = []
        lost_rows: list[LostSaleModel] = []
        doc_counter = 1000
        for idx, (p, start, level, season, kind) in enumerate(plans):
            if start > end:
                continue
            supplier = suppliers[idx % len(suppliers)] if suppliers else None
            unit_cost = p.unit_cost if p.unit_cost and p.unit_cost > 0 else money(float(p.unit_price) * 0.55)
            daily_base = level / 30.4
            trend_per_day = rng.choice([0.0002, 0.0004, -0.0001, 0.0006])
            lead = max(2, p.lead_time_days or 5)
            order_qty = max(6, int(round(level * rng.choice([1.2, 1.5, 1.8]))))
            reorder_level = max(p.reorder_point or 0, int(round(daily_base * (lead + 7))))
            stock = int(round(level * 1.2)) + 5
            move_rows.append(
                InventoryMovementModel(
                    company_id=company_id, product_id=p.id, movement_type="inbound", quantity=stock,
                    reason="Stock inicial (seed)", occurred_at=at_lima(start, 7), unit_cost=unit_cost,
                    reference_type="adjustment",
                )
            )
            pending_arrival: date | None = None
            days = (end - start).days + 1
            for n in range(days):
                d = start + timedelta(days=n)
                if pending_arrival is not None and d >= pending_arrival:
                    qty = order_qty
                    cost = money(float(unit_cost) * rng.uniform(0.96, 1.05))
                    doc_counter += 1
                    doc = f"F001-{doc_counter:06d}"
                    ref = uuid4()
                    if supplier is not None:
                        purchase_rows.append(
                            PurchaseModel(
                                id=ref, company_id=company_id, supplier_id=supplier.id, product_id=p.id,
                                purchase_date=d, quantity=qty, unit_cost=cost, total_amount=money(cost * qty),
                                document_number=doc, notes=TAG,
                            )
                        )
                    move_rows.append(
                        InventoryMovementModel(
                            company_id=company_id, product_id=p.id, movement_type="inbound", quantity=qty,
                            reason=f"Compra {doc} (seed)", occurred_at=at_lima(d, 8), unit_cost=cost,
                            reference_type="purchase", reference_id=ref,
                        )
                    )
                    stock += qty
                    pending_arrival = None

                if kind == "intermittent":
                    demand = rng.choice([1, 1, 2, 3]) if rng.random() < 0.045 else 0
                else:
                    lam = daily_base * season.get(d.month, 1.0) * WEEKDAY[d.weekday()] * (1 + trend_per_day * n)
                    if rng.random() < 0.004:  # rare bulk order (outlier)
                        lam *= 5
                    demand = poisson(rng, lam)

                sold = min(demand, max(stock, 0))
                if sold > 0:
                    price = p.unit_price
                    sale_rows.append(
                        SaleModel(
                            company_id=company_id, product_id=p.id, batch_id=batch.id, sale_date=d, quantity=sold,
                            unit_price=price, total_amount=money(price * sold), currency=p.currency or "PEN",
                            unit_cost=unit_cost,
                        )
                    )
                    move_rows.append(
                        InventoryMovementModel(
                            company_id=company_id, product_id=p.id, movement_type="outbound", quantity=sold,
                            reason="Venta (seed)", occurred_at=at_lima(d, 18), unit_cost=unit_cost,
                            reference_type="sale",
                        )
                    )
                    stock -= sold
                if demand > sold:
                    attempts = 1 if demand - sold <= 3 else 2
                    seller = rng.choice(sellers) if sellers else None
                    for _ in range(attempts):
                        lost_rows.append(
                            LostSaleModel(
                                company_id=company_id, product_id=p.id,
                                requested_quantity=max(1, (demand - sold) // attempts), available_quantity=max(stock, 0),
                                seller_id=seller.id if seller else None,
                                seller_name=(seller.full_name if seller else ""), source="seed",
                                occurred_at=at_lima(d, rng.randint(10, 20)),
                            )
                        )

                if kind != "intermittent" and pending_arrival is None and stock <= reorder_level:
                    delay = lead
                    if rng.random() < 0.12:  # late supplier -> stock-out gap
                        delay += rng.randint(8, 20)
                    pending_arrival = d + timedelta(days=delay)
                elif kind == "intermittent" and pending_arrival is None and stock <= 1:
                    pending_arrival = d + timedelta(days=lead + 10)

        session.add_all(sale_rows)
        session.add_all(move_rows)
        session.add_all(purchase_rows)
        session.add_all(lost_rows)
        session.flush()

        # ---------------------------------------------------------------- POS tickets (last 60 days)
        next_number = int(
            session.execute(
                select(func.coalesce(func.max(SalesOrderModel.order_number), 0)).where(
                    SalesOrderModel.company_id == company_id
                )
            ).scalar_one()
        ) + 1
        recent = sorted((s for s in sale_rows if s.sale_date >= today - timedelta(days=60)), key=lambda s: s.sale_date)
        by_day = defaultdict(list)
        for s in recent:
            by_day[s.sale_date].append(s)
        orders = 0
        for d, lines in sorted(by_day.items()):
            rng.shuffle(lines)
            i = 0
            while i < len(lines):
                size = rng.choice([1, 1, 2, 2, 3])
                chunk = lines[i : i + size]
                i += size
                total = sum((s.total_amount for s in chunk), Decimal("0"))
                subtotal = money(total / (1 + IGV))
                seller = rng.choice(sellers) if sellers else None
                order = SalesOrderModel(
                    id=uuid4(), company_id=company_id, order_number=next_number,
                    seller_id=seller.id if seller else None, seller_name=seller.full_name if seller else "",
                    document_type="boleta", payment_method=rng.choice(["efectivo", "tarjeta", "yape"]),
                    subtotal=subtotal, igv=money(total - subtotal), total=money(total), currency="PEN",
                    status="completed", notes=TAG, sold_at=at_lima(d, rng.randint(9, 20)),
                )
                next_number += 1
                orders += 1
                session.add(order)
                for s in chunk:
                    s.order_id = order.id
                    s.seller_id = order.seller_id
                    s.seller_name = order.seller_name
        # Older seeded lines still get a seller so the "por vendedor" scope has data.
        for s in sale_rows:
            if s.seller_id is None and sellers:
                seller = sellers[hash((s.product_id, s.sale_date)) % len(sellers)]
                s.seller_id, s.seller_name = seller.id, seller.full_name

        batch.row_count = len(sale_rows)
        batch.period_start = min((s.sale_date for s in sale_rows), default=None)
        batch.period_end = max((s.sale_date for s in sale_rows), default=None)
        session.commit()
        print(
            f"[{company.name if company else company_id}] seeded: {len(plans)} products, {len(sale_rows)} sales lines, "
            f"{orders} tickets, {len(purchase_rows)} purchases, {len(move_rows)} movements, {len(lost_rows)} lost sales, "
            f"suppliers={len(suppliers)}"
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
