"""Bootstrap the PetHouse demo on an EMPTY database (e.g. a fresh Railway Postgres).

Creates, only if missing:

* company "PetHouse Lima" with its owner (demo@pethouse.pe) and a seller (lramos), on an
  active Premium subscription. Passwords come from DEMO_OWNER_PASSWORD and
  DEMO_SELLER_PASSWORD; without both variables nothing is seeded (a clear message is
  printed), in any environment. The demo credentials are never in the code;
* a Perros/Gatos category tree and the 12-product catalog (SKU-001..012) with valid
  EAN-13 barcodes, so the till's scanner can be tried;
* legacy daily sales for 2022-01..2024-12 (the history the original CSV import had),
  so every product has 3+ years of seasonal demand for the FTGM engine;

then runs ``seed_demo_history`` to continue from 2025 to yesterday (POS tickets, purchases
from suppliers, stock movements and stock-outs).

Idempotent: once the demo history exists it does nothing, so it is safe to run on every
boot. It only runs when SEED_DEMO=true (the API Dockerfile calls it after migrations):

    SEED_DEMO=true DEMO_OWNER_PASSWORD=... DEMO_SELLER_PASSWORD=... python scripts/bootstrap_demo.py

Passwords only apply when the users are created; to rotate them later change them in
the app (or remove the users) — re-running the seed does not overwrite them.
"""
from __future__ import annotations

import math
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sqlalchemy import select  # noqa: E402

import app.bootstrap.routers  # noqa: E402,F401  (registers every ORM model)
from app.config import settings  # noqa: E402
from app.modules.billing.infrastructure.persistence.models import SubscriptionModel  # noqa: E402
from app.modules.companies.infrastructure.persistence.models import CompanyModel, UserModel  # noqa: E402
from app.modules.products.infrastructure.persistence.models import CategoryModel, ProductModel  # noqa: E402
from app.modules.sales.infrastructure.persistence.models import SaleModel, SalesBatchModel  # noqa: E402
from app.shared.infrastructure.database import SessionLocal  # noqa: E402
from app.shared.infrastructure.security.hashing import hash_password  # noqa: E402

OWNER_EMAIL = "demo@pethouse.pe"
SELLER_USERNAME = "lramos"
LEGACY_FILE = "ventas_historicas_2022_2024.csv"
SEED_TAG = "seed_demo_history"  # same tag seed_demo_history.py uses for its batch

CATEGORY_TREE = {
    "Perros": ["Alimento", "Higiene", "Salud", "Accesorios"],
    "Gatos": ["Alimento", "Higiene", "Salud", "Juguetes"],
}

# sku, name, cost, price, safety, reorder, lead_time, (brand, type), monthly units today
CATALOG = [
    ("SKU-001", "Alimento Premium Perro 15kg", "85.00", "129.90", 10, 25, 7, ("Perros", "Alimento"), 270),
    ("SKU-002", "Alimento Premium Gato 3kg", "28.00", "45.90", 15, 35, 7, ("Gatos", "Alimento"), 370),
    ("SKU-003", "Snack Natural Pollo Perro 200g", "8.50", "14.90", 20, 50, 5, ("Perros", "Alimento"), 580),
    ("SKU-004", "Shampoo Medicado Perro 500ml", "12.00", "22.90", 12, 28, 7, ("Perros", "Higiene"), 170),
    ("SKU-005", "Toallitas Húmedas Cachorros x50", "6.50", "12.50", 18, 40, 5, ("Perros", "Higiene"), 250),
    ("SKU-006", "Arena para Gatos Aglomerante 5kg", "14.00", "24.90", 14, 30, 7, ("Gatos", "Higiene"), 220),
    ("SKU-007", "Antiparasitario Externo Perro", "18.00", "34.90", 8, 20, 10, ("Perros", "Salud"), 90),
    ("SKU-008", "Vitaminas Articulaciones Perro Senior", "32.00", "59.90", 6, 15, 10, ("Perros", "Salud"), 57),
    ("SKU-009", "Suplemento Omega 3 Gatos 100ml", "22.00", "42.90", 7, 18, 10, ("Gatos", "Salud"), 64),
    ("SKU-010", "Correa Retráctil 5m Perros Medianos", "28.00", "52.90", 5, 12, 14, ("Perros", "Accesorios"), 79),
    ("SKU-011", "Cama Ortopédica Perro Mediano", "55.00", "99.90", 4, 10, 14, ("Perros", "Accesorios"), 28),
    ("SKU-012", "Juguete Interactivo Dispensador Gato", "15.00", "28.90", 8, 20, 10, ("Gatos", "Juguetes"), 190),
]

