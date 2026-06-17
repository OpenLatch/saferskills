#!/usr/bin/env node
/* generate-llms-txt.cjs — emit /docs/llms.txt + /docs/llms-full.txt (I-06 Plan 3).
 *
 * Two machine-readable manifests for LLM consumers, auto-generated at every
 * build (NEVER hand-curated, NEVER committed — emitted into the gitignored
 * `dist/client/docs/`):
 *   • llms.txt      — the llms.txt spec shape (https://llmstxt.org): an H1, a
 *                     blockquote summary, then one `## Section` list per IA group
 *                     of `- [title](url): description` links.
 *   • llms-full.txt — every page's body concatenated as plain Markdown, so a model
 *                     can ingest the whole site in one fetch.
 *
 * Source of truth is the content frontmatter under `src/content/docs/**`, read
 * directly (no built-HTML parse, no dependency) so the output is correct
 * regardless of Astro's `base`/`outDir` layout. Files land directly in
 * `dist/client/docs/` (the native docs output), so they are served at
 * `/docs/llms.txt` + `/docs/llms-full.txt`.
 *
 * Pipeline order (build): astro build → THIS → build-pagefind. */
'use strict'
const fs = require('node:fs')
const path = require('node:path')

const WEBAPP = path.resolve(__dirname, '..')
const CONTENT = path.join(WEBAPP, 'src', 'content', 'docs')
const OUT_DIR = path.join(WEBAPP, 'dist', 'client', 'docs')
const SITE = 'https://saferskills.ai'

// IA section order + labels — KEEP IN LOCKSTEP with the mirror in
// src/lib/docs/sections.ts (a .cjs can't import the .ts). A directory not listed
// here still ships under its own title-cased heading.
const SECTIONS = [
  ['getting-started', 'Getting Started'],
  ['concepts', 'Concepts'],
  ['find-and-verify', 'Find & Verify'],
  ['agent-scan', 'Agent Scan'],
  ['install', 'Install (CLI)'],
  ['for-authors', 'For Authors'],
  ['security-and-methodology', 'Security & Methodology'],
  ['reference', 'Reference'],
]

/** Recursively collect every .md/.mdx under CONTENT (sorted, deterministic). */
function walk(dir) {
  const out = []
  for (const entry of fs
    .readdirSync(dir, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name))) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) out.push(...walk(full))
    else if (/\.mdx?$/.test(entry.name)) out.push(full)
  }
  return out
}

/** Split a page into { frontmatter-string, body } without a YAML dependency. */
function splitFrontmatter(raw) {
  const m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/)
  return m ? { fm: m[1], body: m[2].trim() } : { fm: '', body: raw.trim() }
}

/** Pull a scalar frontmatter value (handles quoted + bare), else ''. */
function fmField(fm, key) {
  const m = fm.match(new RegExp(`^${key}:\\s*(.+?)\\s*$`, 'm'))
  if (!m) return ''
  return m[1].replace(/^['"]|['"]$/g, '').trim()
}

/** content/docs path → canonical site URL (Starlight trailing-slash routes). */
function toUrl(file) {
  let rel = path
    .relative(CONTENT, file)
    .replace(/\\/g, '/')
    .replace(/\.mdx?$/, '')
  if (rel === 'index') return `${SITE}/docs/`
  rel = rel.replace(/\/index$/, '')
  return `${SITE}/docs/${rel}/`
}

const pages = walk(CONTENT).map((file) => {
  const { fm, body } = splitFrontmatter(fs.readFileSync(file, 'utf8'))
  const rel = path.relative(CONTENT, file).replace(/\\/g, '/')
  const section = rel.includes('/') ? rel.split('/')[0] : '' // '' = root index
  return {
    url: toUrl(file),
    title: fmField(fm, 'title') || rel,
    description: fmField(fm, 'description'),
    section,
    body,
  }
})

// ---- llms.txt (spec-shaped link index) ------------------------------------
const root = pages.find((p) => p.section === '')
const summary =
  root?.description ||
  'Every AI capability, independently scanned. The SaferSkills documentation: find and verify AI capabilities, install with confidence, and read the methodology behind every deterministic scan.'

const lines = ['# SaferSkills Documentation', '', `> ${summary}`, '']
for (const [dir, label] of SECTIONS) {
  const group = pages
    .filter((p) => p.section === dir)
    .sort((a, b) =>
      a.url.endsWith('/docs/' + dir + '/')
        ? -1
        : b.url.endsWith('/docs/' + dir + '/')
          ? 1
          : a.url.localeCompare(b.url)
    )
  if (group.length === 0) continue
  lines.push(`## ${label}`, '')
  for (const p of group) {
    lines.push(`- [${p.title}](${p.url})${p.description ? `: ${p.description}` : ''}`)
  }
  lines.push('')
}
const llmsTxt = `${lines.join('\n').trim()}\n`

// ---- llms-full.txt (full-content concatenation) ---------------------------
const ordered = [
  ...(root ? [root] : []),
  ...SECTIONS.flatMap(([dir]) =>
    pages.filter((p) => p.section === dir).sort((a, b) => a.url.localeCompare(b.url))
  ),
]
const fullBlocks = ordered.map((p) => `# ${p.title}\nSource: ${p.url}\n\n${p.body}`)
const llmsFull = `${fullBlocks.join('\n\n---\n\n').trim()}\n`

fs.mkdirSync(OUT_DIR, { recursive: true })
fs.writeFileSync(path.join(OUT_DIR, 'llms.txt'), llmsTxt)
fs.writeFileSync(path.join(OUT_DIR, 'llms-full.txt'), llmsFull)
console.log(
  `[generate-llms-txt] wrote dist/client/docs/llms.txt (${pages.length} pages indexed) + llms-full.txt (${llmsFull.length} bytes)`
)
