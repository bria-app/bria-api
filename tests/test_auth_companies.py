"""Bloque 2A — tests for auth + companies.

Two layers:
- Use-case unit tests with in-memory fake repositories (no DB, fast).
- Endpoint integration tests with an in-memory SQLite database and a transactional
  get_db override (register -> login -> /me flow).
"""
from __future__ import annotations

from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.modules.auth.application.use_cases.authentication import (
    ChangePassword,
    Login,
    RegisterAccount,
)
from app.modules.companies.application.use_cases.user import (
    InviteUser,
    UpdateCompanyUser,
    UpdateUserRole,
)
from app.modules.companies.domain.entities import Company, User
from app.modules.companies.domain.enums import UserRole, UserStatus
from app.modules.companies.domain.exceptions import (
    CompanyAlreadyExistsError,
    UserAlreadyExistsError,
)
from app.shared.domain.errors import ValidationError, ForbiddenError, UnauthorizedError


# --- In-memory fakes implementing the domain ports --------------------------
class FakeCompanyRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, Company] = {}

    def get_by_id(self, company_id: UUID) -> Company | None:
        return self._store.get(company_id)

    def get_by_tax_id(self, tax_id: str) -> Company | None:
        return next((c for c in self._store.values() if c.tax_id == tax_id), None)

    def list(self, offset: int = 0, limit: int = 50) -> list[Company]:
        return list(self._store.values())[offset : offset + limit]

    def add(self, company: Company) -> Company:
        if company.id is None:
            company.id = uuid4()
        self._store[company.id] = company
        return company

    def update(self, company: Company) -> Company:
        assert company.id is not None
        self._store[company.id] = company
        return company

    def delete(self, company_id: UUID) -> bool:
        return self._store.pop(company_id, None) is not None


class FakeUserRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, User] = {}

    def get_by_id(self, user_id: UUID) -> User | None:
        return self._store.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        return next(
            (u for u in self._store.values() if u.email.value == normalized), None
        )

    def list_by_company(
        self, company_id: UUID, offset: int = 0, limit: int = 50
    ) -> list[User]:
        rows = [u for u in self._store.values() if u.company_id == company_id]
        return rows[offset : offset + limit]

    def add(self, user: User) -> User:
        if user.id is None:
            user.id = uuid4()
        self._store[user.id] = user
        return user

    def update(self, user: User) -> User:
        assert user.id is not None
        self._store[user.id] = user
        return user

    def delete(self, user_id: UUID) -> bool:
        return self._store.pop(user_id, None) is not None


def _register(companies: FakeCompanyRepository, users: FakeUserRepository) -> None:
    RegisterAccount(companies, users).execute(
        email="owner@petshop.pe",
        password="secret123",
        full_name="Ana Owner",
        company_name="Petshop 1",
        tax_id="20123456789",
    )


# --- Use-case unit tests -----------------------------------------------------
class TestRegisterAccount:
    def test_creates_company_and_owner(self) -> None:
        companies, users = FakeCompanyRepository(), FakeUserRepository()
        tokens = RegisterAccount(companies, users).execute(
            email="owner@petshop.pe",
            password="secret123",
            full_name="Ana Owner",
            company_name="Petshop 1",
            tax_id="20123456789",
        )
        assert tokens.access_token and tokens.refresh_token
        owner = users.get_by_email("owner@petshop.pe")
        assert owner is not None
        assert owner.role == UserRole.OWNER
        assert owner.status == UserStatus.ACTIVE

    def test_duplicate_tax_id_raises(self) -> None:
        companies, users = FakeCompanyRepository(), FakeUserRepository()
        _register(companies, users)
        with pytest.raises(CompanyAlreadyExistsError):
            RegisterAccount(companies, users).execute(
                email="other@petshop.pe",
                password="secret123",
                full_name="B",
                company_name="Petshop 2",
                tax_id="20123456789",
            )

    def test_duplicate_email_raises(self) -> None:
        companies, users = FakeCompanyRepository(), FakeUserRepository()
        _register(companies, users)
        with pytest.raises(UserAlreadyExistsError):
            RegisterAccount(companies, users).execute(
                email="owner@petshop.pe",
                password="secret123",
                full_name="B",
                company_name="Petshop 2",
                tax_id="20999999999",
            )


