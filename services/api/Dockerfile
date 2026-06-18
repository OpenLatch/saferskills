# syntax=docker/dockerfile:1.7
# SaferSkills API — multi-stage build with uv.
#
# Context is the REPO ROOT (like webapp/Dockerfile): the scan engine reads its rules
# from the repo-root rubric/ tree at runtime, and that dir is outside services/api/.
# Without it the engine loads 0 rules and every scan scores a fake 100. Paths below
# are repo-root-relative.

FROM python:3.14-slim AS builder
WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ADD https://astral.sh/uv/install.sh /tmp/install-uv.sh
RUN sh /tmp/install-uv.sh && rm /tmp/install-uv.sh
ENV PATH="/root/.local/bin:$PATH"

COPY services/api/pyproject.toml services/api/uv.lock* services/api/README.md ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY services/api/app/ ./app/

# alembic.ini + migrations/ are needed at runtime: the API runs
# `alembic upgrade head` in-process on every boot (app/core/startup.py).
COPY services/api/alembic.ini ./
COPY services/api/migrations/ ./migrations/

# Detection rules the scan engine loads at runtime (_resolve_rubric_dir → /app/rubric).
COPY rubric/ ./rubric/

# ── runtime image ────────────────────────────────────────────────────────
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Build identity stamped onto every scan (app/core/config.py). Previously unconsumed,
# so versions were "unknown" and the reconcile's rule/engine re-eval never fired.
# RUBRIC_VERSION/ENGINE_VERSION are the rubric/ + scan-engine subtree SHAs (CI-computed),
# so re-eval fires exactly when rules/engine change. The worker reuses this image.
ARG GIT_SHA=unknown
ARG RUBRIC_VERSION=unknown
ARG ENGINE_VERSION=unknown
ENV GIT_SHA=$GIT_SHA \
    RUBRIC_VERSION=$RUBRIC_VERSION \
    ENGINE_VERSION=$ENGINE_VERSION

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash app

COPY --from=builder --chown=app:app /app/.venv ./.venv
COPY --from=builder --chown=app:app /app/app ./app
COPY --from=builder --chown=app:app /app/alembic.ini ./
COPY --from=builder --chown=app:app /app/migrations ./migrations
COPY --from=builder --chown=app:app /app/rubric ./rubric

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
