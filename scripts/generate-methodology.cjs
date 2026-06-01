#!/usr/bin/env node
/**
 * generate-methodology.cjs — methodology MDX emission from rubric/.
 *
 * Step #7 of the codegen pipeline (locked decision D-22). Reads every
 * `rubric/<CATEGORY>/<NAME>-NN.md`, parses YAML frontmatter, validates against
 * `schemas/rubric-rule.schema.json`, sorts by (sub_score, severity_rank, rule_id),
 * and emits `webapp/src/generated/methodology/index.mdx`. The MDX is consumed by
 * `webapp/src/pages/methodology.astro`.
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

// ─── Helpers ──────────────────────────────────────────────────────────────────

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
  // Group by sub_score using PRD §5.2 ordering.
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
    for (const { frontmatter: fm, sourcePath } of list) {
      out += `  <RuleCard\n`
      out += `    ruleId=${jsxString(fm.ruleId)}\n`
      out += `    severity=${jsxString(fm.severity)}\n`
      out += `    subScore=${jsxString(fm.subScore)}\n`
      out += `    status=${jsxString(fm.status)}\n`
      out += `    weight={${fm.weight}}\n`
      out += `    appliesTo=${jsxArray(fm.appliesTo)}\n`
      out += `    triggerSummary=${jsxString(triggerSummary(fm.trigger))}\n`
      out += `    limitations=${jsxLimitations(fm.limitations)}\n`
      out += `    sourcePath=${jsxString(sourcePath)}\n`
      out += `    rubricSha=${jsxString(rubricShaValue)}\n`
      out += `  />\n`
    }
    out += `</RuleGroup>\n\n`
  }

  return out
}

// Per-category counts, in PRD ordering, for non-empty categories — consumed by
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
      `/** Per-category rule counts, in PRD weighting order — feeds the methodology filter pills. */\n` +
      `export const ruleStats = [\n${statsLiteral}\n] as const\n`
  )
  console.log(`[methodology] Wrote ${path.relative(ROOT, countPath)}.`)
}

main()
