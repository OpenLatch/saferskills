#!/usr/bin/env node
/**
 * validate-outbound-allowlist.cjs — Outbound HTTP host guard.
 *
 * Mirrors check-css.cjs. Run by the `validate` CI lane (and optionally a
 * pre-commit hook). Enforces the closed outbound-host contract documented in
 * .claude/rules/security.md § Public-input handling #2.
 *
 * Two complementary checks:
 *
 *   (A) Python adapter files (services/api/app/ingestion/sources/*.py):
 *       Only lines that are part of an HTTP fetch call (lines containing
 *       `await client.get(`, `client.get(`, `await client.post(`, etc.) are
 *       scanned for URL literals. Data-field assignments like
 *       `github_url = f"https://github.com/{org}/{repo}"` are intentionally
 *       excluded — those are catalog metadata values, not outbound fetches.
 *       Regex patterns and constant-prefix strings are also excluded.
 *
 *   (B) YAML config files (services/api/app/ingestion/config/sources/*.yaml):
 *       Every entry in a `hosts:` list is checked against the allowlist.
 *       The YAML `hosts:` list is the canonical declaration of which hosts
 *       an adapter is permitted to reach at the transport layer.
 *
 * Every discovered host must be a member of ALLOWED_HOSTS. Any host outside
 * the set is printed with its origin and the script exits 1.
 *
 * See .claude/rules/security.md § Public-input handling #2 and
 * .claude/rules/ingestion.md § Outbound allowlist coupling.
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')

// The 16 hosts in the closed outbound allowlist
// (security.md § Public-input handling #2 + ingestion.md § Outbound allowlist coupling).
const ALLOWED_HOSTS = new Set([
  // GitHub — scan tarball fetches + GitHub App token exchange
  'api.github.com',
  'raw.githubusercontent.com',
  // npm — replication + registry
  'api.npmjs.org',
  'replicate.npmjs.com',
  'registry.npmjs.com',
  // PyPI
  'pypi.org',
  // MCP aggregators
  'registry.modelcontextprotocol.io',
  'mcp.so',
  'smithery.ai',
  'glama.ai',
  'pulsemcp.com',
  // Skill aggregators
  'clawhub.dev',
  'skillsmp.com',
  'skills.sh',
  'claudeskills.info',
  'skillhub.club',
])

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
  const FETCH_RE = /\bawait\s+client\.(get|post|put|patch|delete|head)\s*\(|\.get\s*\(\s*["'f]/

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

let failures = 0
const fail = (rel, line, host) => {
  failures++
  console.error(
    `::error file=${rel},line=${line}::[validate-outbound-allowlist] ` +
      `host "${host}" is not in the closed outbound allowlist. ` +
      `Add it to security.md § Public-input handling #2 and ALLOWED_HOSTS in this script.`
  )
}

for (const rel of pyFiles) {
  const code = fs.readFileSync(path.join(ROOT, rel), 'utf8')
  for (const { host, line } of extractFetchHostsFromPython(code)) {
    if (!ALLOWED_HOSTS.has(host)) {
      fail(rel, line, host)
    }
  }
}

for (const rel of yamlFiles) {
  const code = fs.readFileSync(path.join(ROOT, rel), 'utf8')
  for (const { host, line } of extractHostsFromYaml(code)) {
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
