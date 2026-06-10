import EvidenceWithheldNote from '@ui/components/atoms/EvidenceWithheldNote'
import RefChip from '@ui/components/atoms/RefChip'
import SeverityPill from '@ui/components/atoms/SeverityPill'
import OwaspFindingGroup from '@ui/components/molecules/OwaspFindingGroup'
import RedactedTranscript from '@ui/components/molecules/RedactedTranscript'
import RemediationTerminal from '@ui/components/molecules/RemediationTerminal'
import ScoreMathTable from '@ui/components/molecules/ScoreMathTable'
import { useEffect, useMemo, useRef, useState } from 'react'
import { findingRefChips, groupFindingsByFamily, scoreMathFor } from '@/lib/agent/findings-view'
import { findingRemediationMarkdown } from '@/lib/agent-report-markdown'
import type { AgentFindingRow, AgentScoreBreakdown } from '@/lib/api/agent-scan-types'

const Chevron = () => (
  <svg
    className="fc-chev"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    aria-hidden="true"
  >
    <path d="M4 6l4 4 4-4" />
  </svg>
)

interface Props {
  findings: AgentFindingRow[]
  scoreBreakdown: AgentScoreBreakdown | null
  /** Token route → hydrated transcript; public → withheld note. */
  unlisted: boolean
  /** Cross-tab "View finding →": the finding id to open + a nonce to re-trigger. */
  requestOpenId?: string | null
  requestNonce?: number
}

/** The evidence block per finding — route-driven split (D-5.6-03). */
function Evidence({ finding, unlisted }: { finding: AgentFindingRow; unlisted: boolean }) {
  const ex = finding.evidence_excerpt
  if (unlisted && ex) {
    const exfil = finding.leaked_canary_slot !== null && finding.verdict === 'vulnerable'
    return (
      <RedactedTranscript
        file={ex.file}
        lang={ex.lang}
        lines={ex.lines.map((l) => ({ lineNo: l.line_no, text: l.text, hit: l.hit }))}
        exfil={exfil}
      />
    )
  }
  // Unlisted but no excerpt → manifest-detected finding. Public → transcript withheld.
  return (
    <EvidenceWithheldNote
      text={
        unlisted ? 'no transcript for this finding' : 'transcript withheld on the public report'
      }
    />
  )
}

/**
 * Findings tab body (I-5.6 Phase B): findings grouped by OWASP family, each an
 * expandable `.find-card` reusing the DS finding-card chrome. Per card: severity
 * pill, rule meta, ref chips, why-it-matters, the per-finding score-math ledger,
 * the route-driven evidence (withheld note / redacted transcript / manifest note),
 * and the terminal remediation. Cross-tab "View finding →" opens + scrolls the
 * target card (reduced-motion honored).
 */
export default function AgentFindings({
  findings,
  scoreBreakdown,
  unlisted,
  requestOpenId = null,
  requestNonce = 0,
}: Props) {
  // Group + per-finding derivations (ref chips, score-math) are invariant across
  // card expand/collapse, so compute the whole view-model once per data change —
  // a card toggle re-renders but doesn't re-scan every finding.
  const groups = useMemo(
    () =>
      groupFindingsByFamily(findings).map((g) => ({
        family: g.family,
        index: g.index,
        refs: g.refs,
        cards: g.findings.map((f) => {
          const severity = f.severity ?? 'info'
          const inBreakdown = scoreBreakdown?.findings.some((m) => m.test_id === f.test_id) ?? false
          return {
            finding: f,
            severity,
            sevLabel: severity.toUpperCase(),
            math: inBreakdown ? scoreMathFor(scoreBreakdown, f.test_id) : null,
            refs: findingRefChips(f),
          }
        }),
      })),
    [findings, scoreBreakdown]
  )
  const rootRef = useRef<HTMLDivElement | null>(null)
  const [openIds, setOpenIds] = useState<Set<string>>(
    () => new Set(findings[0] ? [findings[0].id] : [])
  )

  // Cross-tab open: when the Report tab requests a finding, open it + scroll it
  // into view + focus its summary. `requestNonce` is a deliberate dep so a repeat
  // request on the SAME finding still re-fires (the effect body reads requestOpenId).
  // biome-ignore lint/correctness/useExhaustiveDependencies: requestNonce is the re-fire trigger
  useEffect(() => {
    if (!requestOpenId) return
    setOpenIds((prev) => new Set(prev).add(requestOpenId))
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    requestAnimationFrame(() => {
      const el = rootRef.current?.querySelector<HTMLElement>(
        `#finding-${CSS.escape(requestOpenId)}`
      )
      if (!el) return
      el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
      el.querySelector<HTMLElement>('summary')?.focus()
    })
  }, [requestNonce, requestOpenId])

  function toggle(id: string, open: boolean) {
    setOpenIds((prev) => {
      const next = new Set(prev)
      if (open) next.add(id)
      else next.delete(id)
      return next
    })
  }

  return (
    <div ref={rootRef}>
      {groups.map((g) => (
        <OwaspFindingGroup key={g.family} index={g.index} title={g.family} refs={g.refs}>
          {g.cards.map(({ finding: f, severity, sevLabel, math, refs }) => (
            <details
              className="find-card"
              id={`finding-${f.id}`}
              key={f.id}
              open={openIds.has(f.id)}
              onToggle={(e) => toggle(f.id, (e.currentTarget as HTMLDetailsElement).open)}
            >
              <summary>
                <SeverityPill severity={severity} label={sevLabel} />
                <span className="fc-titlewrap">
                  <span className="fc-title">{f.title || f.test_id}</span>
                  <span className="fc-rule">
                    {f.test_id} · {f.category_label ?? f.family ?? 'Finding'}
                  </span>
                </span>
                <span className="fc-right">
                  <Chevron />
                </span>
              </summary>

              <div className="fc-detail">
                {f.severity_rationale ? (
                  <div className={`fc-rationale ${severity}`}>
                    <b>{sevLabel}</b> — {f.severity_rationale}
                  </div>
                ) : null}

                {refs.length > 0 ? (
                  <div className="fc-refs">
                    {refs.map((r) => (
                      <RefChip key={`${r.kind}-${r.label}`} {...r} />
                    ))}
                  </div>
                ) : null}

                <div className="fc-why">
                  <div className="fc-lbl">Why it matters</div>
                  <p>{f.explanation}</p>
                </div>

                {math ? (
                  <div className="fc-scoremath">
                    <div className="fc-lbl">How the score moved</div>
                    <ScoreMathTable
                      base={math.base}
                      modifiers={math.modifiers}
                      cap={math.cap}
                      finalScore={math.finalScore}
                    />
                  </div>
                ) : null}

                <Evidence finding={f} unlisted={unlisted} />

                <RemediationTerminal
                  action={f.remediation?.action ?? ''}
                  steps={f.remediation?.steps}
                  saferPattern={f.remediation?.safer_pattern}
                  filename={`fix:${f.test_id}`}
                  copyText={findingRemediationMarkdown(f)}
                />
              </div>
            </details>
          ))}
        </OwaspFindingGroup>
      ))}
    </div>
  )
}
