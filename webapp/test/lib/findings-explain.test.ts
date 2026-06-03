import { describe, expect, it } from 'vitest'

import type { Finding } from '@/lib/api/scans'
import {
  fillTemplate,
  groupFindings,
  placeholdersFor,
  resolveFindingDetail,
  rubricLabel,
} from '@/lib/findings/explain'

function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: crypto.randomUUID(),
    rule_id: 'SS-SKILL-INJECT-FENCED-RUN-01',
    severity: 'high',
    sub_score: 'security',
    penalty: 20,
    status_at_scan: 'active',
    file_path: 'SKILL.md',
    line_start: 13,
    line_end: null,
    matched_content_sha256: 'a'.repeat(64),
    remediation_link: 'https://saferskills.ai/methodology#x',
    rubric_version: 'abc1234',
    ...overrides,
  }
}

describe('groupFindings', () => {
  it('dedups by (rule_id, file) and counts occurrences', () => {
    const groups = groupFindings([
      finding({ line_start: 13 }),
      finding({ line_start: 42 }),
      finding({ rule_id: 'SS-SKILL-INJECT-IGNORE-01', line_start: 5 }),
    ])
    expect(groups).toHaveLength(2)
    const fenced = groups.find((g) => g.ruleId === 'SS-SKILL-INJECT-FENCED-RUN-01')
    expect(fenced?.occurrences.map((o) => o.line)).toEqual([13, 42])
  })

  it('orders groups by severity (critical first)', () => {
    const groups = groupFindings([
      finding({ rule_id: 'SS-A-01', severity: 'low', file_path: 'a' }),
      finding({ rule_id: 'SS-B-01', severity: 'critical', file_path: 'b' }),
      finding({ rule_id: 'SS-C-01', severity: 'medium', file_path: 'c' }),
    ])
    expect(groups.map((g) => g.severity)).toEqual(['critical', 'medium', 'low'])
  })

  it('picks the excerpt-bearing occurrence as representative', () => {
    const groups = groupFindings([
      finding({ line_start: 13, evidence_excerpt: null }),
      finding({
        line_start: 42,
        evidence_excerpt: {
          file: 'SKILL.md',
          lang: 'markdown',
          truncated: false,
          lines: [{ line_no: 42, text: 'curl | sh', hit: true }],
        },
      }),
    ])
    expect(groups[0].excerpt?.lines[0].text).toBe('curl | sh')
  })
})

describe('placeholdersFor', () => {
  it('derives match (trimmed hit line), path, line, count', () => {
    const [g] = groupFindings([
      finding({
        line_start: 13,
        evidence_excerpt: {
          file: 'SKILL.md',
          lang: 'markdown',
          truncated: false,
          lines: [{ line_no: 13, text: '   curl https://x | sh   ', hit: true }],
        },
      }),
    ])
    const ph = placeholdersFor(g)
    expect(ph.match).toBe('curl https://x | sh')
    expect(ph.path).toBe('SKILL.md')
    expect(ph.line).toBe(13)
    expect(ph.count).toBe(1)
  })

  it('truncates a long match', () => {
    const [g] = groupFindings([
      finding({
        evidence_excerpt: {
          file: 'a',
          lang: null,
          truncated: false,
          lines: [{ line_no: 1, text: 'x'.repeat(200), hit: true }],
        },
      }),
    ])
    const ph = placeholdersFor(g)
    expect(ph.match?.length).toBeLessThanOrEqual(49)
    expect(ph.match?.endsWith('…')).toBe(true)
  })

  it('omits match when no excerpt is present', () => {
    const [g] = groupFindings([finding({ evidence_excerpt: null })])
    expect(placeholdersFor(g).match).toBeUndefined()
  })
})

describe('fillTemplate', () => {
  it('interpolates present placeholders', () => {
    expect(fillTemplate('runs {match} at L{line}', { match: 'curl|sh', line: 13 })).toBe(
      'runs curl|sh at L13'
    )
  })
  it('drops empty placeholders and collapses the gap', () => {
    expect(fillTemplate('an imperative like {match} buried here', {})).toBe(
      'an imperative like buried here'
    )
  })
})

describe('rubricLabel', () => {
  it('shows a 7-char sha for a real version', () => {
    expect(rubricLabel('abcdef1234567')).toBe('rubric abcdef1')
  })
  it('falls back to dev for unknown/missing', () => {
    expect(rubricLabel('unknown')).toBe('rubric · dev')
    expect(rubricLabel(null)).toBe('rubric · dev')
  })
})

describe('resolveFindingDetail', () => {
  it('resolves authored content for a known rule (title is not the rule id)', () => {
    const [g] = groupFindings([finding()])
    const props = resolveFindingDetail(g, {
      githubUrl: 'https://github.com/a/b',
      refSha: 'abc1234',
      rubricVersion: 'abc1234',
    })
    expect(props.ruleId).toBe('SS-SKILL-INJECT-FENCED-RUN-01')
    expect(props.title).not.toBe(props.ruleId)
    expect(props.categoryLabel.length).toBeGreaterThan(0)
    expect(props.githubHref).toContain('/blob/abc1234/SKILL.md#L13')
    expect(props.rubricLabel).toBe('rubric abc1234')
  })

  it('falls back gracefully for an unknown rule id', () => {
    const [g] = groupFindings([finding({ rule_id: 'SS-SKILL-DOES-NOT-EXIST-99' })])
    const props = resolveFindingDetail(g)
    expect(props.title).toBe('SS-SKILL-DOES-NOT-EXIST-99')
    expect(props.githubHref).toBeNull()
  })
})
