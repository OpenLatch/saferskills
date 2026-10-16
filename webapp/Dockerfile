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
# The ingestion key is public; private upload credentials are secret-mounted.
ARG PUBLIC_POSTHOG_KEY=""
ENV PUBLIC_POSTHOG_KEY=$PUBLIC_POSTHOG_KEY
ARG PUBLIC_POSTHOG_HOST="/ingest"
ENV PUBLIC_POSTHOG_HOST=$PUBLIC_POSTHOG_HOST
# Release identity is shared by browser, SSR, and uploaded source maps.
ARG GIT_SHA=""
ENV PUBLIC_GIT_SHA=$GIT_SHA
# A cache-keyed opt-in: deployed images must generate and upload source maps.
ARG SOURCEMAP_UPLOAD=0
# `pnpm run build` runs `astro build` (which prerenders the native /docs/* pages
# into dist/client/docs) + the llms.txt + Pagefind index steps — one build, no
# separate docs server (I-06 native docs).
RUN pnpm run build

# Inject before the runtime COPY so the uploaded and served chunks match.
# Local/PR builds need no credentials. Deploy builds fail on missing credentials
# or upload failure, and never publish source maps in the runtime image.
ARG POSTHOG_PROJECT_ID=272364
ENV POSTHOG_CLI_HOST=https://eu.posthog.com
RUN --mount=type=secret,id=posthog_cli_api_key,env=POSTHOG_CLI_API_KEY <<'EOF'
set -eu
if [ "$SOURCEMAP_UPLOAD" = 1 ]; then
  : "${POSTHOG_CLI_API_KEY:?PostHog upload credential required}"
  : "${PUBLIC_GIT_SHA:?Release SHA required}"
  [ "$POSTHOG_PROJECT_ID" = 272364 ]
  export POSTHOG_CLI_PROJECT_ID="$POSTHOG_PROJECT_ID"
  pnpm exec posthog-cli sourcemap inject --directory dist \
    --release-name saferskills-webapp --release-version "$PUBLIC_GIT_SHA" --release-mode event
  pnpm exec posthog-cli sourcemap upload --directory dist \
    --release-name saferskills-webapp --release-version "$PUBLIC_GIT_SHA" --release-mode event --delete-after
fi
if [ -n "$(find dist -name '*.map' -print -quit)" ]; then
  echo "Source maps must not be shipped in the runtime image" >&2
  exit 1
fi
EOF

# ── runtime — Node 24 alpine serving the standalone bundle ───────────────
FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=5173
ARG GIT_SHA=""
ENV GIT_SHA=$GIT_SHA

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
