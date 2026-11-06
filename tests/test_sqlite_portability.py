"""SQL that must run on SQLite (local stack, tests) as well as on Postgres (production).

The POS search used CONCAT()/LPAD(), the summaries used timezone()/GREATEST(): all
Postgres-only. SQLite also hands timestamps back naive and stores whatever wall time it
is given, so Lima-time bounds were compared five hours off.
"""
from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, literal, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.modules.sales.domain.services import lima_today
from app.shared.infrastructure.database.portable import (
    UTCDateTime,
    greatest,
    lima_date,
    zero_pad,
)

API = "/api/v1"
LIMA = timezone(timedelta(hours=-5))


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    from app.main import app
    from app.modules.companies.infrastructure.persistence import models  # noqa: F401
    from app.shared.infrastructure.database import Base, get_db

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)  # no lifespan: the real database is never touched
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def _company_with_product(client: TestClient) -> tuple[dict[str, str], str, str]:
    register = client.post(
        f"{API}/auth/register",
        json={
            "email": f"owner-{uuid4().hex[:8]}@tienda.pe",
            "password": "secret123",
            "full_name": "Ana Owner",
            "company_name": "Tienda Ana",
            "tax_id": "20123456789",
        },
    )
    assert register.status_code == 201, register.text
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    company_id = client.get(f"{API}/auth/me", headers=headers).json()["company_id"]
    imported = client.post(
        f"{API}/companies/{company_id}/products/import",
        headers=headers,
        json={
            "rows": [{"row": 1, "name": "Polo azul", "unit_price": "25", "initial_stock": "30"}],
            "update_existing": True,
        },
    )
    assert imported.status_code == 200, imported.text
    products = client.get(f"{API}/companies/{company_id}/products", headers=headers).json()
    return headers, company_id, products[0]["id"]


def _sell(
    client: TestClient, headers: dict[str, str], company_id: str, product_id: str, **body: object
) -> dict[str, object]:
    res = client.post(
        f"{API}/companies/{company_id}/sales-orders",
        headers=headers,
        json={
            "items": [{"product_id": product_id, "quantity": 1, "unit_price": "25"}],
            "payment_method": "yape",
            **body,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _search(client: TestClient, headers: dict[str, str], company_id: str, q: str) -> list[str]:
    res = client.get(f"{API}/companies/{company_id}/sales-orders", headers=headers, params={"q": q})
    assert res.status_code == 200, res.text
    return [row["document_number"] for row in res.json()["items"]]


# --- the POS search (known bug) ----------------------------------------------------
def test_sales_search_by_document_number_on_sqlite(client: TestClient) -> None:
    headers, company_id, product_id = _company_with_product(client)
    boleta = _sell(client, headers, company_id, product_id, document_type="boleta", client_name="Juan Pérez")
    ticket = _sell(client, headers, company_id, product_id, document_type="nota_venta")
    boleta_no, ticket_no = str(boleta["document_number"]), str(ticket["document_number"])
    assert boleta_no.startswith("B") and ticket_no.startswith("NV-")

    assert _search(client, headers, company_id, boleta_no) == [boleta_no]
    assert _search(client, headers, company_id, boleta_no.lower()) == [boleta_no]
    assert _search(client, headers, company_id, boleta_no[-4:]) == [boleta_no]  # padded tail
    assert _search(client, headers, company_id, ticket_no) == [ticket_no]
    assert _search(client, headers, company_id, "juan") == [boleta_no]
    assert _search(client, headers, company_id, "F999-00000001") == []


def test_sales_date_filter_and_summary_use_lima_day(client: TestClient) -> None:
    headers, company_id, product_id = _company_with_product(client)
    _sell(client, headers, company_id, product_id, document_type="nota_venta")
    _sell(client, headers, company_id, product_id, document_type="nota_venta")
    today = lima_today().isoformat()
    base = f"{API}/companies/{company_id}/sales-orders"

    page = client.get(base, headers=headers, params={"date_from": today, "date_to": today})
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 2

    summary = client.get(f"{base}/summary", headers=headers, params={"date_from": today, "date_to": today})
    assert summary.status_code == 200, summary.text
    assert summary.json()["orders"] == 2
    assert summary.json()["by_day"] == [{"date": today, "orders": 2, "total": "50.00"}]


def test_erp_summary_and_timeline_run_on_sqlite(client: TestClient) -> None:
    headers, company_id, product_id = _company_with_product(client)
    _sell(client, headers, company_id, product_id, document_type="nota_venta")
    lost = client.post(
        f"{API}/companies/{company_id}/lost-sales",
        headers=headers,
        json={"product_id": product_id, "requested_quantity": 5, "available_quantity": 2},
    )
    assert lost.status_code == 201, lost.text

    erp = client.get(f"{API}/companies/{company_id}/dashboard/erp-summary", headers=headers)
    assert erp.status_code == 200, erp.text

    timeline = client.get(f"{API}/companies/{company_id}/products/{product_id}/timeline", headers=headers)
    assert timeline.status_code == 200, timeline.text

    preview = client.post(
        f"{API}/companies/{company_id}/forecast-runs/scope-preview",
        headers=headers,
        json={"scope": {"type": "all"}},
    )
    assert preview.status_code == 200, preview.text


# --- the helpers themselves --------------------------------------------------------
_meta = MetaData()
_t = Table(
    "portable_probe",
    _meta,
    Column("id", Integer, primary_key=True),
    Column("n", Integer),
    Column("label", String),
    Column("at", UTCDateTime()),
)


@pytest.fixture()
def probe() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://")
    _meta.create_all(engine)
    with Session(engine) as session:
        yield session


def test_zero_pad_and_greatest_on_sqlite(probe: Session) -> None:
    assert probe.execute(select(zero_pad(literal(12), 8))).scalar_one() == "00000012"
    assert probe.execute(select(zero_pad(literal(123456789), 8))).scalar_one() == "123456789"
    assert probe.execute(select(zero_pad(literal(None, Integer), 8))).scalar_one() is None
    assert probe.execute(select(greatest(literal(3) - literal(5), 0))).scalar_one() == 0
    assert probe.execute(select(greatest(literal(7), 0))).scalar_one() == 7


def test_utc_datetime_and_lima_date_on_sqlite(probe: Session) -> None:
    # 22:30 in Lima on 2 Nov is 03:30 UTC on 3 Nov.
    lima_evening = datetime(2026, 11, 2, 22, 30, tzinfo=LIMA)
    probe.execute(_t.insert().values(id=1, at=lima_evening))
    stored = probe.execute(select(_t.c.at)).scalar_one()
    assert stored == lima_evening and stored.tzinfo is not None
    assert probe.execute(select(lima_date(_t.c.at))).scalar_one().isoformat() == "2026-11-02"
    # Bounds in Lima time select the row by instant, not by wall time.
    bound = datetime(2026, 11, 2, 22, 0, tzinfo=LIMA)
    assert probe.execute(select(_t.c.id).where(_t.c.at >= bound)).scalar_one() == 1


def test_postgres_sql_is_unchanged() -> None:
    def sql(expr: object) -> str:
        return str(select(expr).compile(dialect=postgresql.dialect()))  # type: ignore[call-overload]

    assert "date(timezone('America/Lima', portable_probe.at))" in sql(lima_date(_t.c.at))
    assert "greatest(portable_probe.n" in sql(greatest(_t.c.n, 0))
    assert "lpad" not in sql(zero_pad(_t.c.n, 8)).lower()
