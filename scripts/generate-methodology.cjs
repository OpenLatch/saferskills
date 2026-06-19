#!/usr/bin/env node
/**
 * generate-methodology.cjs — methodology MDX emission from rubric/.
 *
 * Step #7 of the codegen pipeline. Reads every
 * `rubric/<CATEGORY>/<NAME>-NN.md`, parses YAML frontmatter, validates against
 * `schemas/rubric-rule.schema.json`, sorts by (sub_score, severity_rank, rule_id),
 * and emits `webapp/src/generated/methodology/index.mdx`. The MDX is consumed by
 * `webapp/src/pages/methodology.astro`.
 *
 * It also emits `webapp/src/generated/rules/content.ts` — the typed `RULE_CONTENT`
 * map (rule_id → plain-English title / explanation / severityRationale /
 * remediation) consumed by the report surfaces to render the explainable
 * `FindingDetail` card. This is the codegen replacement for the v3 mockup's
 * hardcoded in-JS `RULES` object — rule prose never lives in JS/TSX.
 *
 * `rubricSha` is resolved from `git log -n 1 --pretty=format:%H -- rubric/` so the
 * generated file only diff-flips when rules actually change (drift-gate friendly).
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')

const ROOT = path.resolve(__dirname, '..')
const RUBRIC_DIR = path.join(ROOT, 'rubric')
const OUT_DIR = path.join(ROOT, 'webapp', 'src', 'generated', 'methodology')
const RULES_OUT_DIR = path.join(ROOT, 'webapp', 'src', 'generated', 'rules')
// Backend mirror of the explainable-finding content map, consumed by
// `GET /api/v1/rubric/content` so the install CLI can render finding prose
// offline. Snake_case keys (it is served over the API, which is
// snake_case) — emitted from the SAME rule walk as content.ts so the two
// never drift.
const BACKEND_RULES_OUT = path.join(
  ROOT,
  'services',
  'api',
  'app',
  'generated',
  'rule_content.json'
)
const RUBRIC_SCHEMA = path.join(ROOT, 'schemas', 'rubric-rule.schema.json')

let yaml
try {
  yaml = require('yaml')
} catch {
  console.error('[methodology] `yaml` package missing. Run `pnpm install` at the repo root.')
  process.exit(2)
}

let Ajv2020
try {
  Ajv2020 = require('ajv/dist/2020').default
} catch {
  console.error('[methodology] `ajv` missing. Run `pnpm install` at the repo root.')
  process.exit(2)
}

// ─── Constants ────────────────────────────────────────────────────────────────

const SUB_SCORE_ORDER = ['security', 'supply_chain', 'maintenance', 'transparency', 'community']
const SUB_SCORE_WEIGHTS = {
  security: 35,
  supply_chain: 20,
  maintenance: 15,
  transparency: 15,
  community: 15,
}
const SUB_SCORE_TITLES = {
  security: 'Security',
  supply_chain: 'Supply Chain',
  maintenance: 'Maintenance',
  transparency: 'Transparency',
  community: 'Community',
}
const SEVERITY_RANK = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }

// ─── Framework catalog (OWASP LLM Top 10 / MITRE ATLAS / CWE) ──────────────────

// Single source of truth for the framework-badge labels + canonical URLs. A rule's
// `frameworks:` codes (schema-validated `^(owasp-llm|mitre-atlas|cwe):…$`) resolve
// here into clickable {family,id,label,url} badges on the methodology card + the
// scan-report findings. `resolveFrameworks` hard-fails on an unknown code (mirrors
// the KNOWN_ENUMS discipline) so a rule can never ship an unresolvable reference.
// OWASP slug quirk: LLM01 is `llm01-prompt-injection`; the rest are `llmNN2025-…`.
const FRAMEWORK_CATALOG = {
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
  'owasp-llm:llm03': {
    family: 'owasp-llm',
    id: 'LLM03',
    label: 'Supply Chain',
    url: 'https://genai.owasp.org/llmrisk/llm032025-supply-chain/',
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
  'mitre-atlas:AML.T0051': {
    family: 'mitre-atlas',
    id: 'AML.T0051',
    label: 'LLM Prompt Injection',
    url: 'https://atlas.mitre.org/techniques/AML.T0051',
  },
  'mitre-atlas:AML.T0050': {
    family: 'mitre-atlas',
    id: 'AML.T0050',
    label: 'Command and Scripting Interpreter',
    url: 'https://atlas.mitre.org/techniques/AML.T0050',
  },
  'mitre-atlas:AML.T0053': {
    family: 'mitre-atlas',
    id: 'AML.T0053',
    label: 'AI Agent Tool Invocation',
    url: 'https://atlas.mitre.org/techniques/AML.T0053',
  },
  'mitre-atlas:AML.T0010': {
    family: 'mitre-atlas',
    id: 'AML.T0010',
    label: 'AI Supply Chain Compromise',
    url: 'https://atlas.mitre.org/techniques/AML.T0010',
  },
  'mitre-atlas:AML.T0025': {
    family: 'mitre-atlas',
    id: 'AML.T0025',
    label: 'Exfiltration via Cyber Means',
    url: 'https://atlas.mitre.org/techniques/AML.T0025',
  },
  'cwe:78': {
    family: 'cwe',
    id: 'CWE-78',
    label: 'OS Command Injection',
    url: 'https://cwe.mitre.org/data/definitions/78.html',
  },
  'cwe:94': {
    family: 'cwe',
    id: 'CWE-94',
    label: 'Code Injection',
    url: 'https://cwe.mitre.org/data/definitions/94.html',
  },
  'cwe:95': {
    family: 'cwe',
    id: 'CWE-95',
    label: 'Eval Injection',
    url: 'https://cwe.mitre.org/data/definitions/95.html',
  },
  'cwe:200': {
    family: 'cwe',
    id: 'CWE-200',
    label: 'Exposure of Sensitive Information',
    url: 'https://cwe.mitre.org/data/definitions/200.html',
  },
  'cwe:250': {
    family: 'cwe',
    id: 'CWE-250',
    label: 'Execution with Unnecessary Privileges',
    url: 'https://cwe.mitre.org/data/definitions/250.html',
  },
  'cwe:732': {
    family: 'cwe',
    id: 'CWE-732',
    label: 'Incorrect Permission Assignment',
    url: 'https://cwe.mitre.org/data/definitions/732.html',
  },
  'cwe:798': {
    family: 'cwe',
    id: 'CWE-798',
    label: 'Use of Hard-coded Credentials',
    url: 'https://cwe.mitre.org/data/definitions/798.html',
  },
}

// Lock the badged/unbadged split so a NEW rule cannot silently ship unmapped: a
// new mappable rule bumps EXPECTED_BADGED, a new maintenance/transparency/community
// rule bumps EXPECTED_UNBADGED — either way an author makes a conscious choice.
const EXPECTED_BADGED = 39
const EXPECTED_UNBADGED = 16

// ─── Helpers ──────────────────────────────────────────────────────────────────

function resolveFrameworks(codes, sourcePath) {
  if (!Array.isArray(codes) || codes.length === 0) return []
  return codes.map((code) => {
    const entry = FRAMEWORK_CATALOG[code]
    if (!entry) {
      console.error(
        `[methodology] ${sourcePath}: unknown framework code '${code}' — add it to FRAMEWORK_CATALOG in scripts/generate-methodology.cjs.`
      )
      process.exit(1)
    }
    return { family: entry.family, id: entry.id, label: entry.label, url: entry.url }
  })
}

// Neutralize the {match}/{path}/{line}/{count} evidence placeholders for the static
// methodology surface (no per-finding evidence to interpolate). The report surfaces
// keep the raw, evidence-interpolated `explanation`.
function staticDescription(explanation) {
  return String(explanation)
    .replace(/\{match\}/g, 'the flagged value')
    .replace(/\{path\}/g, 'the file')
    .replace(/\{line\}/g, 'that line')
    .replace(/\{count\}/g, 'the matches')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()
}

// Lowercased haystack consumed by BOTH the card's data-search and the CSV row, so
// the two never drift. Strips our own inline <code> tags from the searchable text.
function buildSearchIndex(fm, frameworks, description, trigger, categoryLabel) {
  const fw = frameworks.flatMap((f) => [f.id, f.label]).join(' ')
  return [fm.ruleId, fm.title, description, categoryLabel, fw, trigger]
    .join(' ')
    .replace(/<\/?code>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

// One derived view per rule, computed once and consumed by emitMdx + emitRuleContent
// + emitRulesTable so the framework data / neutralized description / search index
// never drift across the three generated surfaces.
function deriveRule(rule) {
  const fm = rule.frontmatter
  const frameworks = resolveFrameworks(fm.frameworks, rule.sourcePath)
  const categoryLabel = fm.categoryLabel || SUB_SCORE_TITLES[fm.subScore]
  const description = staticDescription(fm.explanation)
  const trigger = triggerSummary(fm.trigger)
  const sourceUrl = `https://github.com/OpenLatch/saferskills/blob/main/${rule.sourcePath}`
  return {
    frameworks,
    categoryLabel,
    description,
    triggerSummary: trigger,
    sourceUrl,
    searchIndex: buildSearchIndex(fm, frameworks, description, trigger, categoryLabel),
  }
}

function parseFrontmatter(rawContent, sourcePath) {
  if (!rawContent.startsWith('---\n') && !rawContent.startsWith('---\r\n')) {
    throw new Error(`${sourcePath}: missing YAML frontmatter (must start with '---\\n').`)
  }
  const closing = rawContent.indexOf('\n---', 3)
  if (closing === -1) {
    throw new Error(`${sourcePath}: unterminated YAML frontmatter (no closing '---').`)
  }
  const frontmatterRaw = rawContent.slice(4, closing).trim()
  try {
    return yaml.parse(frontmatterRaw)
  } catch (err) {
    throw new Error(`${sourcePath}: YAML parse error — ${err.message}`)
  }
}

function rubricSha() {
  // Use the git tree SHA of the rubric/ directory rather than the last-commit
  // SHA: tree SHAs are content-addressable (two commits with identical
  // rubric/ contents produce the same tree SHA), so the output is stable
  // across local dev (which sees real commits) and CI (which checks out
  // virtual merge commits like `pull/N/merge` with different commit SHAs
  // but identical tree state).
  try {
    const sha = execFileSync('git', ['rev-parse', 'HEAD:rubric'], {
      cwd: ROOT,
      encoding: 'utf8',
    }).trim()
    return sha || 'unknown'
  } catch {
    return 'unknown'
  }
}

function triggerSummary(trigger) {
  switch (trigger.type) {
    case 'regex_match': {
      const scope = trigger.scope?.paths ? trigger.scope.paths.join(', ') : 'all files'
      return `regex \`${trigger.pattern}\` against ${scope}`
    }
    case 'file_glob_present':
      return `file present at ${trigger.paths.join(' or ')}`
    case 'file_glob_absent':
      return `no file at ${trigger.paths.join(' or ')}`
    case 'commit_history_check':
      return `${trigger.signal} ${trigger.operator} ${trigger.threshold}`
    case 'metadata_check':
      return `metadata ${trigger.field} ${trigger.operator} ${JSON.stringify(trigger.value)}`
    case 'composite_and_or':
      return `${trigger.op.toUpperCase()} of ${trigger.children.length} sub-triggers`
    default:
      return 'unspecified trigger'
  }
}

function jsxEscapeAttr(value) {
  return String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')
}

function jsxString(value) {
  return `"${jsxEscapeAttr(value)}"`
}

function jsxArray(values) {
  return `{${JSON.stringify(values)}}`
}

function jsxLimitations(items) {
  // RuleCard accepts a string[]; emit as JSON.
  return `{${JSON.stringify(items)}}`
}

// ─── Walk rubric/ ─────────────────────────────────────────────────────────────

function walkRubric() {
  const rules = []
  if (!fs.existsSync(RUBRIC_DIR)) {
    return rules
  }
  for (const category of fs.readdirSync(RUBRIC_DIR, { withFileTypes: true })) {
    if (!category.isDirectory()) continue
    // `rubric/AGENT/` is the behavioral-pack tree — a DIFFERENT taxonomy +
    // schema (AS-NN tests, agent-pack-test.schema.json) owned by the step-9
    // `generate-agent-pack.cjs` generator. The component methodology generator
    // must NOT parse/count it (its frontmatter is not a `rubric-rule`, and the
    // badge-count assertion below would `process.exit(1)`).
    if (category.name === 'AGENT') continue
    const catDir = path.join(RUBRIC_DIR, category.name)
    for (const file of fs.readdirSync(catDir)) {
      if (!file.endsWith('.md') || file === 'README.md') continue
      const fullPath = path.join(catDir, file)
      const relPath = path.relative(ROOT, fullPath).replace(/\\/g, '/')
      const raw = fs.readFileSync(fullPath, 'utf8')
      const fm = parseFrontmatter(raw, relPath)
      rules.push({ frontmatter: fm, sourcePath: relPath })
    }
  }
  return rules
}

// ─── Validate against rubric-rule.schema.json ────────────────────────────────

function buildValidator() {
  const schema = JSON.parse(fs.readFileSync(RUBRIC_SCHEMA, 'utf8'))
  const ajv = new Ajv2020({ strict: false, allErrors: true })
  return ajv.compile(schema)
}

// ─── Emit MDX ─────────────────────────────────────────────────────────────────

function emitMdx(rules, rubricShaValue) {
  // Group by sub_score using the methodology weighting order.
  const bySub = new Map()
  for (const key of SUB_SCORE_ORDER) bySub.set(key, [])
  for (const r of rules) {
    const sub = r.frontmatter.subScore
    if (!bySub.has(sub)) bySub.set(sub, [])
    bySub.get(sub).push(r)
  }
  for (const list of bySub.values()) {
    list.sort((a, b) => {
      const sevA = SEVERITY_RANK[a.frontmatter.severity] ?? 99
      const sevB = SEVERITY_RANK[b.frontmatter.severity] ?? 99
      if (sevA !== sevB) return sevA - sevB
      return a.frontmatter.ruleId.localeCompare(b.frontmatter.ruleId)
    })
  }

  let out = `{/* AUTO-GENERATED by scripts/generate-methodology.cjs from rubric/. DO NOT EDIT. */}\n`
  out += `{/* rubricSha: ${rubricShaValue} */}\n\n`
  out += `import RuleCard from '@/components/methodology/RuleCard.astro'\n`
  out += `import RuleGroup from '@/components/methodology/RuleGroup.astro'\n\n`
  // Machine-readable rule count — the single source of truth for any surface
  // that quotes "N detection rules" without an API round-trip (kills 87↔55 drift).
  out += `export const ruleCount = ${rules.length}\n\n`
  // No page-level heading / intro here: methodology.astro already owns the
  // "§02 The rules." heading + intro, so emitting another H1 + paragraph
  // duplicated it. Each category is a RuleGroup whose header carries the title,
  // weight, and rule count — these are the only headings the page renders.

  for (const sub of SUB_SCORE_ORDER) {
    const list = bySub.get(sub) || []
    if (list.length === 0) continue
    out += `<RuleGroup category=${jsxString(sub)} title=${jsxString(SUB_SCORE_TITLES[sub])} weight={${SUB_SCORE_WEIGHTS[sub]}} count={${list.length}}>\n`
    for (const { frontmatter: fm, sourcePath, derived } of list) {
      out += `  <RuleCard\n`
      out += `    ruleId=${jsxString(fm.ruleId)}\n`
      out += `    title=${jsxString(fm.title)}\n`
      out += `    categoryLabel=${jsxString(derived.categoryLabel)}\n`
      out += `    description=${jsxString(derived.description)}\n`
      out += `    severity=${jsxString(fm.severity)}\n`
      out += `    subScore=${jsxString(fm.subScore)}\n`
      out += `    status=${jsxString(fm.status)}\n`
      out += `    weight={${fm.weight}}\n`
      out += `    appliesTo=${jsxArray(fm.appliesTo)}\n`
      out += `    frameworks=${jsxArray(derived.frameworks)}\n`
      out += `    triggerSummary=${jsxString(derived.triggerSummary)}\n`
      out += `    limitations=${jsxLimitations(fm.limitations)}\n`
      out += `    searchIndex=${jsxString(derived.searchIndex)}\n`
      out += `    sourcePath=${jsxString(sourcePath)}\n`
      out += `    rubricSha=${jsxString(rubricShaValue)}\n`
      out += `  />\n`
    }
    out += `</RuleGroup>\n\n`
  }

  return out
}

// Per-category counts, in methodology weighting order, for non-empty categories — consumed by
// the RuleFilter island's category pills (SSR-correct counts, no DOM probing).
function buildStats(rules) {
  const counts = new Map()
  for (const r of rules) {
    const sub = r.frontmatter.subScore
    counts.set(sub, (counts.get(sub) || 0) + 1)
  }
  return SUB_SCORE_ORDER.filter((sub) => (counts.get(sub) || 0) > 0).map((sub) => ({
    key: sub,
    title: SUB_SCORE_TITLES[sub],
    weight: SUB_SCORE_WEIGHTS[sub],
    count: counts.get(sub),
  }))
}

// ─── Emit rules/content.ts ──────────────────────────────────────────────────

// The typed RULE_CONTENT map (rule_id → plain-English title / explanation /
// severityRationale / remediation). Replaces the v3 mockup's hardcoded in-JS
// `RULES` object — the frontend `FindingDetail` composes from this map plus the
// backend-supplied evidence. Keys stay camelCase (this is frontend-internal
// generated TS, not an API wire DTO — mirrors rule-count.ts).
function emitRuleContent(rules) {
  const sorted = [...rules].sort((a, b) => a.frontmatter.ruleId.localeCompare(b.frontmatter.ruleId))
  const map = {}
  for (const { frontmatter: fm, derived } of sorted) {
    const remediation = { action: fm.remediation.action }
    if (Array.isArray(fm.remediation.steps) && fm.remediation.steps.length > 0) {
      remediation.steps = fm.remediation.steps
    }
    if (fm.remediation.saferPattern) {
      remediation.saferPattern = {
        before: fm.remediation.saferPattern.before,
        after: fm.remediation.saferPattern.after,
      }
    }
    const entry = {
      ruleId: fm.ruleId,
      severity: fm.severity,
      subScore: fm.subScore,
      categoryLabel: fm.categoryLabel || SUB_SCORE_TITLES[fm.subScore],
      title: fm.title,
      explanation: fm.explanation,
    }
    if (fm.severityRationale) entry.severityRationale = fm.severityRationale
    entry.remediation = remediation
    // Resolved framework badges — read by the web FindingDetail (scan-report
    // surface) straight off RULE_CONTENT; omitted entirely for unmapped rules.
    if (derived.frameworks.length > 0) entry.frameworks = derived.frameworks
    map[fm.ruleId] = entry
  }

  const header =
    `// AUTO-GENERATED by scripts/generate-methodology.cjs from rubric/. DO NOT EDIT.\n` +
    `// One entry per rule — the explainable-finding content map (D-reco).\n\n` +
    `export type RuleSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical'\n` +
    `export type RuleSubScore =\n` +
    `  | 'security'\n  | 'supply_chain'\n  | 'maintenance'\n  | 'transparency'\n  | 'community'\n\n` +
    `export type FrameworkFamily = 'owasp-llm' | 'mitre-atlas' | 'cwe'\n\n` +
    `export interface FrameworkRef {\n` +
    `  /** Taxonomy family — drives the badge tint. */\n  family: FrameworkFamily\n` +
    `  /** Canonical short code, e.g. 'LLM01' / 'AML.T0051' / 'CWE-78'. */\n  id: string\n` +
    `  /** Human risk name, e.g. 'Prompt Injection'. */\n  label: string\n` +
    `  /** Canonical reference URL. */\n  url: string\n}\n\n` +
    `export interface RuleSaferPattern {\n  before: string\n  after: string\n}\n\n` +
    `export interface RuleRemediation {\n` +
    `  /** Imperative one-line action naming the user's construct. */\n  action: string\n` +
    `  /** Optional ordered remediation steps (may contain inline <code>…</code>). */\n  steps?: string[]\n` +
    `  /** Optional Avoid → Safer pattern before/after pair. */\n  saferPattern?: RuleSaferPattern\n}\n\n` +
    `export interface RuleContent {\n` +
    `  ruleId: string\n  severity: RuleSeverity\n  subScore: RuleSubScore\n` +
    `  /** Human category label for the meta line (falls back to the sub-score title). */\n  categoryLabel: string\n` +
    `  /** Plain-English headline (no rule_id). */\n  title: string\n` +
    `  /** 'Why it matters' paragraph; may use {match} {path} {line} {count} + inline <code>. */\n  explanation: string\n` +
    `  /** Optional severity→outcome clause rendered after the severity word. */\n  severityRationale?: string\n` +
    `  /** Optional resolved framework-reference badges (OWASP LLM / MITRE ATLAS / CWE). */\n  frameworks?: FrameworkRef[]\n` +
    `  remediation: RuleRemediation\n}\n\n`

  const body = `export const RULE_CONTENT: Record<string, RuleContent> = ${JSON.stringify(
    map,
    null,
    2
  )}\n`
  return header + body
}

