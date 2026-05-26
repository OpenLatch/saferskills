"""GET /api/v1/health — liveness + version + git-sha echo."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.orm_base import OrmBaseModel

router = APIRouter(tags=["meta"])


class HealthResponse(OrmBaseModel):
    status: str
    version: str
    git_sha: str


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.version,
        git_sha=settings.git_sha,
    )
