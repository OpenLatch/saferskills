/**
 * Pure view-model helpers for the Agent Report Findings tab. Maps the
 * `AgentScanReportDetail` finding shape onto the framework-agnostic `ui/` molecule
 * props: deep-linked ref chips, OWASP-family grouping, and the per-finding
 * score-math ledger (sourced verbatim from the report `score_breakdown`).
 */
import type { RefChipProps } from '@ui/components/atoms/RefChip'
import type { ScoreMathModifier } from '@ui/components/molecules/ScoreMathTable'

import type { AgentFindingRow, AgentScoreBreakdown } from '@/lib/api/agent-scan-types'

// Deep-link targets. MITRE deep-links the technique id.
export const OWASP_AGENTIC_URL =
  'https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/'
export const OWASP_LLM_URL = 'https://genai.owasp.org/llm-top-10/'
export const MITRE_ATLAS_URL = 'https://atlas.mitre.org'
export const NIST_URL = 'https://www.nist.gov/itl/ai-risk-management-framework'

/** Map one ref id (e.g. `ASI04:2026`, `AML.T0053`, `NIST AI 600-1`) to a chip, or
 * null when the id is unrecognised (so a broken link is never rendered). */
export function refToChip(ref: string): RefChipProps | null {
  const r = ref.trim()
  if (/^ASI/i.test(r)) return { label: r, href: OWASP_AGENTIC_URL, kind: 'owasp' }
  if (/^LLM/i.test(r)) return { label: r, href: OWASP_LLM_URL, kind: 'owasp' }
  if (/^AML\.T/i.test(r)) {
    const technique = r.split(/[\s:]/)[0]
    return { label: r, href: `${MITRE_ATLAS_URL}/techniques/${technique}`, kind: 'mitre' }
  }
  if (/nist/i.test(r)) return { label: r, href: NIST_URL, kind: 'nist' }
  return null
}

/** All ref chips for one finding (owasp + atlas + nist, in that order). */
export function findingRefChips(f: AgentFindingRow): RefChipProps[] {
  return [...(f.owasp_refs ?? []), ...(f.atlas_refs ?? []), ...(f.nist_refs ?? [])]
    .map(refToChip)
    .filter((c): c is RefChipProps => c !== null)
}

/** The OWASP index for a family group head (e.g. `ASI04`), from the first ref. */
export function owaspIndex(owaspRefs: string[]): string {
  const first = (owaspRefs ?? [])[0]
  return first ? first.split(':')[0] : ''
}

export interface FindingGroup {
  family: string
  index: string
  refs: RefChipProps[]
  findings: AgentFindingRow[]
}

/** Group findings by OWASP family (first-seen order); derive the head index + the
 * deduped OWASP/MITRE chip row from the group's findings. */
export function groupFindingsByFamily(findings: AgentFindingRow[]): FindingGroup[] {
  const order: string[] = []
  const byFamily = new Map<string, AgentFindingRow[]>()
  for (const f of findings) {
    const family = f.family || 'Other'
    if (!byFamily.has(family)) {
      byFamily.set(family, [])
      order.push(family)
    }
    byFamily.get(family)?.push(f)
  }
  return order.map((family) => {
    const rows = byFamily.get(family) ?? []
    const index = owaspIndex(rows[0]?.owasp_refs ?? [])
    const seen = new Set<string>()
    const refs: RefChipProps[] = []
    for (const f of rows) {
      for (const ref of [...(f.owasp_refs ?? []), ...(f.atlas_refs ?? [])]) {
        const chip = refToChip(ref)
        if (chip && !seen.has(chip.label)) {
          seen.add(chip.label)
          refs.push(chip)
        }
      }
    }
    return { family, index, refs, findings: rows }
  })
}

export interface FindingScoreMath {
  base: number
  modifiers: ScoreMathModifier[]
  cap: { label: string; value: number } | null
  finalScore: number
}

/** Build the per-finding score-math ledger from the report `score_breakdown`,
 * emphasizing the row for `testId`. Numbers come straight from the breakdown —
 * `base` is the arithmetic identity `raw − Σdelta` (no scoring logic re-run).
 * Returns null when no breakdown is present (the table is then omitted). */
export function scoreMathFor(
  breakdown: AgentScoreBreakdown | null,
  testId: string
): FindingScoreMath | null {
  if (!breakdown) return null
  const modifiers: ScoreMathModifier[] = breakdown.findings.map((m) => ({
    testId: m.test_id,
    severity: m.severity,
    delta: m.score_delta,
    emphasized: m.test_id === testId,
  }))
  const sumDelta = modifiers.reduce((acc, m) => acc + m.delta, 0)
  const cap =
    breakdown.ceiling_applied && breakdown.ceiling !== null
      ? { label: 'Worst-finding cap', value: breakdown.ceiling }
      : null
  return {
    base: breakdown.raw_score - sumDelta,
    modifiers,
    cap,
    finalScore: breakdown.final_score,
  }
}