// ─── Emit services/api/app/generated/rule_content.json ───────────────────────

// The backend-served projection of the same rule prose. Keys are
// snake_case because this file is loaded by the API and re-served over the wire
// (the API is snake_case end-to-end). The install CLI fetches it once from
// `GET /api/v1/rubric/content`, caches it under `~/.saferskills/cache/`, and
// renders finding explanations offline. Emitted from the same `rules` walk as
// `content.ts` so the two contents can never drift.
function emitRuleContentJson(rules, rubricShaValue) {
  const sorted = [...rules].sort((a, b) => a.frontmatter.ruleId.localeCompare(b.frontmatter.ruleId))
  const map = {}
  for (const { frontmatter: fm } of sorted) {
    const remediation = { action: fm.remediation.action }
    if (Array.isArray(fm.remediation.steps) && fm.remediation.steps.length > 0) {
      remediation.steps = fm.remediation.steps
    }
    if (fm.remediation.saferPattern) {
      remediation.safer_pattern = {
        before: fm.remediation.saferPattern.before,
        after: fm.remediation.saferPattern.after,
      }
    }
    const entry = {
      rule_id: fm.ruleId,
      severity: fm.severity,
      sub_score: fm.subScore,
      category_label: fm.categoryLabel || SUB_SCORE_TITLES[fm.subScore],
      title: fm.title,
      explanation: fm.explanation,
    }
    if (fm.severityRationale) entry.severity_rationale = fm.severityRationale
    entry.remediation = remediation
    map[fm.ruleId] = entry
  }
  return `${JSON.stringify({ rubric_version: rubricShaValue, rules: map }, null, 2)}\n`
}

