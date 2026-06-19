#!/usr/bin/env node
/* build-pagefind.cjs — index the prerendered docs HTML for full-text search.
 * Runs as the last step of `pnpm build` (after the docs
 * are prerendered into dist/client/docs/**). Scopes the index to docs only —
 * the catalog/scan/agent SSR pages are excluded via the glob. Emits
 * dist/client/pagefind/ (pagefind.js + the wasm/index), which the DocsSearch
 * island dynamic-imports at runtime. */
'use strict'
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const WEBAPP = path.resolve(__dirname, '..')
const SITE = path.join(WEBAPP, 'dist', 'client')
const INDEX = path.join(SITE, 'pagefind', 'pagefind.js')

if (!fs.existsSync(path.join(SITE, 'docs'))) {
  console.error(`[build-pagefind] no docs at ${path.join(SITE, 'docs')} — run the build first.`)
  process.exit(1)
}

// Resolve the local `pagefind` (devDependency) JS launcher + run it through
// node directly — no shell (avoids command-injection + cross-platform npx
// quirks). `pagefind`'s `exports` map blocks `require()` of its package.json /
// internal files, so read the `bin` field straight off disk instead. Values
// below are repo paths, never user input.
const pkgDir = fs.existsSync(path.join(WEBAPP, 'node_modules', 'pagefind'))
  ? path.join(WEBAPP, 'node_modules', 'pagefind')
  : path.join(WEBAPP, '..', 'node_modules', 'pagefind')
const pkg = JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json'), 'utf8'))
const binRel = typeof pkg.bin === 'string' ? pkg.bin : pkg.bin.pagefind
const pagefindBin = path.join(pkgDir, binRel)

execFileSync(process.execPath, [pagefindBin, '--site', SITE, '--glob', 'docs/**/*.html'], {
  stdio: 'inherit',
  cwd: WEBAPP,
})

if (!fs.existsSync(INDEX)) {
  console.error(`[build-pagefind] expected ${INDEX} — Pagefind emitted no index.`)
  process.exit(1)
}
console.log('[build-pagefind] indexed dist/client/docs → dist/client/pagefind/')
