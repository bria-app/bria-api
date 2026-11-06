"""Billing module domain — plan catalog (static; prices in PEN, IGV included)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.modules.billing.domain.enums import BillingCycle

FREE_PLAN_ID = "free"
PREMIUM_PLAN_ID = "premium"
IGV_RATE = Decimal("0.18")


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    tagline: str
    price_monthly: Decimal
    price_yearly: Decimal
    features: tuple[str, ...] = field(default_factory=tuple)
    limits: tuple[str, ...] = field(default_factory=tuple)
    currency: str = "PEN"

    def price_for(self, cycle: BillingCycle) -> Decimal:
        return self.price_yearly if cycle == BillingCycle.YEARLY else self.price_monthly


PLANS: dict[str, Plan] = {
    FREE_PLAN_ID: Plan(
        id=FREE_PLAN_ID,
        name="Gratis",
        tagline="Todo para manejar tu negocio, sin costo.",
        price_monthly=Decimal("0.00"),
        price_yearly=Decimal("0.00"),
        features=(
            "Ventas en caja con boleta y factura",
            "Compras y proveedores",
            "Inventario con entradas y salidas de productos",
            "Columnas a tu medida en productos y proveedores",
            "Accesos para tus vendedores",
            "Predicciones con IA (3 al mes)",
        ),
        limits=(
            "Límite de 3 predicciones con IA al mes",
        ),
    ),
    PREMIUM_PLAN_ID: Plan(
        id=PREMIUM_PLAN_ID,
        name="Premium",
        tagline="Toda la IA trabajando para tu negocio.",
        price_monthly=Decimal("149.00"),
        price_yearly=Decimal("1490.00"),
        features=(
            "Todo lo del plan Gratis",
            "Predicciones con IA sin límite mensual",
            "Pronóstico de todo tu catálogo",
            "Pronóstico por proveedor, vendedor o categoría",
            "Compara lo pronosticado con lo que vendiste",
            "Te sugiere qué y cuánto comprar",
            "Para cuántos días te alcanza y qué se puede agotar",
            "Avisos cuando toca reponer",
            "Reportes e indicadores para descargar",
        ),
    ),
}


def get_plan(plan_id: str) -> Plan | None:
    return PLANS.get(plan_id)
