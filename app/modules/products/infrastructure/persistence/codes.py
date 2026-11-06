"""Products module — global product code correlativo.

When a product arrives without a code (manual create, smart import, purchase of a new
item) it gets the company's next code: P-000001, P-000002... The counter lives on the
company row and is taken with SELECT ... FOR UPDATE so concurrent imports never hand
out the same code. Every company's catalog is independent.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.companies.infrastructure.persistence.models import CompanyModel
from app.modules.products.infrastructure.persistence.models import ProductModel

CODE_PREFIX = "P-"


def next_product_code(session: Session, company_id: UUID) -> str:
    company = session.execute(
        select(CompanyModel).where(CompanyModel.id == company_id).with_for_update()
    ).scalar_one()
    n = company.next_product_code or 1
    while True:
        code = f"{CODE_PREFIX}{n:06d}"
        n += 1
        taken = session.execute(
            select(ProductModel.id).where(
                ProductModel.company_id == company_id, ProductModel.sku == code
            )
        ).first()
        if taken is None:
            break
    company.next_product_code = n
    session.flush()
    return code
