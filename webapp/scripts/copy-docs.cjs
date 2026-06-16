#!/usr/bin/env node
/* copy-docs.cjs — fold the Starlight docs SSG build into the main webapp build.
 *
 * The docs build (`astro build --config docs.astro.config.mjs`) emits to
 * `webapp/dist-docs/` with every asset + link prefixed `/docs` (Astro `base`).
 * The @astrojs/node standalone server serves `dist/client/**` as static files,
 * so copying the docs build into `dist/client/docs/` makes the main webapp
 * serve `/docs/*` as a static fall-through — one host, no separate docs server.
 * See plan/01-scaffold.md § Build & Deployment Strategy.
 *
 * Order matters in the Dockerfile: `pnpm run build` (main) creates
 * `dist/client`, then `pnpm run build:docs` runs this. Standalone is fine too —
 * cpSync creates intermediate dirs. */
'use strict'
const fs = require('node:fs')
const path = require('node:path')

const WEBAPP = path.resolve(__dirname, '..')
const SRC = path.join(WEBAPP, 'dist-docs')
const DEST = path.join(WEBAPP, 'dist', 'client', 'docs')

if (!fs.existsSync(SRC)) {
  console.error(`[copy-docs] missing ${SRC} — run the docs build first.`)
  process.exit(1)
}

// Replace any prior copy so a removed page never lingers.
fs.rmSync(DEST, { recursive: true, force: true })
fs.cpSync(SRC, DEST, { recursive: true })

const count = fs
  .readdirSync(SRC, { recursive: true })
  .filter((f) => String(f).endsWith('index.html')).length
console.log(`[copy-docs] copied dist-docs → dist/client/docs (${count} pages)`)
