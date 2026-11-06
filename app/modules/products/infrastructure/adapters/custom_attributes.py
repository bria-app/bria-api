"""Products module — adapters over the custom fields module («columnas propias»).

* SqlCustomAttributeCaster types and validates a product's own column values; one
  instance reads the company's product columns once per import.
* SqlProductAlertSource evaluates the columns' alerts for a list of products,
  resolving each product's category ancestors for columns scoped to some categories.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.custom_fields.application.use_cases import (
    CastCustomAttributes,
    EvaluateColumnAlerts,
)
from app.modules.custom_fields.infrastructure.persistence.repositories import (
    SqlCustomFieldRepository,
)
from app.modules.products.infrastructure.persistence.repositories import SqlCategoryRepository


class SqlCustomAttributeCaster:
    def __init__(self, session: Session) -> None:
        self._cast = CastCustomAttributes(SqlCustomFieldRepository(session))

    def cast(
        self,
        company_id: UUID,
        attributes: dict[str, Any],
        previous: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._cast.execute(company_id, "product", attributes, previous=previous)


class SqlProductAlertSource:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._evaluate = EvaluateColumnAlerts(SqlCustomFieldRepository(session))

    def _ancestors(self, company_id: UUID) -> dict[UUID, UUID | None]:
        categories = SqlCategoryRepository(self._session).list_by_company(company_id)
        return {c.id: c.parent_id for c in categories if c.id is not None}

    def alerts(
        self, company_id: UUID, products: list[tuple[UUID | None, dict[str, Any]]]
    ) -> list[list[dict[str, str]]]:
        fields = self._evaluate.alerting_fields(company_id, "product")
        if not fields:
            return [[] for _ in products]
        parents = self._ancestors(company_id) if any(f.category_ids for f in fields) else {}
        scopes: dict[UUID | None, set[str]] = {}

        def scope_of(category_id: UUID | None) -> set[str]:
            if category_id not in scopes:
                chain: set[str] = set()
                current = category_id
                while current is not None and str(current) not in chain:
                    chain.add(str(current))
                    current = parents.get(current)
                scopes[category_id] = chain
            return scopes[category_id]

        hits = self._evaluate.execute(
            company_id, [(scope_of(cat), attrs) for cat, attrs in products], entity="product"
        )
        return [
            [{"key": h.key, "column": h.column, "label": h.label, "tone": h.tone} for h in found]
            for found in hits
        ]
