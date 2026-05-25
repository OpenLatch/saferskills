"""FastAPI entrypoint for the SaferSkills API.

W1 surface: /api/v1/health only. The scan engine, ingestion adapters, and
catalog/report endpoints land via Initiatives I-02 / I-03 / I-04 starting W2.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.observability import init_observability
from app.routers import health


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    await init_observability(settings)
    yield


app = FastAPI(
    title="SaferSkills API",
    description=(
        "The VirusTotal of AI agents — public, free, Apache-2.0 trust-scoring "
        "for skills, MCP servers, hooks, and plugins."
    ),
    version="0.0.0+foundation",
    lifespan=lifespan,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url=None,
)

# W1 CORS posture: open. Tightens to allow-list + auth when Track E lands.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)

app.include_router(health.router, prefix="/api/v1")
