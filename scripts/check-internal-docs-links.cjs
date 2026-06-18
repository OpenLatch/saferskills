#!/usr/bin/env node
/* check-internal-docs-links.cjs — build-time broken-internal-link gate for the
 * docs. Runs AFTER `astro build` over the prerendered docs HTML in
 * webapp/dist/client/docs: collects every internal `href` (the `/docs/*` surface)
 * and asserts each resolves to a built file. A broken `[link](/docs/nonexistent)`
 * fails the PR. Main-site links (e.g. /methodology) are out of this gate's scope.
 *
 * Usage (defaults to webapp/dist/client/docs):
 *   node scripts/check-internal-docs-links.cjs [distDir]
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')
const DIST = path.resolve(ROOT, process.argv[2] || 'webapp/dist/client/docs')
const BASE = '/docs' // the docs URL surface (native /docs/[...slug] route)

if (!fs.existsSync(DIST)) {
  console.error(`[docs-links] build output not found: ${DIST}\n  Run the docs build first.`)
  process.exit(1)
}

const htmlFiles = fs
  .readdirSync(DIST, { recursive: true })
  .map((f) => String(f))
  .filter((f) => f.endsWith('.html'))

// A href resolves if it maps to an existing built file. Directory routes emit
// `<route>/index.html`; assets resolve to the file directly.
function resolves(urlPath) {
  // Strip the base prefix → path relative to DIST.
  let rel = urlPath.startsWith(`${BASE}/`) ? urlPath.slice(BASE.length) : urlPath
  rel = rel.replace(/^\/+/, '') // drop leading slash
  if (rel === '' || urlPath === `${BASE}/` || urlPath === BASE) {
    return fs.existsSync(path.join(DIST, 'index.html'))
  }
  const direct = path.join(DIST, rel)
  if (fs.existsSync(direct) && fs.statSync(direct).isFile()) return true
  // Directory route → index.html (trailing slash already normalized away above).
  if (fs.existsSync(path.join(DIST, rel, 'index.html'))) return true
  if (!path.extname(rel) && fs.existsSync(path.join(DIST, `${rel}.html`))) return true
  return false
}

const HREF = /\shref="([^"]+)"/g
let failures = 0
const broken = new Map() // url → Set(source files)

const ORIGIN = 'https://docs.invalid' // dummy origin for relative-href resolution

for (const rel of htmlFiles) {
  const relUrl = rel.replace(/\\/g, '/')
  // The served URL of this page: BASE + path, with the trailing `index.html`
  // dropped for directory routes (`getting-started/quickstart/index.html` →
  // `/docs/getting-started/quickstart/`). Relative hrefs resolve against it.
  const pageUrl = new URL(`${BASE}/${relUrl.replace(/index\.html$/, '')}`, ORIGIN)
  const html = fs.readFileSync(path.join(DIST, rel), 'utf8')
  for (const m of html.matchAll(HREF)) {
    const raw = m[1]
    // External, protocol-relative, mailto, tel, pure anchors, data: → skip.
    if (/^([a-z]+:)?\/\//i.test(raw) || /^(mailto:|tel:|data:|#)/i.test(raw)) continue
    let resolved
    try {
      resolved = new URL(raw, pageUrl) // resolves both absolute (/docs/…) and relative (../x)
    } catch {
      continue
    }
    const p = decodeURIComponent(resolved.pathname)
    // Gate ONLY our docs surface — `=== BASE` or `BASE/` (so `/docsx` is excluded,
    // and main-site links like `/methodology` are out of this gate's scope).
    if (p !== BASE && !p.startsWith(`${BASE}/`)) continue
    if (!resolves(p)) {
      if (!broken.has(p)) broken.set(p, new Set())
      broken.get(p).add(relUrl)
    }
  }
}

for (const [url, sources] of broken) {
  failures++
  console.error(
    `::error::[docs-links] broken internal link ${url} — referenced by: ${[...sources].join(', ')}`
  )
}

if (failures > 0) {
  console.error(
    `\n[docs-links] ${failures} broken internal link(s) across ${htmlFiles.length} page(s).`
  )
  process.exit(1)
}
console.log(`[docs-links] ${htmlFiles.length} page(s) — no broken internal links ✓`)
