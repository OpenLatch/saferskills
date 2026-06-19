#!/usr/bin/env node
/**
 * validate-outbound-allowlist.cjs — Outbound HTTP host guard.
 *
 * Mirrors check-css.cjs. Run by the `validate` CI lane (and optionally a
 * pre-commit hook). Enforces the closed outbound-host contract documented in
 * .claude/rules/security.md § Public-input handling #2.
 *
 * The allowlist is SELF-DERIVING: it is the union of every YAML `hosts:` list
 * under config/sources/*.yaml (the single source of truth — same set the
 * generated source_registry.ALL_HOSTS exposes to the backend). There is no
 * hand-maintained host set in this script. Adding a provider = adding its YAML;
 * its declared hosts join the allowlist automatically.
 *
 * The single check is the real guard: an adapter `.py` file that fetches a
 * host NOT declared in any YAML `hosts:` list fails the lane.
 *
 *   - YAML config files (config/sources/*.yaml) are parsed to BUILD the
 *     allowlist (the union of every `hosts:` list). They are not validated
 *     against it — a YAML host is in the allowlist by construction.
 *   - Python adapter files (services/api/app/ingestion/sources/*.py): only
 *     lines that are part of an HTTP fetch call (`await client.get(`,
 *     `client.get(`, `await client.post(`, …) are scanned for URL literals.
 *     Data-field assignments like `github_url = f"https://github.com/{org}/…"`
 *     are intentionally excluded — those are catalog metadata values, not
 *     outbound fetches. Regex patterns and constant-prefix strings too. Every
 *     fetched host must appear in some YAML `hosts:` list.
 *
 * See .claude/rules/security.md § Public-input handling #2 and
 * .claude/rules/ingestion.md § Outbound allowlist coupling.
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')

// ---------------------------------------------------------------------------
// File discovery helpers
// ---------------------------------------------------------------------------

function listFiles(dir, ext) {
  const abs = path.join(ROOT, dir)
  if (!fs.existsSync(abs)) return []
  return fs
    .readdirSync(abs)
    .filter((f) => f.endsWith(ext))
    .map((f) => path.join(dir, f).replace(/\\/g, '/'))
}

// ---------------------------------------------------------------------------
// Host extraction — Python source files (fetch-call lines only)
// ---------------------------------------------------------------------------

/**
 * Scan only lines that are part of an HTTP client fetch call.
 * This avoids false-positives from:
 *   - Data-value f-strings: `github_url = f"https://github.com/{org}/{repo}"`
 *   - Regex/constant prefix strings: `_GITHUB_URL_PREFIXES = ("https://github.com/", ...)`
 *   - Docstrings and comments describing external URLs
 *
 * Returns [{host, line}] pairs for every URL found on a fetch-call line.
 */
