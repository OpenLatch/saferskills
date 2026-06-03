/**
 * Group + resolve findings into `FindingDetail` props.
 *
 * Ports the v3 mockup's `groupFindings()` + the `RULES` lookup, except the rule
 * library is the codegen `RULE_CONTENT` map (rule prose never lives in TSX). The
 * webapp owns the grouping + map lookup + placeholder interpolation and hands
 * the DS `FindingDetail` already-resolved props — `ui/` never imports the map.
 */

import type { FindingDetailProps } from '@ui/components/molecules/FindingDetail'

import { RULE_CONTENT, type RuleContent } from '@/generated/rules/content'
import type { EvidenceExcerpt, Finding } from '@/lib/api/scans'

/** One (rule_id, file) group: the dedup unit — one card per group. */
export interface FindingGroup {
  ruleId: string
  file: string
  severity: Finding['severity']
  subScore: string
  occurrences: { line: number; file: string }[]
  /** Representative excerpt (first occurrence that carries one), or null. */
  excerpt: EvidenceExcerpt | null
  sha: string | null
  remediationLink: string
}

export interface Placeholders {
  match?: string
  path?: string
  line?: string | number
  count?: number
}

export interface ResolveCtx {
  githubUrl?: string | null
  refSha?: string | null
  rubricVersion?: string | null
}

const SEV_RANK: Record<Finding['severity'], number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
}

const SUB_LABEL: Record<string, string> = {
  security: 'Security',
  supply_chain: 'Supply chain',
  maintenance: 'Maintenance',
  transparency: 'Transparency',
  community: 'Community',
}

const MATCH_MAX = 48 // inline {match} is decorative — the full value is in the excerpt

/**
 * De-duplicate findings by `(rule_id, file_path)` → one group per card.
 * Occurrences are line-sorted; the representative excerpt/sha is taken from the
 * first occurrence that carries an excerpt (else the first finding). Groups are
 * ordered by severity (critical → info).
 */
export function groupFindings(findings: Finding[]): FindingGroup[] {
  const map = new Map<string, FindingGroup>()
  const order: string[] = []
  for (const f of findings) {
    const key = `${f.rule_id}@@${f.file_path}`
    let g = map.get(key)
    if (!g) {
      g = {
        ruleId: f.rule_id,
        file: f.file_path,
        severity: f.severity,
        subScore: f.sub_score,
        occurrences: [],
        excerpt: null,
        sha: f.matched_content_sha256 ?? null,
        remediationLink: f.remediation_link,
      }
      map.set(key, g)
      order.push(key)
    }
    g.occurrences.push({ line: f.line_start, file: f.file_path })
    if (f.evidence_excerpt && !g.excerpt) {
      g.excerpt = f.evidence_excerpt
      g.sha = f.matched_content_sha256 ?? g.sha
    }
  }
  const groups = order.map((k) => map.get(k) as FindingGroup)
  for (const g of groups) g.occurrences.sort((a, b) => a.line - b.line)
  groups.sort((a, b) => (SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9))
  return groups
}

/** Closed-set placeholder values for a group (graceful when a value is absent). */
export function placeholdersFor(group: FindingGroup): Placeholders {
  const ph: Placeholders = {
    path: group.file,
    line: group.occurrences[0]?.line,
    count: group.occurrences.length,
  }
  if (group.excerpt) {
    const hit = group.excerpt.lines.find((l) => l.hit) ?? group.excerpt.lines[0]
    if (hit) {
      let text = hit.text.trim()
      if (text.length > MATCH_MAX) text = `${text.slice(0, MATCH_MAX)}…`
      if (text) ph.match = text
    }
  }
  return ph
}

/** Plain-text placeholder fill (for non-render uses — e.g. CLI / tests). */
export function fillTemplate(tpl: string, ph: Placeholders): string {
  return tpl
    .replace(/\{(match|path|line|count)\}/g, (_full, key: string) => {
      const v = ph[key as keyof Placeholders]
      return v === undefined || v === null ? '' : String(v)
    })
    .replace(/\s{2,}/g, ' ')
    .trim()
}

/** Friendly rubric label: a 7-char sha, else `dev` for unknown/missing. */
export function rubricLabel(version?: string | null): string {
  if (version && /^[a-f0-9]{7,40}$/i.test(version)) return `rubric ${version.slice(0, 7)}`
  return 'rubric · dev'
}

function toExcerptProp(excerpt: EvidenceExcerpt | null): FindingDetailProps['evidence'] {
  if (!excerpt) return null
  return {
    file: excerpt.file,
    lang: excerpt.lang,
    truncated: excerpt.truncated,
    lines: excerpt.lines.map((l) => ({ lineNo: l.line_no, text: l.text, hit: l.hit })),
  }
}

/** Resolve a group + the codegen content map → fully-resolved FindingDetail props. */
export function resolveFindingDetail(
  group: FindingGroup,
  ctx: ResolveCtx = {}
): Omit<FindingDetailProps, 'defaultOpen' | 'onExpand'> {
  const content: RuleContent | undefined = RULE_CONTENT[group.ruleId]
  const placeholders = placeholdersFor(group)
  const githubHref = ctx.githubUrl
    ? `${ctx.githubUrl.replace(/\/$/, '')}/blob/${ctx.refSha ?? 'HEAD'}/${group.file}#L${
        group.occurrences[0]?.line ?? 1
      }`
    : null
  const common = {
    ruleId: group.ruleId,
    file: group.file,
    placeholders,
    evidence: toExcerptProp(group.excerpt),
    occurrences: group.occurrences,
    sha: group.sha,
    methodologyHref: group.remediationLink,
    githubHref,
    rubricLabel: rubricLabel(ctx.rubricVersion),
  }

  if (!content) {
    // Should not happen — the drift gate guarantees content for every rule.
    return {
      ...common,
      severity: group.severity,
      title: group.ruleId,
      categoryLabel: SUB_LABEL[group.subScore] ?? group.subScore,
      explanation: 'This rule fired on the scanned artifact. See the location below.',
      remediation: { action: 'Review the flagged location.' },
    }
  }

  return {
    ...common,
    severity: content.severity,
    title: content.title,
    categoryLabel: content.categoryLabel,
    severityRationale: content.severityRationale,
    explanation: content.explanation,
    remediation: content.remediation,
  }
}
