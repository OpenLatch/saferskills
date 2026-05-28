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
RUN pnpm run build

# ── runtime — Node 24 alpine serving the standalone bundle ───────────────
FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=5173

COPY --from=builder /repo/webapp/dist ./dist
COPY --from=builder /repo/webapp/package.json ./package.json
COPY --from=builder /repo/node_modules ./node_modules
COPY --from=builder /repo/ui ./ui

EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O- http://127.0.0.1:5173/ >/dev/null || exit 1

CMD ["node", "./dist/server/entry.mjs"]
