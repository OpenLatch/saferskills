#!/usr/bin/env node
/* validate-docs-frontmatter.cjs — Zod-equivalent frontmatter gate for the docs
 * (I-06 Plan 1, D-8). Mirrors the build-time `docsSchema` extension in
 * webapp/docs/content.config.ts, but as a fast standalone CI lane that fails a
 * PR with a precise file/line before the (slower) Starlight build runs.
 *
 * Contract (the hard gate): every page under webapp/docs/content/docs carries
 *   - title       (required, non-empty string)
 *   - description  (required, non-empty string)   ← SEO + meta
 *   - author       (optional, string)             ← byline (Plan 2 SEO-D3)
 *   - updated      (optional, YYYY-MM-DD date)
 *
 * Run by the `docs-build` CI lane and available locally:
 *   node scripts/validate-docs-frontmatter.cjs
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')
const YAML = require('yaml')

const ROOT = path.resolve(__dirname, '..')
const DOCS = path.join(ROOT, 'webapp', 'docs', 'content', 'docs')

if (!fs.existsSync(DOCS)) {
  console.error(`[docs-frontmatter] content dir not found: ${DOCS}`)
  process.exit(1)
}

const files = fs
  .readdirSync(DOCS, { recursive: true })
  .map((f) => String(f))
  .filter((f) => f.endsWith('.md') || f.endsWith('.mdx'))

let failures = 0
const fail = (rel, msg) => {
  failures++
  console.error(`::error file=${rel}::[docs-frontmatter] ${msg}`)
}

// Frontmatter block must be the first thing in the file: ---\n...\n---
const FM = /^---\r?\n([\s\S]*?)\r?\n---/

for (const rel of files) {
  const abs = path.join(DOCS, rel)
  const gitRel = path.relative(ROOT, abs).replace(/\\/g, '/')
  const src = fs.readFileSync(abs, 'utf8')
  const m = src.match(FM)
  if (!m) {
    fail(gitRel, 'missing frontmatter block (--- … ---) at the top of the file.')
    continue
  }
  let data
  try {
    data = YAML.parse(m[1]) || {}
  } catch (e) {
    fail(gitRel, `frontmatter is not valid YAML: ${e.message}`)
    continue
  }

  if (typeof data.title !== 'string' || !data.title.trim()) {
    fail(gitRel, '`title` is required and must be a non-empty string.')
  }
  if (typeof data.description !== 'string' || !data.description.trim()) {
    fail(gitRel, '`description` is required and must be a non-empty string.')
  }
  if ('author' in data && typeof data.author !== 'string') {
    fail(gitRel, '`author` must be a string when present.')
  }
  if ('updated' in data) {
    const u = data.updated
    if (u instanceof Date) {
      // YAML only parses a *valid* ISO date into a Date, so this is already good.
      if (Number.isNaN(u.getTime())) fail(gitRel, '`updated` is not a valid date.')
    } else if (typeof u === 'string') {
      // Strict YYYY-MM-DD + round-trip so `2026-02-31` / `06/16/2026` are rejected.
      const ok =
        /^\d{4}-\d{2}-\d{2}$/.test(u) && new Date(`${u}T00:00:00Z`).toISOString().slice(0, 10) === u
      if (!ok) fail(gitRel, '`updated` must be a real calendar date in YYYY-MM-DD form.')
    } else {
      fail(gitRel, '`updated` must be a date (YYYY-MM-DD).')
    }
  }
}

if (failures > 0) {
  console.error(`\n[docs-frontmatter] ${failures} violation(s) across ${files.length} page(s).`)
  process.exit(1)
}
console.log(`[docs-frontmatter] ${files.length} page(s) clean ✓`)
