"""Fixes «planes-acceso»: Premium access honours the paid period, emails are one account
whatever their case/spaces, every new password has 8+ characters, plan texts without jargon.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.modules.billing.application.dtos import SubscriptionDTO
from app.modules.billing.application.use_cases.billing import (
    CancelSubscription,
    CheckPremiumAccess,
    Checkout,
    GetSubscription,
    ResumeSubscription,
    UpdateSubscriptionStatus,
)
from app.modules.billing.domain.entities import Subscription
from app.modules.billing.domain.enums import BillingCycle, PaymentMethod, SubscriptionStatus
from app.modules.billing.domain.exceptions import PaymentValidationError
from app.modules.billing.domain.plans import PLANS
from app.modules.billing.infrastructure.plan_access import company_has_premium_access
from app.modules.companies.domain.credentials import MIN_PASSWORD_LENGTH, ensure_new_password
from app.modules.companies.domain.exceptions import WeakPasswordError
from app.modules.companies.infrastructure.persistence.models import UserModel
from app.shared.infrastructure.security.hashing import hash_password
from tests.test_audit_fixes import API, _create_user, _register, client, db_factory  # noqa: F401

NOW = datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc)


def _ruc(prefix10: str) -> str:
    """A RUC with a valid SUNAT check digit (mod 11, weights 5,4,3,2,7,6,5,4,3,2)."""
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(int(d) * w for d, w in zip(prefix10, weights))
    digit = 11 - total % 11
    digit = 0 if digit == 10 else 1 if digit == 11 else digit
    return f"{prefix10}{digit}"


def test_ruc_helper_matches_known_valid_ruc() -> None:
    assert _ruc("2012345678") == "20123456786"


# --- fakes ----------------------------------------------------------------------
class FakeSubscriptions:
    def __init__(self) -> None:
        self.store: dict[UUID, Subscription] = {}

    def get_by_company(self, company_id: UUID) -> Subscription | None:
        return self.store.get(company_id)

    def add(self, subscription: Subscription) -> Subscription:
        subscription.id = subscription.id or uuid4()
        self.store[subscription.company_id] = subscription
        return subscription

    def update(self, subscription: Subscription) -> Subscription:
        assert subscription.id is not None
        self.store[subscription.company_id] = subscription
        return subscription


class FakePayments:
    def __init__(self) -> None:
        self.items: list = []

    def add(self, payment):  # type: ignore[no-untyped-def]
        payment.id = uuid4()
        self.items.append(payment)
        return payment

    def list_by_company(self, company_id: UUID, limit: int = 50) -> list:
        return [p for p in self.items if p.company_id == company_id]

    def reference_exists(self, reference: str) -> bool:
        return False


def _sub(status: SubscriptionStatus, end: datetime, plan: str = "premium") -> tuple[FakeSubscriptions, UUID]:
    repo = FakeSubscriptions()
    cid = uuid4()
    repo.add(Subscription(company_id=cid, plan_id=plan, status=status,
                          current_period_start=end - timedelta(days=30), current_period_end=end))
    return repo, cid


# --- 1. Premium access honours the paid period ------------------------------------
class TestPremiumAccessRule:
    @pytest.mark.parametrize(
        ("status", "end_offset", "expected"),
        [
            (SubscriptionStatus.ACTIVE, timedelta(days=10), True),
            (SubscriptionStatus.TRIALING, timedelta(days=10), True),
            # Canceled only stops the renewal: access lasts until the paid period ends.
            (SubscriptionStatus.CANCELED, timedelta(days=10), True),
            (SubscriptionStatus.CANCELED, -timedelta(seconds=1), False),
            # An active Premium past its period end is not paid any more.
            (SubscriptionStatus.ACTIVE, -timedelta(days=1), False),
            (SubscriptionStatus.TRIALING, -timedelta(days=1), False),
            (SubscriptionStatus.PAST_DUE, timedelta(days=10), False),
        ],
    )
    def test_enforcement_matches_dto(self, status: SubscriptionStatus, end_offset: timedelta, expected: bool) -> None:
        repo, cid = _sub(status, NOW + end_offset)
        assert CheckPremiumAccess(repo).execute(cid, NOW) is expected
        assert SubscriptionDTO.from_entity(repo.store[cid], NOW).is_premium is expected

    def test_free_plan_and_missing_row_have_no_access(self) -> None:
        repo, cid = _sub(SubscriptionStatus.ACTIVE, NOW + timedelta(days=10), plan="free")
        assert CheckPremiumAccess(repo).execute(cid, NOW) is False
        assert CheckPremiumAccess(FakeSubscriptions()).execute(uuid4(), NOW) is False

    def test_naive_period_end_is_read_as_utc(self) -> None:
        repo, cid = _sub(SubscriptionStatus.CANCELED, (NOW + timedelta(hours=1)).replace(tzinfo=None))
        assert CheckPremiumAccess(repo).execute(cid, NOW) is True

    def test_expired_active_premium_falls_back_to_free(self) -> None:
        repo, cid = _sub(SubscriptionStatus.ACTIVE, datetime.now(timezone.utc) - timedelta(days=1))
        dto = GetSubscription(repo).execute(cid)
        assert dto.plan_id == "free" and dto.is_premium is False and dto.auto_renew is False
        assert repo.store[cid].plan_id == "free"

    def test_canceled_premium_inside_period_stays_premium(self) -> None:
        end = datetime.now(timezone.utc) + timedelta(days=12)
        repo, cid = _sub(SubscriptionStatus.CANCELED, end)
        dto = GetSubscription(repo).execute(cid)
        assert dto.plan_id == "premium" and dto.is_premium is True and dto.auto_renew is False

    def test_cancel_of_expired_premium_gives_no_extra_time(self) -> None:
        end = datetime.now(timezone.utc) - timedelta(days=3)
        repo, cid = _sub(SubscriptionStatus.ACTIVE, end)
        with pytest.raises(PaymentValidationError, match="ya venció"):
            CancelSubscription(repo).execute(cid)
        assert repo.store[cid].current_period_end == end

    def test_resume_of_expired_canceled_premium_is_refused(self) -> None:
        repo, cid = _sub(SubscriptionStatus.CANCELED, datetime.now(timezone.utc) - timedelta(days=1))
        with pytest.raises(PaymentValidationError):
            ResumeSubscription(repo).execute(cid)

    def test_webhook_activation_without_dates_is_a_month_of_access(self) -> None:
        repo = FakeSubscriptions()
        cid = uuid4()
        dto = UpdateSubscriptionStatus(repo).execute(cid, SubscriptionStatus.ACTIVE, plan_id="premium")
        assert dto.is_premium is True
        assert dto.current_period_end > datetime.now(timezone.utc) + timedelta(days=27)

    def test_webhook_with_explicit_past_end_is_expired(self) -> None:
        repo = FakeSubscriptions()
        cid = uuid4()
        past = datetime.now(timezone.utc) - timedelta(days=2)
        dto = UpdateSubscriptionStatus(repo).execute(
            cid, SubscriptionStatus.ACTIVE, plan_id="premium",
            period_start=past - timedelta(days=30), period_end=past,
        )
        assert dto.is_premium is False
        assert CheckPremiumAccess(repo).execute(cid) is False

    def test_renewing_a_canceled_premium_extends_from_its_end(self) -> None:
        end = datetime.now(timezone.utc) + timedelta(days=5)
        repo, cid = _sub(SubscriptionStatus.CANCELED, end)
        result = Checkout(repo, FakePayments()).execute(
            cid, "premium", BillingCycle.MONTHLY, PaymentMethod.YAPE, yape_code="123456"
        )
        assert result.subscription.status == SubscriptionStatus.ACTIVE
        assert result.subscription.current_period_end > end + timedelta(days=27)


class TestPremiumAccessThroughApi:
    def test_cancel_keeps_access_until_period_end(
        self, client: TestClient, db_factory: sessionmaker[Session]  # noqa: F811
    ) -> None:
        headers, cid, _ = _register(client, "pa1", _ruc("2010000001"))
        pay = client.post(
            f"{API}/companies/{cid}/billing/checkout", headers=headers,
            json={"method": "yape", "yape_code": "123456"},
        )
        assert pay.status_code == 201, pay.text
        cancel = client.post(f"{API}/companies/{cid}/billing/cancel", headers=headers)
        assert cancel.status_code == 200, cancel.text
        assert cancel.json()["status"] == "canceled" and cancel.json()["is_premium"] is True

        with db_factory() as session:
            assert company_has_premium_access(session, UUID(cid)) is True
            later = datetime.now(timezone.utc) + timedelta(days=40)
            assert company_has_premium_access(session, UUID(cid), later) is False

    def test_active_premium_past_its_end_is_expired(
        self, client: TestClient, db_factory: sessionmaker[Session]  # noqa: F811
    ) -> None:
        headers, cid, _ = _register(client, "pa2", _ruc("2010000002"))
        past = datetime.now(timezone.utc) - timedelta(days=1)
        res = client.post(
            f"{API}/billing/webhooks/simulate/{cid}", headers=headers,
            json={"status": "active", "plan_id": "premium",
                  "current_period_start": (past - timedelta(days=30)).isoformat(),
                  "current_period_end": past.isoformat()},
        )
        assert res.status_code == 200, res.text
        assert res.json()["is_premium"] is False
        with db_factory() as session:
            assert company_has_premium_access(session, UUID(cid)) is False
        sub = client.get(f"{API}/companies/{cid}/billing/subscription", headers=headers).json()
        assert sub["plan_id"] == "free" and sub["is_premium"] is False


# --- 2. Email: one account whatever the case or spaces ----------------------------
class TestEmailNormalisation:
    def _body(self, email: str, tax_id: str, password: str = "secreto123") -> dict[str, str]:
        return {"email": email, "password": password, "full_name": "Ana", "company_name": "Tienda Ana", "tax_id": tax_id}

    def test_register_refuses_the_same_email_with_other_case_and_spaces(self, client: TestClient) -> None:  # noqa: F811
        first = client.post(f"{API}/auth/register", json=self._body("Ana@Tienda.pe", _ruc("2010000003")))
        assert first.status_code == 201, first.text
        dup = client.post(f"{API}/auth/register", json=self._body("  ana@tienda.pe ", _ruc("2010000004")))
        assert dup.status_code == 409, dup.text
        assert "ana@tienda.pe" in dup.json()["message"]

    def test_login_ignores_case_and_spaces(self, client: TestClient) -> None:  # noqa: F811
        assert client.post(f"{API}/auth/register", json=self._body("Ana@Tienda.pe", _ruc("2010000005"))).status_code == 201
        for login in ("ana@tienda.pe ", " ANA@TIENDA.PE", "Ana@Tienda.pe"):
            res = client.post(f"{API}/auth/login", json={"identifier": login, "password": "secreto123"})
            assert res.status_code == 200, (login, res.text)
        me = client.get(
            f"{API}/auth/me",
            headers={"Authorization": f"Bearer {res.json()['access_token']}"},
        ).json()
        assert me["email"] == "ana@tienda.pe"

    def test_legacy_row_with_capitals_is_found(
        self, client: TestClient, db_factory: sessionmaker[Session]  # noqa: F811
    ) -> None:
        _, cid, _ = _register(client, "pa6", _ruc("2010000006"))
        with db_factory() as session:
            session.add(UserModel(
                company_id=UUID(cid), email="Luis@Tienda.pe ", full_name="Luis",
                hashed_password=hash_password("clave1"), role="admin", status="active",
            ))
            session.commit()
        # Login works with the normalised email (and an old 6-character password).
        res = client.post(f"{API}/auth/login", json={"identifier": "luis@tienda.pe", "password": "clave1"})
        assert res.status_code == 200, res.text
        dup = client.post(f"{API}/auth/register", json=self._body("LUIS@tienda.pe", _ruc("2010000007")))
        assert dup.status_code == 409, dup.text


# --- 3. Every new password has 8+ characters ---------------------------------------
class TestPasswordMinimum:
    def test_domain_rule(self) -> None:
        assert MIN_PASSWORD_LENGTH == 8
        ensure_new_password("12345678")
        with pytest.raises(WeakPasswordError, match="al menos 8 caracteres"):
            ensure_new_password("1234567")
        with pytest.raises(WeakPasswordError):
            ensure_new_password("        ")

    def test_register_with_short_password_is_refused(self, client: TestClient) -> None:  # noqa: F811
        res = client.post(f"{API}/auth/register", json={
            "email": "corta@tienda.pe", "password": "abc1234", "full_name": "C",
            "company_name": "Corta", "tax_id": _ruc("2010000008"),
        })
        assert res.status_code == 422, res.text
        assert "al menos 8 caracteres" in res.json()["message"]

    def test_create_user_set_and_change_password(self, client: TestClient) -> None:  # noqa: F811
        headers, cid, _ = _register(client, "pa9", _ruc("2010000009"))
        short = client.post(
            f"{API}/companies/{cid}/users", headers=headers,
            json={"full_name": "Vende", "username": "vende1", "password": "abc1234", "role": "seller"},
        )
        assert short.status_code == 422, short.text
        assert "al menos 8 caracteres" in short.json()["message"]

        uid, seller_headers = _create_user(client, headers, cid, "vende2", "seller")
        reset = client.patch(f"{API}/companies/{cid}/users/{uid}", headers=headers, json={"password": "abc1234"})
        assert reset.status_code == 422, reset.text
        ok = client.patch(f"{API}/companies/{cid}/users/{uid}", headers=headers, json={"password": "abcd1234"})
        assert ok.status_code == 200, ok.text

        weak = client.patch(
            f"{API}/auth/me/password", headers=headers,
            json={"current_password": "secret123", "new_password": "abc1234"},
        )
        assert weak.status_code == 422, weak.text
        assert "al menos 8 caracteres" in weak.json()["message"]
        good = client.patch(
            f"{API}/auth/me/password", headers=headers,
            json={"current_password": "secret123", "new_password": "nueva1234"},
        )
        assert good.status_code == 200, good.text

    def test_existing_short_password_still_signs_in(
        self, client: TestClient, db_factory: sessionmaker[Session]  # noqa: F811
    ) -> None:
        _, cid, _ = _register(client, "pa10", _ruc("2010000010"))
        with db_factory() as session:
            session.add(UserModel(
                company_id=UUID(cid), username="antiguo", full_name="Antiguo",
                hashed_password=hash_password("abc123"), role="seller", status="active",
            ))
            session.commit()
        res = client.post(f"{API}/auth/login", json={"identifier": "antiguo", "password": "abc123"})
        assert res.status_code == 200, res.text


# --- 4. Plan texts without jargon ---------------------------------------------------
class TestPlanTexts:
    JARGON = re.compile(r"\b(POS|KPIs?|ERP|SKU|stock|quiebre|reposici[oó]n)\b", re.IGNORECASE)

    def test_no_jargon_in_catalog(self) -> None:
        for plan in PLANS.values():
            for text in (plan.tagline, *plan.features, *plan.limits):
                assert not self.JARGON.search(text), text

    def test_free_plan_wording_and_web_contract(self) -> None:
        free = PLANS["free"]
        assert "Ventas en caja con boleta y factura" in free.features
        # The web reads the monthly limit from the digits in `limits` and keeps the
        # prediction line apart by matching «predicci»/«IA».
        assert re.search(r"\d+", " ".join(free.limits)).group(0) == "3"  # type: ignore[union-attr]
        assert sum(bool(re.search(r"predicci|\bIA\b", f, re.IGNORECASE)) for f in free.features) == 1


# --- forecasting quota follows the paid period ---------------------------------------
def test_forecast_quota_honours_the_paid_period(db_factory) -> None:  # noqa: F811
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from app.modules.billing.infrastructure.persistence.models import SubscriptionModel
    from app.modules.forecasting.infrastructure.plan import company_is_premium

    now = datetime.now(timezone.utc)
    cases = [
        ("active", now + timedelta(days=10), True),
        ("active", now - timedelta(days=1), False),
        ("canceled", now + timedelta(days=10), True),
        ("canceled", now - timedelta(days=1), False),
        ("past_due", now + timedelta(days=10), False),
    ]
    for status, end, expected in cases:
        session = db_factory()
        company_id = uuid4()
        session.add(SubscriptionModel(company_id=company_id, plan_id="premium", status=status,
                                      current_period_start=now - timedelta(days=20), current_period_end=end))
        session.flush()
        assert company_is_premium(session, company_id) is expected, (status, end)
        session.close()
