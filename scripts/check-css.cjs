#!/usr/bin/env node
/**
 * check-css.cjs — CSS token-discipline guardrail.
 *
 * Mirrors validate-schemas.cjs. Run by the `validate` CI lane (and optionally a
 * pre-commit hook). Enforces three rules on the hand-written CSS so the
 * design-system token contract can't silently regress:
 *
 *   (b) No `var(--token, #hex)` fallback literals — the token is always defined
 *       in ui/styles/tokens.css; a stale hex fallback never renders but lies
 *       about the real color and hides dark-mode bugs. Repo-wide.
 *   (c) No references to undefined custom properties — catches typos like the
 *       old `var(--bg-paper)` / `var(--ink)` / `var(--bg-dotgrid-ink)` that fell
 *       through to a wrong literal or to nothing. Repo-wide.
 *   (a) No bare raw `#rrggbb` literals in the cleaned "shell" page files
 *       (catalog / scan-progress / scan-report / scan-submit) — those must use
 *       tokens. #000/#fff inside mask/url() compositing are exempt. The ported
 *       homepage mockup (page-home.css) and the DS file (components.css, which
 *       carries the intentional terminal-ANSI palette) are out of rule (a) scope
 *       — see .claude/rules/design-system.md § CSS token discipline.
 *
 * See .claude/rules/design-system.md.
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')

// Files scanned for rules (b) + (c).
const SCAN_GLOBS = ['ui/styles', 'webapp/src/styles']
// Files subject to rule (a) — bare-hex ban. Token discipline was restored here.
const SHELL_FILES = [
  'webapp/src/styles/page-catalog.css',
  'webapp/src/styles/page-scan-progress.css',
  'webapp/src/styles/page-scan-report.css',
  'webapp/src/styles/page-scan-submit.css',
  'webapp/src/styles/page-agent-report.css',
  'webapp/src/styles/page-agent-directory.css',
  'webapp/src/styles/page-docs.css',
]
// Custom properties set at runtime (never declared with `:` in CSS) — allow.
// `--wb-frac`: per-row fill fraction set inline by the WeightBars molecule
// (`style={{ '--wb-frac': r.weight / 100 }}`), consumed as scaleX(var(--wb-frac, 1)).
// `--dz-frac`: DropZone upload progress fraction set inline by the DropZone
// molecule (`style={{ '--dz-frac': progress }}`), consumed as scaleX(var(--dz-frac, 0)).
// `--dz-i`: DropZone file-card index set inline (`style={{ '--dz-i': i }}`),
// consumed as the per-card stagger `animation-delay: calc(var(--dz-i, 0) * 50ms)`.
// `--cat-row-i`: catalog row index set inline by CatalogResultsList
// (`style={{ '--cat-row-i': idx }}`), consumed as the per-row entrance stagger
// `animation-delay: calc(var(--cat-row-i, 0) * 45ms)`.
const RUNTIME_VARS = new Set([
  '--search-dropdown-max-h',
  '--wb-frac',
  '--dz-frac',
  '--dz-i',
  '--cat-row-i',
])

function listCss(dir) {
  const abs = path.join(ROOT, dir)
  if (!fs.existsSync(abs)) return []
  return fs
    .readdirSync(abs)
    .filter((f) => f.endsWith('.css'))
    .map((f) => path.join(dir, f).replace(/\\/g, '/'))
}

// Strip block comments but preserve newlines, so line numbers stay accurate for
// the violation scan AND a multi-line comment can't smuggle a fake var()/hex past
// the per-line rules.
const stripComments = (css) => css.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))

// Read each file once; both passes below consume the cached, comment-stripped text.
const sources = [...new Set(SCAN_GLOBS.flatMap(listCss))].map((rel) => ({
  rel,
  code: stripComments(fs.readFileSync(path.join(ROOT, rel), 'utf8')),
}))

// Build the set of defined custom properties from every declaration across all
// scanned CSS (tokens.css, globals.css, components.css + page files). A custom
// property declared anywhere (incl. locally on a selector) counts as defined.
const defined = new Set(RUNTIME_VARS)
for (const { code } of sources) {
  for (const m of code.matchAll(/(--[A-Za-z0-9-]+)\s*:/g)) defined.add(m[1])
}

let failures = 0
const fail = (rel, line, msg) => {
  failures++
  console.error(`::error file=${rel},line=${line}::[check-css] ${msg}`)
}

for (const { rel, code: fileCode } of sources) {
  const isShell = SHELL_FILES.includes(rel)
  fileCode.split('\n').forEach((code, i) => {
    const ln = i + 1
    if (!code.trim()) return

    // (b) var(--token, ...#hex...) fallback literal
    for (const m of code.matchAll(/var\(\s*(--[A-Za-z0-9-]+)\s*,[^;]*?#[0-9a-fA-F]{3,8}/g)) {
      fail(
        rel,
        ln,
        `rule (b): drop the stale hex fallback in \`var(${m[1]}, …)\` — tokens are always defined in tokens.css.`
      )
    }

    // (c) reference to an undefined custom property
    for (const m of code.matchAll(/var\(\s*(--[A-Za-z0-9-]+)/g)) {
      if (!defined.has(m[1])) {
        fail(
          rel,
          ln,
          `rule (c): \`var(${m[1]})\` references an undefined token. Define it in tokens.css or fix the name.`
        )
      }
    }

    // (a) bare raw hex in the cleaned shell files
    if (isShell) {
      const withoutUrls = code.replace(/url\([^)]*\)/g, '')
      for (const m of withoutUrls.matchAll(/#[0-9a-fA-F]{3,8}\b/g)) {
        const hex = m[0].toLowerCase()
        if (hex === '#000' || hex === '#fff' || hex === '#000000' || hex === '#ffffff') continue
        fail(
          rel,
          ln,
          `rule (a): raw hex \`${m[0]}\` — use a token (var(--…)). Shell page CSS must be token-only.`
        )
      }
    }
  })
}

if (failures > 0) {
  console.error(
    `\n[check-css] ${failures} violation(s). See .claude/rules/design-system.md § CSS token discipline.`
  )
  process.exit(1)
}
console.log(`[check-css] ${sources.length} CSS files clean ✓ (${defined.size} tokens defined)`)
