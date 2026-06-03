# syntax=docker/dockerfile:1.7
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
# "PUBLIC_" picks up matching process-env vars). Supplied as a build-arg by the
# deploy workflow (GH secret-backed). Empty default keeps a plain local
# `docker build` working — an unset key just disables the scan-submit gate.
ARG PUBLIC_TURNSTILE_SITE_KEY=""
ENV PUBLIC_TURNSTILE_SITE_KEY=$PUBLIC_TURNSTILE_SITE_KEY
RUN pnpm run build

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
