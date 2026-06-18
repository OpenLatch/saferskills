# syntax=docker/dockerfile:1.10
# SaferSkills webapp — Astro 6 SSR via @astrojs/node standalone runtime.
# Replaces the W1 nginx static host per plan/01a-design-system-foundation.md §1.6 (D-FE-22).

# ── builder ─────────────────────────────────────────────────────────────
FROM node:24-alpine AS builder
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@10 --activate

# Workspace layout matches the repo (pnpm workspaces).
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* tsconfig.base.json ./
COPY webapp/package.json webapp/
COPY ui/package.json ui/

RUN pnpm install --frozen-lockfile || pnpm install

COPY webapp ./webapp
COPY ui ./ui

WORKDIR /repo/webapp
# PUBLIC_* vars are inlined into the Astro bundle at build time (Vite envPrefix
# "PUBLIC_" picks up matching process-env vars). Supplied as build-args by the
# deploy workflow (GH secret-backed). Empty defaults keep a plain local
# `docker build` working — an unset key just disables that integration.
ARG PUBLIC_TURNSTILE_SITE_KEY=""
ENV PUBLIC_TURNSTILE_SITE_KEY=$PUBLIC_TURNSTILE_SITE_KEY
# Browser observability — Sentry DSN + PostHog key/host are public (ship in the
# bundle by design). Empty defaults disable the SDK at runtime (env-checked in
# observability.ts).
ARG PUBLIC_SENTRY_DSN=""
ENV PUBLIC_SENTRY_DSN=$PUBLIC_SENTRY_DSN
ARG PUBLIC_POSTHOG_KEY=""
ENV PUBLIC_POSTHOG_KEY=$PUBLIC_POSTHOG_KEY
ARG PUBLIC_POSTHOG_HOST="https://eu.i.posthog.com"
ENV PUBLIC_POSTHOG_HOST=$PUBLIC_POSTHOG_HOST
# Git SHA → the Sentry release id (browser init `release` + source-map upload
# below). The deploy passes the build-arg as GIT_SHA; re-export as PUBLIC_GIT_SHA
# so Astro inlines it into the client bundle (only PUBLIC_* is inlined).
ARG GIT_SHA=""
ENV PUBLIC_GIT_SHA=$GIT_SHA
# `pnpm run build` runs `astro build` (which prerenders the native /docs/* pages
# into dist/client/docs) + the llms.txt + Pagefind index steps — one build, no
# separate docs server (I-06 native docs).
RUN pnpm run build

# Upload source maps to Sentry, keyed to the GIT_SHA release. SENTRY_AUTH_TOKEN
# is a BuildKit secret (never an image layer / build-cache metadata). No-op when
# the secret OR the release SHA is empty (plain local `docker build`, PR builds)
# — the guard makes the step non-fatal so a tokenless build still succeeds.
# SaferSkills Sentry is the DE region (https://de.sentry.io); org `openlatch`,
# project `saferskills-webapp`.
ENV SENTRY_URL="https://de.sentry.io"
RUN --mount=type=secret,id=sentry_auth_token,env=SENTRY_AUTH_TOKEN \
    if [ -n "$SENTRY_AUTH_TOKEN" ] && [ -n "$PUBLIC_GIT_SHA" ]; then \
      pnpm exec sentry-cli sourcemaps inject ./dist && \
      pnpm exec sentry-cli sourcemaps upload \
        --org openlatch \
        --project saferskills-webapp \
        --release "$PUBLIC_GIT_SHA" \
        ./dist ; \
    else \
      echo "Sentry source-map upload skipped (no auth token or no release SHA)." ; \
    fi

# ── runtime — Node 24 alpine serving the standalone bundle ───────────────
FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=5173

# Install production dependencies into a flat node_modules tree the runtime
# can resolve from /app. Going through `npm install --omit=dev` instead of
# carrying pnpm's workspace-symlinked node_modules across stages avoids the
# resolution gap that crashed staging on 2026-05-28 (ERR_MODULE_NOT_FOUND
# for `zod`): pnpm hoists into webapp/node_modules and node_modules/.pnpm,
# and only the latter was carried over, leaving the bundle's runtime imports
# unresolvable.
RUN corepack enable && corepack prepare pnpm@10 --activate
COPY --from=builder /repo/webapp/package.json ./package.json
RUN npm install --omit=dev --omit=peer --no-audit --no-fund --prefer-offline

COPY --from=builder /repo/webapp/dist ./dist

EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O- http://127.0.0.1:5173/ >/dev/null || exit 1

CMD ["node", "./dist/server/entry.mjs"]
