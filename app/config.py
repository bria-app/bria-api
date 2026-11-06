from typing import Annotated, Any, List
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic import Field, field_validator, model_validator

#: Environments where the insecure local defaults (JWT secret, demo passwords) are tolerated.
LOCAL_ENVS = frozenset({"development", "test"})
#: Known placeholder JWT secrets (config default and .env.example) — never valid outside dev.
PLACEHOLDER_JWT_SECRETS = frozenset(
    {"change-this-in-production", "change-this-in-production-use-a-strong-secret"}
)
MIN_JWT_SECRET_BYTES = 32

class Settings(BaseSettings):
    app_name: str = "bria API"
    app_env: str = "development"
    # When true SQLAlchemy echoes every SQL statement — very noisy, keep it opt-in.
    app_debug: bool = False
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://user:password@localhost:5432/bria"

    # CORS
    cors_origins: Annotated[List[str], NoDecode] = Field(default=["http://localhost:3000"])
    # Optional regex to allow dynamic origins (e.g. Vercel preview deploys):
    # CORS_ORIGIN_REGEX=https://.*\.vercel\.app
    cors_origin_regex: str = ""

    # Security / JWT
    jwt_secret_key: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_minutes: int = 60 * 24 * 7 # 7 days

    # FTGM Engine
    ftgm_engine_base_url: str = "http://localhost:8010/api/v1"
    # "real" calls the deployed FTGM engine; "mock" answers locally with demo-grade
    # predictions (no engine needed) — see adapters/mock_ftgm.py.
    ftgm_engine_mode: str = "real"
    # Respected as configured. Rolling-origin validation re-fits the model several times
    # per product, so the default is generous for whole-catalog runs.
    ftgm_engine_timeout_seconds: int = 180
    # Shared secret with the engine (engine env ENGINE_API_KEY). When set, every call to
    # the engine carries the header ``X-Engine-Key``. Empty = no header (local dev).
    ftgm_engine_api_key: str = ""
    # Explicit override to run the demo (mock) engine with APP_ENV=production. Without it
    # the API refuses to start in that combination (see main.check_ftgm_engine_mode).
    allow_ftgm_mock: bool = False
    # Seasonal period the engine forecasts on (12 = monthly). Drives day->period mapping.
    ftgm_seasonal_period: int = 12

    # Storage
    # Backend for uploaded files: "db" keeps bytes in Postgres (survives restarts /
    # ephemeral disks on Render/Railway free tiers); "local" writes to storage_root.
    storage_backend: str = "db"
    storage_root: str = "./storage"
    max_upload_size_mb: int = 10
    allowed_upload_mime_types: Annotated[List[str], NoDecode] = Field(default=["text/csv", "application/vnd.ms-excel"])

    # Email / SMTP
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    emails_from_email: str = "info@example.com"
    emails_from_name: str = "bria"

    @field_validator("cors_origins", "allowed_upload_mime_types", mode="before")
    @classmethod
    def _split_csv(cls, value: Any) -> Any:
        """Parse comma-separated env vars (e.g. CORS_ORIGINS=http://a,http://b) into a list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: Any) -> Any:
        """Coerce managed-Postgres URLs to the psycopg (v3) driver.

        Render/Neon/Railway hand out ``postgres://`` or ``postgresql://`` URLs, but
        SQLAlchemy needs an explicit ``postgresql+psycopg://`` driver. Leave URLs that
        already specify a driver (``postgresql+...``) untouched.
        """
        if isinstance(value, str):
            if value.startswith("postgresql+"):
                return value
            if value.startswith("postgresql://"):
                return "postgresql+psycopg://" + value[len("postgresql://"):]
            if value.startswith("postgres://"):
                return "postgresql+psycopg://" + value[len("postgres://"):]
        return value

    @property
    def ftgm_mode(self) -> str:
        """Normalised engine mode: ``"mock"`` (demo, simulated numbers) or ``"real"``."""
        return "mock" if self.ftgm_engine_mode.strip().lower() == "mock" else "real"

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @model_validator(mode="after")
    def _require_strong_jwt_secret(self) -> "Settings":
        """Outside development/test a placeholder or short JWT secret is a hard error:
        anyone could otherwise sign tokens for any company (audit A-03)."""
        if self.app_env.strip().lower() in LOCAL_ENVS:
            return self
        secret = self.jwt_secret_key or ""
        if secret in PLACEHOLDER_JWT_SECRETS or len(secret.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
            raise ValueError(
                f"JWT_SECRET_KEY must be set to a random value of at least {MIN_JWT_SECRET_BYTES} "
                f"bytes when APP_ENV={self.app_env!r} (placeholder or too short)."
            )
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