function extractFetchHostsFromPython(code) {
  const results = []
  // Patterns that indicate an actual outbound HTTP request in adapter code.
  // Covers: `await client.get(`, `await client.post(`, `r = await client.get(`,
  // `async for raw in self._iter_*(client, url` etc. but the simplest reliable
  // signal is `client.get(` / `client.post(` on the same line as a URL literal.
  // Also recognizes curl_cffi session fetches (`session.get(` / `.request(`) used
  // by the ScrapingAdapter tier-1 path (best-effort — the runtime
  // `allowlist.assert_host_allowed` is the real guard for variable-URL fetches).
  const FETCH_RE =
    /\bawait\s+(client|session)\.(get|post|put|patch|delete|head|request)\s*\(|\.(get|post|put|patch|delete|head|request)\s*\(\s*["'f]/

  code.split('\n').forEach((rawLine, i) => {
    const ln = i + 1
    const noComment = rawLine.replace(/#.*$/, '')
    if (!FETCH_RE.test(noComment)) return
    for (const m of noComment.matchAll(/https?:\/\/([a-z0-9][a-z0-9.-]+)/gi)) {
      results.push({ host: m[1].toLowerCase(), line: ln })
    }
  })
  return results
}

// ---------------------------------------------------------------------------
// Host extraction — YAML config files (hosts: list)
// ---------------------------------------------------------------------------

/**
 * Extract entries from a `hosts:` list block in YAML.
 * Handles both inline `hosts: [a, b]` and block-sequence `hosts:\n  - a`.
 * Returns [{host, line}] pairs.
 */
function extractHostsFromYaml(code) {
  const results = []
  const lines = code.split('\n')
  let inHostsBlock = false

  lines.forEach((line, i) => {
    const ln = i + 1
    const trimmed = line.trim()

    // Detect `hosts: [a, b, c]` inline array
    const inlineMatch = trimmed.match(/^hosts\s*:\s*\[([^\]]+)\]/)
    if (inlineMatch) {
      inHostsBlock = false
      for (const entry of inlineMatch[1].split(',')) {
        const host = entry.trim().replace(/^['"]|['"]$/g, '')
        if (host) results.push({ host: host.toLowerCase(), line: ln })
      }
      return
    }

    // Detect `hosts:` block-sequence header (with nothing after the colon)
    if (trimmed === 'hosts:') {
      inHostsBlock = true
      return
    }

    // A `hosts: value` line (not a block sequence) — not our pattern, reset
    if (trimmed.startsWith('hosts:') && trimmed !== 'hosts:') {
      inHostsBlock = false
      return
    }

    // Inside a hosts block: each `  - <value>` is a host entry
    if (inHostsBlock) {
      const itemMatch = trimmed.match(/^-\s+(.+)$/)
      if (itemMatch) {
        const host = itemMatch[1].trim().replace(/^['"]|['"]$/g, '')
        if (host) results.push({ host: host.toLowerCase(), line: ln })
      } else if (trimmed && !trimmed.startsWith('#')) {
        // Non-list, non-comment line ends the hosts block
        inHostsBlock = false
      }
    }
  })

  return results
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const PY_DIR = 'services/api/app/ingestion/sources'
const YAML_DIR = 'services/api/app/ingestion/config/sources'

const pyFiles = listFiles(PY_DIR, '.py')
const yamlFiles = listFiles(YAML_DIR, '.yaml')

// Build the allowlist from the union of every YAML `hosts:` list — the single
// source of truth (mirrors generated source_registry.ALL_HOSTS).
const ALLOWED_HOSTS = new Set()
for (const rel of yamlFiles) {
  const code = fs.readFileSync(path.join(ROOT, rel), 'utf8')
  for (const { host } of extractHostsFromYaml(code)) {
    ALLOWED_HOSTS.add(host)
  }
}

let failures = 0
const fail = (rel, line, host) => {
  failures++
  console.error(
    `::error file=${rel},line=${line}::[validate-outbound-allowlist] ` +
      `host "${host}" is fetched by an adapter but declared in no ` +
      `config/sources/*.yaml \`hosts:\` list. Add it to the provider's YAML ` +
      `(see security.md § Public-input handling #2).`
  )
}

// Check (A) is the real guard: every host an adapter `.py` actually fetches
// must be declared in some YAML `hosts:` list (= the self-derived allowlist).
// There is no check (B): a YAML host is in the allowlist by construction, so
// validating the YAMLs against it would be tautological.
for (const rel of pyFiles) {
  const code = fs.readFileSync(path.join(ROOT, rel), 'utf8')
  for (const { host, line } of extractFetchHostsFromPython(code)) {
    if (!ALLOWED_HOSTS.has(host)) {
      fail(rel, line, host)
    }
  }
}

if (failures > 0) {
  console.error(
    `\n[validate-outbound-allowlist] ${failures} violation(s). ` +
      `See .claude/rules/security.md § Public-input handling #2.`
  )
  process.exit(1)
}

const totalFiles = pyFiles.length + yamlFiles.length
console.log(
  `[validate-outbound-allowlist] ${totalFiles} file(s) clean ✓ ` +
    `(${pyFiles.length} py, ${yamlFiles.length} yaml; ${ALLOWED_HOSTS.size} hosts in allowlist)`
)
