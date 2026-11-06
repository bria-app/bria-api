"""Products module — attaching own-column alerts to product reads.

The custom fields module owns the alert rules («Vencimiento en los próximos 30 días»);
this helper only asks the port once for a whole list and copies the hits into each
ProductDTO. Without a source, or without alerting columns, products come back as-is.
"""
from __future__ import annotations

from uuid import UUID

from app.modules.products.application.dtos import ProductAlertDTO, ProductDTO
from app.modules.products.application.ports import ProductAlertSource


def with_alerts(
    products: list[ProductDTO], company_id: UUID, source: ProductAlertSource | None
) -> list[ProductDTO]:
    if source is None or not products:
        return products
    hits = source.alerts(company_id, [(p.category_id, p.custom_attributes) for p in products])
    return [
        p.model_copy(update={"alerts": [ProductAlertDTO.model_validate(h) for h in found]}) if found else p
        for p, found in zip(products, hits, strict=True)
    ]


def with_alert(product: ProductDTO, company_id: UUID, source: ProductAlertSource | None) -> ProductDTO:
    return with_alerts([product], company_id, source)[0]