class TestLogin:
    def test_login_ok(self) -> None:
        companies, users = FakeCompanyRepository(), FakeUserRepository()
        _register(companies, users)
        tokens = Login(users).execute(email="owner@petshop.pe", password="secret123")
        assert tokens.access_token

    def test_wrong_password_raises(self) -> None:
        companies, users = FakeCompanyRepository(), FakeUserRepository()
        _register(companies, users)
        with pytest.raises(UnauthorizedError):
            Login(users).execute(email="owner@petshop.pe", password="wrong")

    def test_unknown_user_raises(self) -> None:
        users = FakeUserRepository()
        with pytest.raises(UnauthorizedError):
            Login(users).execute(email="nobody@petshop.pe", password="x")

    def test_disabled_user_forbidden(self) -> None:
        companies, users = FakeCompanyRepository(), FakeUserRepository()
        _register(companies, users)
        owner = users.get_by_email("owner@petshop.pe")
        assert owner is not None
        owner.disable()
        users.update(owner)
        with pytest.raises(ForbiddenError):
            Login(users).execute(email="owner@petshop.pe", password="secret123")


class TestUserManagement:
    def test_invite_duplicate_email_raises(self) -> None:
        companies, users = FakeCompanyRepository(), FakeUserRepository()
        _register(companies, users)
        with pytest.raises(UserAlreadyExistsError):
            InviteUser(users).execute(
                uuid4(),
                email="owner@petshop.pe",
                full_name="Dup",
                role=UserRole.ANALYST,
                temporary_password="temp1234",
            )

    def test_update_role(self) -> None:
        users = FakeUserRepository()
        company_id = uuid4()
        invited = InviteUser(users).execute(
            company_id,
            email="analyst@petshop.pe",
            full_name="Carlos",
            role=UserRole.VIEWER,
            temporary_password="temp1234",
        )
        updated = UpdateUserRole(users).execute(
            company_id, invited.id, role=UserRole.ANALYST, acting_user_id=uuid4()
        )
        assert updated.role == "analyst"

    def test_change_password_wrong_current_raises(self) -> None:
        companies, users = FakeCompanyRepository(), FakeUserRepository()
        _register(companies, users)
        owner = users.get_by_email("owner@petshop.pe")
        assert owner is not None
        assert owner.id is not None
        with pytest.raises(ValidationError):
            ChangePassword(users).execute(
                owner.id, current_password="wrong", new_password="newpass123"
            )


    def test_nobody_else_resets_the_owner_password(self) -> None:
        companies, users = FakeCompanyRepository(), FakeUserRepository()
        _register(companies, users)
        owner = users.get_by_email("owner@petshop.pe")
        assert owner is not None and owner.id is not None and owner.company_id is not None
        with pytest.raises(ForbiddenError):
            UpdateCompanyUser(users).execute(owner.company_id, owner.id, acting_user_id=uuid4(), password="takeover1")
        # Renaming the owner and the owner's own reset still work.
        renamed = UpdateCompanyUser(users).execute(owner.company_id, owner.id, acting_user_id=uuid4(), full_name="Ana María")
        assert renamed.full_name == "Ana María"
        UpdateCompanyUser(users).execute(owner.company_id, owner.id, acting_user_id=owner.id, password="newpass123")

# --- Endpoint integration tests (SQLite) ------------------------------------
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


_REGISTER_PAYLOAD = {
    "email": "owner@petshop.pe",
    "password": "secret123",
    "full_name": "Ana Owner",
    "company_name": "Petshop 1",
    "tax_id": "20123456789",
}


class TestAuthEndpoints:
    def test_register_login_me_flow(self, client: TestClient) -> None:
        reg = client.post("/api/v1/auth/register", json=_REGISTER_PAYLOAD)
        assert reg.status_code == 201, reg.text
        assert reg.json()["access_token"]

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@petshop.pe", "password": "secret123"},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]

        me = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert me.status_code == 200, me.text
        body = me.json()
        assert body["email"] == "owner@petshop.pe"
        assert body["role"] == "owner"

    def test_me_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_duplicate_registration_conflict(self, client: TestClient) -> None:
        first = client.post("/api/v1/auth/register", json=_REGISTER_PAYLOAD)
        assert first.status_code == 201
        second = client.post("/api/v1/auth/register", json=_REGISTER_PAYLOAD)
        assert second.status_code == 409, second.text
