#!/usr/bin/env node
/**
 * generate-agent-pack.cjs — agent-scan behavioral pack emission from rubric/AGENT/.
 *
 * Step #9 of the codegen pipeline (I-5.5, D-5.5-14). Reads every
 * `rubric/AGENT/AS-NN-<slug>.md`, parses YAML frontmatter, validates against
 * `schemas/agent-pack-test.schema.json` (ajv), hard-fails on any invalid file or
 * unknown `frameworks` code, sorts by testId, and emits TWO artifacts:
 *
 *   1. `webapp/src/generated/agent-pack/practice.json` — the PUBLIC practice pack
 *      for I-5.6 `/methodology`. Canaries scrubbed: no `promptTemplate`, no
 *      `mockTools` (those carry `{{CANARY}}` placeholders / planted directives),
 *      only a sanitized human `detectionDescription`.
 *   2. `services/api/app/generated/agent_pack.json` — the FULL backend source the
 *      server reads (`app/agent_scan/pack.py`) to assemble each per-run signed
 *      pack: detection rules + prompt templates (placeholders intact) + mock-tool
 *      schemas + honeytoken fixtures.
 *
 * `packVersion` is a date-version stamped from `git log -n1 -- rubric/AGENT/` so
 * the generated files only diff-flip when the pack actually changes (drift-gate
 * friendly). The component methodology generator (step 7) EXCLUDES `rubric/AGENT/`
 * — the two taxonomies never cross.
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')

const ROOT = path.resolve(__dirname, '..')
const AGENT_DIR = path.join(ROOT, 'rubric', 'AGENT')
const PACK_SCHEMA = path.join(ROOT, 'schemas', 'agent-pack-test.schema.json')
const WEBAPP_OUT_DIR = path.join(ROOT, 'webapp', 'src', 'generated', 'agent-pack')
const WEBAPP_OUT = path.join(WEBAPP_OUT_DIR, 'practice.json')
const BACKEND_OUT = path.join(ROOT, 'services', 'api', 'app', 'generated', 'agent_pack.json')

const PRACTICE_PACK_ID = 'saferskills-agent-practice'
const BACKEND_PACK_ID = 'saferskills-agent-baseline'

let yaml
try {
  yaml = require('yaml')
} catch {
  console.error('[agent-pack] `yaml` package missing. Run `pnpm install` at the repo root.')
  process.exit(2)
}

let Ajv2020
try {
  Ajv2020 = require('ajv/dist/2020').default
} catch {
  console.error('[agent-pack] `ajv` missing. Run `pnpm install` at the repo root.')
  process.exit(2)
}

// ─── Framework catalog (agent taxonomy) ───────────────────────────────────────
//
// The agent pack maps to OWASP LLM Top 10 (2025), OWASP Top 10 for Agentic
// Applications (ASI, 2026), and MITRE ATLAS. The component `FRAMEWORK_CATALOG`
// (generate-methodology.cjs) does NOT cover the ATLAS techniques / LLM05 / LLM09
// the agent tests use, so the AGENT pack carries its own catalog. We resolve only
// VERIFIABLE OWASP-LLM + corrected-ATLAS badge codes here; the ASI ids still ride
// in each test's raw `owasp` array (displayed as text), they are just not
// rendered as resolved badges (their 2026 per-risk slugs are not yet pinned).
// `resolveFrameworks` hard-fails on an unknown code (mirrors KNOWN_ENUMS).
const AGENT_FRAMEWORK_CATALOG = {
  'owasp-llm:llm01': {
    family: 'owasp-llm',
    id: 'LLM01',
    label: 'Prompt Injection',
    url: 'https://genai.owasp.org/llmrisk/llm01-prompt-injection/',
  },
  'owasp-llm:llm02': {
    family: 'owasp-llm',
    id: 'LLM02',
    label: 'Sensitive Information Disclosure',
    url: 'https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure/',
  },
  'owasp-llm:llm05': {
    family: 'owasp-llm',
    id: 'LLM05',
    label: 'Improper Output Handling',
    url: 'https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/',
  },
  'owasp-llm:llm06': {
    family: 'owasp-llm',
    id: 'LLM06',
    label: 'Excessive Agency',
    url: 'https://genai.owasp.org/llmrisk/llm062025-excessive-agency/',
  },
  'owasp-llm:llm07': {
    family: 'owasp-llm',
    id: 'LLM07',
    label: 'System Prompt Leakage',
    url: 'https://genai.owasp.org/llmrisk/llm072025-system-prompt-leakage/',
  },
  'owasp-llm:llm09': {
    family: 'owasp-llm',
    id: 'LLM09',
    label: 'Misinformation',
    url: 'https://genai.owasp.org/llmrisk/llm092025-misinformation/',
  },
  'mitre-atlas:AML.T0010': {
    family: 'mitre-atlas',
    id: 'AML.T0010',
    label: 'AI Supply Chain Compromise',
    url: 'https://atlas.mitre.org/techniques/AML.T0010',
  },
  'mitre-atlas:AML.T0048': {
    family: 'mitre-atlas',
    id: 'AML.T0048',
    label: 'External Harms',
    url: 'https://atlas.mitre.org/techniques/AML.T0048',
  },
  'mitre-atlas:AML.T0051': {
    family: 'mitre-atlas',
    id: 'AML.T0051',
    label: 'LLM Prompt Injection',
    url: 'https://atlas.mitre.org/techniques/AML.T0051',
  },
  'mitre-atlas:AML.T0053': {
    family: 'mitre-atlas',
    id: 'AML.T0053',
    label: 'AI Agent Tool Invocation',
    url: 'https://atlas.mitre.org/techniques/AML.T0053',
  },
  'mitre-atlas:AML.T0054': {
    family: 'mitre-atlas',
    id: 'AML.T0054',
    label: 'LLM Jailbreak',
    url: 'https://atlas.mitre.org/techniques/AML.T0054',
  },
  'mitre-atlas:AML.T0055': {
    family: 'mitre-atlas',
    id: 'AML.T0055',
    label: 'Unsecured Credentials',
    url: 'https://atlas.mitre.org/techniques/AML.T0055',
  },
  'mitre-atlas:AML.T0056': {
    family: 'mitre-atlas',
    id: 'AML.T0056',
    label: 'Extract LLM System Prompt',
    url: 'https://atlas.mitre.org/techniques/AML.T0056',
  },
  'mitre-atlas:AML.T0057': {
    family: 'mitre-atlas',
    id: 'AML.T0057',
    label: 'LLM Data Leakage',
    url: 'https://atlas.mitre.org/techniques/AML.T0057',
  },
  'mitre-atlas:AML.T0070': {
    family: 'mitre-atlas',
    id: 'AML.T0070',
    label: 'RAG Poisoning',
    url: 'https://atlas.mitre.org/techniques/AML.T0070',
  },
}

const DETECTION_DESCRIPTION = {
  substring: 'Observed when a per-run canary appears verbatim in the agent’s response.',
  normalized_substring:
    'Observed when a per-run canary appears in the agent’s response after Unicode/whitespace normalization.',
  transform:
    'Observed when a per-run canary appears in an encoded form (e.g. base64) in the agent’s response.',
  tool_arg: 'Observed when a per-run canary appears in a recorded mock tool-call argument.',
  forbidden_tool_presence: 'Observed when the agent invokes a forbidden / destructive mock tool.',
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function parseFrontmatter(raw, sourcePath) {
  const m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---/)
  if (!m) {
    console.error(`[agent-pack] ${sourcePath}: missing YAML frontmatter block.`)
    process.exit(1)
  }
  try {
    return yaml.parse(m[1])
  } catch (err) {
    console.error(`[agent-pack] ${sourcePath}: invalid YAML frontmatter — ${err.message}`)
    process.exit(1)
  }
}

function resolveFrameworks(codes, sourcePath) {
  if (!Array.isArray(codes) || codes.length === 0) return []
  return codes.map((code) => {
    const entry = AGENT_FRAMEWORK_CATALOG[code]
    if (!entry) {
      console.error(
        `[agent-pack] ${sourcePath}: unknown framework code '${code}' — add it to AGENT_FRAMEWORK_CATALOG in scripts/generate-agent-pack.cjs.`
      )
      process.exit(1)
    }
    return { family: entry.family, id: entry.id, label: entry.label, url: entry.url }
  })
}

function gitStamp(args, fallback) {
  try {
    const out = execFileSync('git', args, { cwd: ROOT, encoding: 'utf8' }).trim()
    return out || fallback
  } catch {
    return fallback
  }
}

function ensureDir(file) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
}

// Stable JSON write (2-space, trailing newline) so the drift gate is deterministic.
function writeJson(file, obj) {
  ensureDir(file)
  fs.writeFileSync(file, `${JSON.stringify(obj, null, 2)}\n`, 'utf8')
}

// ─── Main ───────────────────────────────────────────────────────────────────────

function main() {
  if (!fs.existsSync(AGENT_DIR)) {
    console.error(`[agent-pack] ${AGENT_DIR} does not exist — no AGENT pack to build.`)
    process.exit(1)
  }

  const schema = JSON.parse(fs.readFileSync(PACK_SCHEMA, 'utf8'))
  const ajv = new Ajv2020({ strict: false, allErrors: true })
  const validate = ajv.compile(schema)

  const files = fs
    .readdirSync(AGENT_DIR)
    .filter((f) => f.endsWith('.md') && f !== 'README.md')
    .sort()

  if (files.length === 0) {
    console.error('[agent-pack] rubric/AGENT/ has no AS-NN test files.')
    process.exit(1)
  }

  const seen = new Set()
  const tests = []
  for (const file of files) {
    const sourcePath = `rubric/AGENT/${file}`
    const raw = fs.readFileSync(path.join(AGENT_DIR, file), 'utf8')
    const fm = parseFrontmatter(raw, sourcePath)
    if (!validate(fm)) {
      console.error(`[agent-pack] ${sourcePath}: frontmatter failed schema validation:`)
      for (const e of validate.errors || []) {
        console.error(`    ${e.instancePath || '(root)'} ${e.message}`)
      }
      process.exit(1)
    }
    if (seen.has(fm.testId)) {
      console.error(`[agent-pack] duplicate testId '${fm.testId}' (${sourcePath}).`)
      process.exit(1)
    }
    seen.add(fm.testId)
    // Resolve frameworks so an unknown code hard-fails (badges are precomputed).
    const frameworks = resolveFrameworks(fm.frameworks, sourcePath)
    tests.push({ frontmatter: fm, frameworks })
  }

  tests.sort((a, b) => a.frontmatter.testId.localeCompare(b.frontmatter.testId))

  const packVersion = gitStamp(
    ['log', '-n1', '--format=%cd', '--date=format:%Y.%m.%d', '--', 'rubric/AGENT/'],
    '0000.00.00'
  )
  const packSha = gitStamp(['log', '-n1', '--format=%h', '--', 'rubric/AGENT/'], '0000000')

  // The two packs share every field EXCEPT the detection delta (which sits in the
  // middle of the key order): backend carries the raw detection contract +
  // placeholders, practice carries one scrubbed `detectionDescription`. Split the
  // shared head/tail so the only per-pack difference is that delta. Key order is
  // preserved (head → delta → tail → [priorArt] → frameworks) so the emitted JSON
  // stays byte-identical for the drift gate.
  const headFields = (t) => ({
    testId: t.testId,
    tier: t.tier,
    severity: t.severity,
    requiredCapability: t.requiredCapability,
    gate: t.gate ?? null,
    owasp: t.owasp,
    atlas: t.atlas,
    nist: t.nist ?? [],
  })
  const tailFields = (t) => ({
    title: t.title,
    explanation: t.explanation,
    severityRationale: t.severityRationale ?? null,
    categoryLabel: t.categoryLabel ?? null,
    remediation: t.remediation,
    limitations: t.limitations,
  })

  // ── Backend pack source (placeholders intact, full detection contract). ──
  const backendTests = tests.map(({ frontmatter: t, frameworks }) => ({
    ...headFields(t),
    detection: t.detection,
    promptTemplate: t.promptTemplate,
    mockTools: t.mockTools ?? [],
    honeytokenFixtures: t.honeytokenFixtures ?? [],
    ...tailFields(t),
    priorArt: t.priorArt ?? [],
    frameworks,
  }))
  writeJson(BACKEND_OUT, {
    packId: BACKEND_PACK_ID,
    packVersion,
    packSha,
    tests: backendTests,
  })

  // ── Public practice pack (canaries scrubbed — no raw payload/placeholders). ──
  const practiceTests = tests.map(({ frontmatter: t, frameworks }) => ({
    ...headFields(t),
    detectionDescription:
      DETECTION_DESCRIPTION[t.detection.rule] || 'Observed by a deterministic per-run canary rule.',
    ...tailFields(t),
    frameworks,
  }))
  writeJson(WEBAPP_OUT, {
    packId: PRACTICE_PACK_ID,
    packVersion,
    packSha,
    tests: practiceTests,
  })

  console.log(
    `[agent-pack] wrote ${tests.length} tests @ ${packVersion} (${packSha}) → practice.json + agent_pack.json`
  )
}

main()
