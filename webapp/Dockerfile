# syntax=docker/dockerfile:1.7
# SaferSkills webapp — Astro build → nginx static host.

FROM node:24-alpine AS builder
WORKDIR /repo

# Workspace layout matches the repo (pnpm workspaces).
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* tsconfig.base.json ./
COPY webapp/package.json webapp/
COPY ui/package.json ui/

RUN corepack enable && corepack prepare pnpm@10 --activate
RUN pnpm install --frozen-lockfile || pnpm install

COPY webapp ./webapp
COPY ui ./ui

WORKDIR /repo/webapp
RUN pnpm run build

# ── runtime image ────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

COPY webapp/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /repo/webapp/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O- http://localhost/ >/dev/null || exit 1