// ─── Emit methodology/rules-table.ts ─────────────────────────────────────────

// The full per-rule data the methodology CSV export needs (name = first column),
// keyed by ruleId. The RuleFilter island joins the currently-visible cards (read
// from the DOM) to these rows — one filter authority, no second predicate. Carries
// the SAME neutralized description / resolved frameworks / searchIndex as the cards
// (via `derived`) so the CSV and the on-page cards can never drift.
function emitRulesTable(rules) {
  const sorted = [...rules].sort((a, b) => a.frontmatter.ruleId.localeCompare(b.frontmatter.ruleId))
  const rows = sorted.map(({ frontmatter: fm, derived }) => ({
    ruleId: fm.ruleId,
    name: fm.title,
    category: fm.subScore,
    categoryLabel: derived.categoryLabel,
    severity: fm.severity,
    // Effective weight — shadow rules contribute 0, matching the card display.
    weight: fm.status === 'shadow' ? 0 : fm.weight,
    status: fm.status,
    appliesTo: fm.appliesTo,
    description: derived.description,
    ...(fm.severityRationale ? { severityRationale: fm.severityRationale } : {}),
    remediationAction: fm.remediation.action,
    frameworks: derived.frameworks,
    detection: derived.triggerSummary,
    limitations: fm.limitations,
    sourceUrl: derived.sourceUrl,
    searchIndex: derived.searchIndex,
  }))

  const header =
    `// AUTO-GENERATED by scripts/generate-methodology.cjs from rubric/. DO NOT EDIT.\n` +
    `// Full per-rule table backing the /methodology CSV export (joined to the\n` +
    `// visible cards by ruleId in RuleFilter — the DOM is the single filter authority).\n\n` +
    `import type { FrameworkRef } from '@/generated/rules/content'\n\n` +
    `export interface RuleRow {\n` +
    `  ruleId: string\n` +
    `  /** Plain-English headline — the CSV's first column. */\n  name: string\n` +
    `  category: 'security' | 'supply_chain' | 'maintenance' | 'transparency' | 'community'\n` +
    `  categoryLabel: string\n` +
    `  severity: 'info' | 'low' | 'medium' | 'high' | 'critical'\n` +
    `  /** Effective max penalty (shadow → 0). */\n  weight: number\n` +
    `  status: 'shadow' | 'active' | 'deprecated'\n` +
    `  appliesTo: string[]\n` +
    `  description: string\n` +
    `  severityRationale?: string\n` +
    `  remediationAction: string\n` +
    `  frameworks: FrameworkRef[]\n` +
    `  /** Human trigger summary (the card's "Detection logic"). */\n  detection: string\n` +
    `  limitations: string[]\n` +
    `  sourceUrl: string\n` +
    `  searchIndex: string\n` +
    `}\n\n`

  return `${header}export const ruleRows: RuleRow[] = ${JSON.stringify(rows, null, 2)}\n`
}