# Retail pet-shop seasonality (Dec gifts + campaigns; slow Feb).
SEASON = {1: 0.92, 2: 0.85, 3: 0.95, 4: 0.97, 5: 1.02, 6: 1.0, 7: 1.08, 8: 0.98, 9: 0.96, 10: 1.0, 11: 1.07, 12: 1.30}
WEEKDAY = [0.85, 0.9, 0.95, 1.0, 1.15, 1.35, 1.1]  # Mon..Sun


def ean13(body12: str) -> str:
    """Append the EAN-13 check digit to a 12-digit body."""
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body12))
    return body12 + str((10 - total % 10) % 10)


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:  # normal approximation keeps it fast for high-volume items
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    threshold, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


def enabled() -> bool:
    return os.getenv("SEED_DEMO", "").strip().lower() in {"1", "true", "yes", "on"}


def demo_passwords() -> tuple[str, str] | None:
    """(owner, seller) passwords for the demo users, or None when seeding must be skipped.

    Both env vars set -> use them. There are no default passwords in the code (audit C-03).
    """
    owner = os.getenv("DEMO_OWNER_PASSWORD", "").strip()
    seller = os.getenv("DEMO_SELLER_PASSWORD", "").strip()
    if owner and seller:
        return owner, seller
    return None


def bootstrap(owner_password: str, seller_password: str) -> bool:
    """Create the demo master data + legacy history. Returns False when already seeded."""
    session = SessionLocal()
    try:
        owner = session.execute(select(UserModel).where(UserModel.email == OWNER_EMAIL)).scalar_one_or_none()
        if owner is not None:
            seeded = session.execute(
                select(SalesBatchModel.id).where(
                    SalesBatchModel.company_id == owner.company_id, SalesBatchModel.source_file == SEED_TAG
                )
            ).first()
            if seeded:
                print("bootstrap_demo: la demo ya existe, no se hace nada.")
                return False

        now = datetime.now(timezone.utc)
        if owner is None:
            company = CompanyModel(
                name="PetHouse Lima", tax_id="20612345671", business_type="Tienda de mascotas",
                address="Av. Primavera 1234, Santiago de Surco, Lima", phone="01 4567890",
                email=OWNER_EMAIL, plan="premium", status="active",
            )
            session.add(company)
            session.flush()
            owner = UserModel(
                company_id=company.id, email=OWNER_EMAIL, full_name="Demo PetHouse",
                hashed_password=hash_password(owner_password), role="owner", status="active",
            )
            session.add(owner)
            session.flush()
        company_id = owner.company_id

        if session.execute(select(UserModel.id).where(UserModel.username == SELLER_USERNAME)).first() is None:
            session.add(UserModel(
                company_id=company_id, email=None, username=SELLER_USERNAME, full_name="Lucía Ramos",
                hashed_password=hash_password(seller_password), role="seller", status="active",
            ))

        if session.execute(select(SubscriptionModel.id).where(SubscriptionModel.company_id == company_id)).first() is None:
            session.add(SubscriptionModel(
                company_id=company_id, plan_id="premium", status="active",
                current_period_start=now, current_period_end=now + timedelta(days=365),
            ))

        # Category tree: brand (Perros/Gatos) -> type.
        cats: dict[tuple[str, str], CategoryModel] = {}
        for brand, types in CATEGORY_TREE.items():
            parent = session.execute(
                select(CategoryModel).where(
                    CategoryModel.company_id == company_id, CategoryModel.name == brand, CategoryModel.parent_id.is_(None)
                )
            ).scalar_one_or_none()
            if parent is None:
                parent = CategoryModel(company_id=company_id, name=brand, description=f"Productos para {brand.lower()}")
                session.add(parent)
                session.flush()
            for t in types:
                child = session.execute(
                    select(CategoryModel).where(CategoryModel.company_id == company_id, CategoryModel.name == t,
                                                CategoryModel.parent_id == parent.id)
                ).scalar_one_or_none()
                if child is None:
                    child = CategoryModel(company_id=company_id, name=t, description="", parent_id=parent.id)
                    session.add(child)
                    session.flush()
                cats[(brand, t)] = child

        products: dict[str, ProductModel] = {}
        for i, (sku, name, cost, price, safety, reorder, lead, cat, _) in enumerate(CATALOG, start=1):
            p = session.execute(
                select(ProductModel).where(ProductModel.company_id == company_id, ProductModel.sku == sku)
            ).scalar_one_or_none()
            if p is None:
                p = ProductModel(
                    company_id=company_id, sku=sku, name=name, description="", category_id=cats[cat].id,
                    unit_cost=Decimal(cost), unit_price=Decimal(price), currency="PEN", unit_of_measure="unidad",
                    lead_time_days=lead, safety_stock=safety, reorder_point=reorder, is_active=True,
                    barcode=ean13(f"77512345{i:04d}"), custom_attributes={},
                )
                session.add(p)
                session.flush()
            products[sku] = p

        # Legacy 2022-2024 history (what the original CSV import contained), unless present.
        legacy = session.execute(
            select(SalesBatchModel).where(SalesBatchModel.company_id == company_id, SalesBatchModel.source_file == LEGACY_FILE)
        ).scalar_one_or_none()
        if legacy is None:
            start, end = date(2022, 1, 1), date(2024, 12, 31)
            legacy = SalesBatchModel(company_id=company_id, source_file=LEGACY_FILE, status="completed",
                                     row_count=0, period_start=start, period_end=end)
            session.add(legacy)
            session.flush()
            rng = random.Random(2022)
            rows: list[SaleModel] = []
            for sku, _, _, price, *_rest, monthly_now in CATALOG:
                p = products[sku]
                # Demand grew ~12%/yr up to today's level, so 2022 starts clearly lower.
                growth = rng.uniform(0.08, 0.16)
                d = start
                while d <= end:
                    years_before_2026 = (date(2026, 6, 1) - d).days / 365.25
                    level = monthly_now / ((1 + growth) ** years_before_2026)
                    lam = level / 30.4 * SEASON[d.month] * WEEKDAY[d.weekday()]
                    qty = poisson(rng, lam)
                    if qty > 0:
                        unit = Decimal(price)
                        rows.append(SaleModel(
                            company_id=company_id, product_id=p.id, batch_id=legacy.id, sale_date=d,
                            quantity=qty, unit_price=unit, total_amount=unit * qty, currency="PEN",
                            seller_name="",
                        ))
                    d += timedelta(days=1)
            session.add_all(rows)
            legacy.row_count = len(rows)
            print(f"bootstrap_demo: {len(rows)} ventas históricas 2022-2024 creadas.")

        session.commit()
        print("bootstrap_demo: empresa, usuarios, catálogo y suscripción listos.")
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    if not enabled():
        return
    passwords = demo_passwords()
    if passwords is None:
        print(
            "bootstrap_demo: SEED_DEMO=true pero faltan DEMO_OWNER_PASSWORD y/o "
            f"DEMO_SELLER_PASSWORD (APP_ENV={settings.app_env}). No se siembra la demo: "
            "defina ambas variables o desactive SEED_DEMO.",
            file=sys.stderr,
        )
        return
    if bootstrap(*passwords):
        import seed_demo_history  # continues the history from 2025 to yesterday

        sys.argv = [sys.argv[0], "--company-email", OWNER_EMAIL]
        seed_demo_history.main()
        print("bootstrap_demo: historia 2025-hoy sembrada. Demo lista.")


if __name__ == "__main__":
    main()
