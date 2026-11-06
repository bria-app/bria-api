"""Sales spreadsheet import: origin filter and the old-sales stock guard."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    from app.main import app
    from app.modules.companies.infrastructure.persistence import models  # noqa: F401
    from app.shared.infrastructure.database import Base, get_db

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSession()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def _setup_company(client: TestClient) -> tuple[dict[str, str], str]:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@tienda.pe",
            "password": "secret123",
            "full_name": "Ana Owner",
            "company_name": "Tienda Ana",
            "tax_id": "20123456789",
        },
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    company_id = client.get("/api/v1/auth/me", headers=headers).json()["company_id"]
    imported = client.post(
        f"/api/v1/companies/{company_id}/products/import",
        headers=headers,
        json={
            "rows": [{"row": 1, "name": "Polo azul", "unit_price": "25", "initial_stock": "30"}],
            "update_existing": True,
        },
    )
    assert imported.status_code == 200, imported.text
    return headers, company_id


def _sales_rows(days_ago: int, count: int) -> list[dict[str, str | int]]:
    start = date.today() - timedelta(days=days_ago)
    return [
        {
            "row": i + 1,
            "name": "Polo azul",
            "sale_date": (start + timedelta(days=i)).isoformat(),
            "quantity": 1,
        }
        for i in range(count)
    ]


def test_imported_history_shows_under_imported_origin(client: TestClient) -> None:
    """Excel loads become tickets, but must still list under origin=imported."""
    headers, company_id = _setup_company(client)
    res = client.post(
        f"/api/v1/companies/{company_id}/sales/import",
        headers=headers,
        json={"rows": _sales_rows(days_ago=90, count=5)},
    )
    assert res.status_code == 201, res.text
    assert res.json()["created"] == 5

    imported = client.get(
        f"/api/v1/companies/{company_id}/sales?origin=imported", headers=headers
    ).json()
    assert len(imported) == 5
    pos = client.get(f"/api/v1/companies/{company_id}/sales?origin=pos", headers=headers).json()
    assert pos == []


def test_old_sales_cannot_discount_stock(client: TestClient) -> None:
    """Months-old sales with affect_stock would double-count; the API refuses them."""
    headers, company_id = _setup_company(client)
    res = client.post(
        f"/api/v1/companies/{company_id}/sales/import",
        headers=headers,
        json={"rows": _sales_rows(days_ago=120, count=5), "affect_stock": True},
    )
    assert res.status_code == 422, res.text
    assert "ventas pasadas" in res.text

    # Recent bulk sales still discount stock normally.
    ok = client.post(
        f"/api/v1/companies/{company_id}/sales/import",
        headers=headers,
        json={"rows": _sales_rows(days_ago=3, count=3), "affect_stock": True},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["created"] == 3
