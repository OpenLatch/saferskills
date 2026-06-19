"""GET /api/v1/health — liveness + version + git-sha echo."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.startup_state import startup_state
from app.schemas.orm_base import OrmBaseModel

router = APIRouter(tags=["meta"])


class HealthResponse(OrmBaseModel):
    status: str
    version: str
    git_sha: str
    migrations_ok: bool
    migrations_error: str | None = None
    # "ok" | "degraded" — the in-process ingestion worker's start status.
    # "degraded" means background ingestion is dead while the API still serves;
    # it does NOT flip `status` (the API is live).
    ingestion: str


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.version,
        git_sha=settings.git_sha,
        migrations_ok=startup_state.migrations_ok,
        migrations_error=startup_state.migrations_error,
        ingestion="degraded" if startup_state.ingestion_degraded else "ok",
    )