// ─── Main ─────────────────────────────────────────────────────────────────────

function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true })

  const rules = walkRubric()
  console.log(`[methodology] Found ${rules.length} rule(s) under rubric/.`)

  if (rules.length > 0) {
    const validate = buildValidator()
    let failures = 0
    for (const { frontmatter, sourcePath } of rules) {
      if (!validate(frontmatter)) {
        failures++
        console.error(`  ✗ ${sourcePath}`)
        for (const err of validate.errors || []) {
          console.error(`      ${err.instancePath} ${err.message}`)
        }
      }
    }
    if (failures > 0) {
      console.error(`\n[methodology] ${failures} rule(s) failed schema validation.`)
      process.exit(1)
    }
    // shadow_until required iff status=shadow (cross-field rule not expressible cleanly in JSON Schema)
    for (const { frontmatter, sourcePath } of rules) {
      if (frontmatter.status === 'shadow' && !frontmatter.shadowUntil) {
        console.error(`  ✗ ${sourcePath}: status=shadow requires shadowUntil`)
        process.exit(1)
      }
      if (frontmatter.status !== 'shadow' && frontmatter.shadowUntil) {
        console.error(`  ✗ ${sourcePath}: shadowUntil only allowed when status=shadow`)
        process.exit(1)
      }
    }
  }

  // Derive the shared per-rule view (frameworks / neutralized description /
  // search index) ONCE; emitMdx + emitRuleContent + emitRulesTable all read it.
  for (const rule of rules) rule.derived = deriveRule(rule)

  // Lock the badged/unbadged split — a new rule cannot silently ship unmapped.
  const badged = rules.filter((r) => r.derived.frameworks.length > 0).length
  const unbadged = rules.length - badged
  if (rules.length > 0 && (badged !== EXPECTED_BADGED || unbadged !== EXPECTED_UNBADGED)) {
    console.error(
      `[methodology] framework-badge count drift: badged=${badged} (expected ${EXPECTED_BADGED}), unbadged=${unbadged} (expected ${EXPECTED_UNBADGED}).`
    )
    console.error(
      `[methodology] Map the new rule's frameworks (or leave it intentionally unbadged), then update EXPECTED_BADGED / EXPECTED_UNBADGED in scripts/generate-methodology.cjs.`
    )
    process.exit(1)
  }

  const sha = rubricSha()
  const mdx = emitMdx(rules, sha)
  const outPath = path.join(OUT_DIR, 'index.mdx')
  // Normalize trailing newlines: single \n at EOF (matches end-of-file-fixer).
  fs.writeFileSync(outPath, mdx.replace(/\n+$/, '\n'))
  console.log(`[methodology] Wrote ${path.relative(ROOT, outPath)} (rubricSha=${sha.slice(0, 7)}).`)

  // Typed sidecar: `astro check` does not type named exports from a standalone
  // .mdx module, so emit the rule count as a plain .ts constant for type-safe
  // consumers (single source of truth — kills any "N detection rules" drift).
  const countPath = path.join(OUT_DIR, 'rule-count.ts')
  const stats = buildStats(rules)
  const statsLiteral = stats
    .map(
      (s) =>
        `  { key: ${JSON.stringify(s.key)}, title: ${JSON.stringify(s.title)}, weight: ${s.weight}, count: ${s.count} },`
    )
    .join('\n')
  fs.writeFileSync(
    countPath,
    `// AUTO-GENERATED by scripts/generate-methodology.cjs from rubric/. DO NOT EDIT.\n` +
      `// rubricSha: ${sha}\n` +
      `export const ruleCount = ${rules.length}\n\n` +
      `/** Per-category rule counts, in methodology weighting order — feeds the methodology filter pills. */\n` +
      `export const ruleStats = [\n${statsLiteral}\n] as const\n`
  )
  console.log(`[methodology] Wrote ${path.relative(ROOT, countPath)}.`)

  // Explainable-finding content map: rule_id → title/explanation/remediation.
  fs.mkdirSync(RULES_OUT_DIR, { recursive: true })
  const contentPath = path.join(RULES_OUT_DIR, 'content.ts')
  fs.writeFileSync(contentPath, emitRuleContent(rules))
  console.log(`[methodology] Wrote ${path.relative(ROOT, contentPath)} (${rules.length} rule(s)).`)

  // Full per-rule table for the methodology CSV export (joined to visible cards
  // by ruleId in RuleFilter).
  const tablePath = path.join(OUT_DIR, 'rules-table.ts')
  fs.writeFileSync(tablePath, emitRulesTable(rules))
  console.log(`[methodology] Wrote ${path.relative(ROOT, tablePath)} (${rules.length} rule(s)).`)

  // Backend mirror for the CLI offline finding prose.
  fs.mkdirSync(path.dirname(BACKEND_RULES_OUT), { recursive: true })
  fs.writeFileSync(BACKEND_RULES_OUT, emitRuleContentJson(rules, sha))
  console.log(
    `[methodology] Wrote ${path.relative(ROOT, BACKEND_RULES_OUT)} (rubric_version=${sha.slice(0, 7)}).`
  )
}

main()
