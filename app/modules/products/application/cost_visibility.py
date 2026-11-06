"""Products module — who may see purchase costs and margins.

Sellers (cashiers) run the till: they see prices and stock, never what the shop paid
for a product or the margin it makes. Their product reads keep the cost fields, as null.
"""
from __future__ import annotations

from app.modules.products.application.dtos import ProductDTO, ProductTimelineDTO

COST_HIDDEN_ROLES = frozenset({"seller"})


def can_see_costs(role: str) -> bool:
    return role not in COST_HIDDEN_ROLES


def product_for_role(product: ProductDTO, role: str) -> ProductDTO:
    return product if can_see_costs(role) else product.without_costs()


def products_for_role(products: list[ProductDTO], role: str) -> list[ProductDTO]:
    return products if can_see_costs(role) else [p.without_costs() for p in products]


def timeline_for_role(timeline: ProductTimelineDTO, role: str) -> ProductTimelineDTO:
    return timeline if can_see_costs(role) else timeline.without_costs()
