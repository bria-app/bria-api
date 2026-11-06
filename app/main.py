import uuid
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Awaitable, Any, cast
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.bootstrap.routers import api_router
from app.config import Settings, settings
from app.shared.domain.errors import (
    DomainError, NotFoundError, ConflictError, 
    ValidationError, UnauthorizedError, ForbiddenError
)
from app.shared.presentation.schemas import ErrorResponse
from app.shared.infrastructure.database.database import engine

logger = logging.getLogger(__name__)


class UnsafeConfigurationError(RuntimeError):
    """The process must not serve traffic with this configuration."""


def check_ftgm_engine_mode(config: Settings) -> None:
    """Refuse to start in production with the demo (mock) engine (audit C-04).

    The mock produces simulated forecasts; serving them to real users must be an explicit
    decision: set ``ALLOW_FTGM_MOCK=true`` to override (e.g. a public demo deployment).
    """
    if config.is_production and config.ftgm_mode == "mock" and not config.allow_ftgm_mock:
        message = (
            "FTGM_ENGINE_MODE=mock with APP_ENV=production: forecasts would be simulated. "
            "Set FTGM_ENGINE_MODE=real, or ALLOW_FTGM_MOCK=true to run the demo on purpose."
        )
        logger.critical(message)
        raise UnsafeConfigurationError(message)
    if config.ftgm_mode == "mock":
        logger.warning("FTGM engine in MOCK mode: forecasts are simulated (demo only).")


def _recover_stale_runs() -> None:
    """Fail forecast runs orphaned in "running" by a restart (audit M-05)."""
    from app.modules.forecasting.infrastructure.background import fail_stale_runs

    with Session(engine) as session:
        stale = fail_stale_runs(session)
        session.commit()
    if stale:
        logger.warning("Marked %d stale forecast run(s) as failed at startup.", stale)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    check_ftgm_engine_mode(settings)
    # Startup: Check database connection
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            logger.info("Database connection successful.")
        db_ok = True
    except SQLAlchemyError as e:
        logger.error("Database connection failed at startup: %s", e)
        # Note: We don't raise here, we allow the app to start (it will report degraded health)

    if db_ok:
        try:
            _recover_stale_runs()
        except SQLAlchemyError:
            logger.exception("Could not recover stale forecast runs at startup.")
    yield
    
    # Shutdown
    engine.dispose()

def create_app() -> FastAPI:
    # Production does not publish the interactive docs / schema (audit B-02).
    docs_enabled = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        description="Plataforma Web de Soporte de Decisiones para la Optimización de Inventarios mediante Predicción de Demanda y Análisis de KPIs basado en el Modelo FTGM en MYPEs retail de Lima Metropolitana.",
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "System", "description": "System health and status endpoints."},
            {"name": "Auth", "description": "Authentication and authorization."},
            {"name": "Companies", "description": "Company management."},
            {"name": "Products", "description": "Product catalog and SKUs."},
            {"name": "Sales", "description": "Sales history and data."},
            {"name": "Inventory", "description": "Current stock and movements."},
            {"name": "Forecasting", "description": "FTGM forecasting runs and results."},
            {"name": "KPIs", "description": "Key performance indicators."},
            {"name": "Recommendations", "description": "Actionable replenishment recommendations."},
        ]
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Let a deployed HTTPS frontend (e.g. Vercel) call this API on localhost
        # during local demos — Chrome Private Network Access preflight opt-in.
        allow_private_network=True,
    )

    # Request ID Logging Middleware
    @app.middleware("http")
    async def add_request_id(request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> JSONResponse:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        # In a real app, bind the request_id to contextvars for logging
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return cast(JSONResponse, response)

    # Global Exception Handlers
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(code=exc.code, message=exc.message, details=exc.details).model_dump()
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(code=exc.code, message=exc.message, details=exc.details).model_dump()
        )
        
    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(code=exc.code, message=exc.message, details=exc.details).model_dump()
        )
        
    @app.exception_handler(UnauthorizedError)
    async def unauthorized_handler(request: Request, exc: UnauthorizedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=ErrorResponse(code=exc.code, message=exc.message, details=exc.details).model_dump(),
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    @app.exception_handler(ForbiddenError)
    async def forbidden_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=ErrorResponse(code=exc.code, message=exc.message, details=exc.details).model_dump()
        )

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(code=exc.code, message=exc.message, details=exc.details).model_dump()
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(code="INTERNAL_SERVER_ERROR", message="Ocurrió un error inesperado. Inténtalo de nuevo en unos minutos.").model_dump()
        )

    # Public, unauthenticated liveness endpoint (used by platform health checks).
    @app.get("/health", tags=["System"])
    def health() -> dict[str, str]:
        # Liveness stays "ok"; the engine mode is exposed so a demo engine is visible.
        return {"status": "ok", "ftgm_engine_mode": settings.ftgm_mode}

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app

app = create_app()

