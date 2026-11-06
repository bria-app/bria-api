import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.config import settings
from app.shared.infrastructure.database.database import get_db
from app.shared.presentation.schemas import PlaceholderResponse
from pydantic import BaseModel
from typing import Dict

router = APIRouter(tags=["System"])

#: Short timeout: /status must answer even when the engine is down.
_ENGINE_PING_TIMEOUT_SECONDS = 3.0


class HealthResponse(BaseModel):
    status: str
    database: str
    # "real" = deployed FTGM engine; "mock" = demo engine with simulated numbers.
    ftgm_engine_mode: str

class StatusResponse(BaseModel):
    status: str
    dependencies: Dict[str, str]
    ftgm_engine_mode: str


def _ping_ftgm_engine() -> str:
    """Reachability of the real engine (its public /health). Mock mode never calls it."""
    if settings.ftgm_mode == "mock":
        return "mock (simulated, engine not called)"
    url = f"{settings.ftgm_engine_base_url.rstrip('/')}/health"
    try:
        response = httpx.get(url, timeout=_ENGINE_PING_TIMEOUT_SECONDS)
    except httpx.HTTPError:
        return "unreachable"
    return "ok" if response.status_code == 200 else f"error ({response.status_code})"

class VersionResponse(BaseModel):
    version: str

@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db, scope="function")) -> HealthResponse:
    """Basic health check endpoint that verifies database connectivity."""
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db_status = "unreachable"
        
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        ftgm_engine_mode=settings.ftgm_mode,
    )

@router.get("/status", response_model=StatusResponse)
def system_status(db: Session = Depends(get_db, scope="function")) -> StatusResponse:
    """More detailed status endpoint checking various dependencies."""
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db_status = "unreachable"
        
    return StatusResponse(
        status="ok" if db_status == "ok" else "degraded",
        dependencies={
            "database": db_status,
            "ftgm_engine": _ping_ftgm_engine(),
        },
        ftgm_engine_mode=settings.ftgm_mode,
    )

@router.get("/version", response_model=VersionResponse)
def system_version() -> VersionResponse:
    """Returns the current API version."""
    # Hardcoded for now, could be read from pyproject.toml
    return VersionResponse(version="0.1.0")

@router.get("/metadata", response_model=PlaceholderResponse)
def metadata() -> PlaceholderResponse:
    return PlaceholderResponse(
        message="Endpoint scaffold ready",
        module="system",
        action="get_metadata"
    )

