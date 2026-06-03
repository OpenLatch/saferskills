#!/usr/bin/env node
/**
 * generate-ingestion-sources.cjs — STEP 0 of the codegen pipeline.
 *
 * The ingestion provider directory is the single source of truth:
 *   services/api/app/ingestion/config/sources/*.yaml
 *
 * This generator reads every YAML and emits / rewrites three artifacts so that
 * adding one YAML (+ an optional adapter module) is the only hand edit needed
 * to onboard a new provider — the source-name enum, the registry-id enum, and
 * the host allowlist all flow from here:
 *
 *   1. services/api/app/ingestion/config/generated/source_registry.py
 *      (+ __init__.py) — SOURCE_NAMES / REGISTRY_IDS / SOURCE_HOSTS / ALL_HOSTS.
 *
 *   2. schemas/ingestion-event.schema.json   → source.enum            = sorted SOURCE_NAMES
 *      schemas/catalog-item.schema.json       → …registryId.enum       = sorted(REGISTRY_IDS ∪ fixed non-adapter set)
 *      Surgical in-place enum-array rewrite (the surrounding hand-authored
 *      formatting is preserved byte-for-byte) so the no-change run is a no-op
 *      and the CI `validate` drift gate stays quiet.
 *
 * Must run BEFORE `validate` + `generate-pydantic` (which consume the rewritten
 * schema JSON) and BEFORE `generate-openapi` (which imports the FastAPI app →
 * loader.py → the Python module emitted here). Wired as step 0 in
 * scripts/_run-generators.cjs.
 *
 * See .claude/rules/ingestion.md § Adding a provider +
 *     .claude/rules/schema-driven-development.md.
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')
const YAML = require('yaml')

const ROOT = path.resolve(__dirname, '..')
const SOURCES_DIR = path.join(ROOT, 'services', 'api', 'app', 'ingestion', 'config', 'sources')
const GENERATED_DIR = path.join(ROOT, 'services', 'api', 'app', 'ingestion', 'config', 'generated')
const INGESTION_EVENT_SCHEMA = path.join(ROOT, 'schemas', 'ingestion-event.schema.json')
const CATALOG_ITEM_SCHEMA = path.join(ROOT, 'schemas', 'catalog-item.schema.json')

// The fixed non-adapter registry ids — endpoints / attributions that are never
// crawled providers, so they have no YAML. Kept in sync with the I-3.5 contract
// (catalog-item.schema.json registryId description).
const FIXED_REGISTRY_IDS = ['user_submission', 'vendor_verified', 'upload']

// ---------------------------------------------------------------------------
// 1. Read every YAML
// ---------------------------------------------------------------------------

function loadSources() {
  const files = fs
    .readdirSync(SOURCES_DIR)
    .filter((f) => f.endsWith('.yaml'))
    .sort()
  const sources = []
  for (const file of files) {
    const raw = fs.readFileSync(path.join(SOURCES_DIR, file), 'utf8')
    const doc = YAML.parse(raw)
    if (!doc || typeof doc.name !== 'string') {
      throw new Error(`[generate-ingestion-sources] ${file}: missing 'name'`)
    }
    if (!Array.isArray(doc.hosts) || doc.hosts.length === 0) {
      throw new Error(`[generate-ingestion-sources] ${file}: missing non-empty 'hosts'`)
    }
    sources.push({
      file,
      name: doc.name,
      registryId: typeof doc.registry_id === 'string' ? doc.registry_id : doc.name,
      hosts: doc.hosts.map((h) => String(h)),
    })
  }
  return sources
}

// ---------------------------------------------------------------------------
// 2. Emit the generated Python module
// ---------------------------------------------------------------------------

// Emit one quoted, comma-suffixed Python literal per item, each on its own line
// at the given indent. Used for every frozenset/dict body below.
function pyLiterals(items, indent) {
  return items.map((v) => `${indent}${JSON.stringify(v)},`).join('\n')
}

function emitPythonModule(sources) {
  const sourceNames = sources.map((s) => s.name).sort()
  const registryIds = [...new Set(sources.map((s) => s.registryId))].sort()

  const sourceNamesBody = pyLiterals(sourceNames, '        ')
  const registryIdsBody = pyLiterals(registryIds, '        ')

  const hostsEntries = sourceNames
    .map((name) => {
      const hosts = [...new Set(sources.find((s) => s.name === name).hosts)].sort()
      const hostsBody = pyLiterals(hosts, '            ')
      return `    ${JSON.stringify(name)}: frozenset(\n        {\n${hostsBody}\n        }\n    ),`
    })
    .join('\n')

  const allHosts = [...new Set(sources.flatMap((s) => s.hosts))].sort()
  const allHostsBody = pyLiterals(allHosts, '        ')

  return `# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate-ingestion-sources.cjs)
"""Generated provider registry — derived from config/sources/*.yaml.

The YAML directory is the single source of truth for ingestion providers. This
module exposes the closed sets consumed across the backend (loader cross-check,
SSRF host allowlist) and is regenerated whenever a YAML is added or changed.
"""

from __future__ import annotations

# Every provider 'name' (the ingestion_events.source / crawler_cursors.source
# closed enum). Includes disabled Phase-B placeholders so the wire enum is stable.
SOURCE_NAMES: frozenset[str] = frozenset(
    {
${sourceNamesBody}
    }
)

# Every provider 'registry_id' (defaults to name) — the item_sources.registry_id
# adapter values, before the fixed non-adapter set (user_submission/upload/…).
REGISTRY_IDS: frozenset[str] = frozenset(
    {
${registryIdsBody}
    }
)

# Per-source allowlisted outbound hosts (the YAML 'hosts:' list).
SOURCE_HOSTS: dict[str, frozenset[str]] = {
${hostsEntries}
}

# Union of every provider's hosts — the closed outbound SSRF allowlist.
ALL_HOSTS: frozenset[str] = frozenset(
    {
${allHostsBody}
    }
)
`
}

// ---------------------------------------------------------------------------
// 3. Surgical enum-array rewrite in the hand-authored schema JSON
// ---------------------------------------------------------------------------

/**
 * Replace the string-enum array that follows the first `"<propName>":` key,
 * preserving all surrounding formatting + indentation. Returns the new text.
 */
function rewriteEnumArray(text, propName, values) {
  const propMarker = `"${propName}":`
  const propIdx = text.indexOf(propMarker)
  if (propIdx === -1) throw new Error(`property "${propName}" not found`)

  const enumIdx = text.indexOf('"enum":', propIdx)
  if (enumIdx === -1) throw new Error(`"enum" not found after "${propName}"`)

  const open = text.indexOf('[', enumIdx)
  const close = text.indexOf(']', open) // enum of strings — no nested arrays
  if (open === -1 || close === -1) throw new Error(`enum brackets not found for "${propName}"`)

  // Indentation of the `"enum":` line → items are +2 spaces, closing `]` aligns with `"enum":`.
  const lineStart = text.lastIndexOf('\n', enumIdx) + 1
  const enumIndent = text.slice(lineStart, enumIdx).match(/^\s*/)[0]
  const itemIndent = `${enumIndent}  `

  const body = values.map((v) => `${itemIndent}${JSON.stringify(v)}`).join(',\n')
  const replacement = `[\n${body}\n${enumIndent}]`

  return text.slice(0, open) + replacement + text.slice(close + 1)
}

function writeIfChanged(file, next, label) {
  const prev = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null
  if (prev === next) {
    console.log(`  · ${label} unchanged`)
    return
  }
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, next, 'utf8')
  console.log(`  ✎ ${label} written`)
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const sources = loadSources()
console.log(`[generate-ingestion-sources] ${sources.length} provider YAML(s) read`)

// (1) Python module + package marker.
const initFile = path.join(GENERATED_DIR, '__init__.py')
const moduleFile = path.join(GENERATED_DIR, 'source_registry.py')
writeIfChanged(
  initFile,
  '# DO NOT EDIT — regenerate via: pnpm run generate\n"""Generated ingestion provider registry."""\n',
  'config/generated/__init__.py'
)
writeIfChanged(moduleFile, emitPythonModule(sources), 'config/generated/source_registry.py')

// (2) Schema enum arrays.
const sourceNames = sources.map((s) => s.name).sort()
const registryIds = [
  ...new Set([...sources.map((s) => s.registryId), ...FIXED_REGISTRY_IDS]),
].sort()

const eventText = fs.readFileSync(INGESTION_EVENT_SCHEMA, 'utf8')
writeIfChanged(
  INGESTION_EVENT_SCHEMA,
  rewriteEnumArray(eventText, 'source', sourceNames),
  'schemas/ingestion-event.schema.json (source.enum)'
)

const catalogText = fs.readFileSync(CATALOG_ITEM_SCHEMA, 'utf8')
writeIfChanged(
  CATALOG_ITEM_SCHEMA,
  rewriteEnumArray(catalogText, 'registryId', registryIds),
  'schemas/catalog-item.schema.json (registryId.enum)'
)

console.log('[generate-ingestion-sources] done ✓')
