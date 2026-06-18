import Button from '@ui/components/atoms/Button'
import ButtonPair from '@ui/components/atoms/ButtonPair'
import Toast, { flashToast } from '@ui/components/atoms/Toast'
import { useMemo, useState } from 'react'

import { bandFromTier, kindTag } from '@/components/catalog/constants'
import FindingExplanation from '@/components/scan/FindingExplanation'
import { track } from '@/lib/analytics'
import type { CapabilityKind, CapabilityRow, ScanRunReportDetail } from '@/lib/api/scans'

// Map a catalog kind onto the mockup's 3-glyph type vocabulary (+ plugin/rules).
const GLYPH_CLASS: Record<CapabilityKind, string> = {
  skill: 'skill',
  mcp_server: 'mcp',
  hook: 'hook',
  plugin: 'plugin',
  rules: 'rules',
}

type FilterKind = 'all' | CapabilityKind

interface Props {
  run: ScanRunReportDetail
  /** Permalink of this report, copied by the Share button. */
  shareUrl: string
}

/** Summary chip text + class from a capability's findings counts. */
function summaryFor(cap: CapabilityRow): { label: string; cls: 'clear' | 'warn' | 'high' } {
  const { total, critical, high } = cap.findings_summary
  if (total === 0) return { label: 'all clear', cls: 'clear' }
  if (critical + high > 0) {
    const n = critical + high
    return { label: `${n} high · ${total} finding${total === 1 ? '' : 's'}`, cls: 'high' }
  }
  return { label: `${total} warning${total === 1 ? '' : 's'}`, cls: 'warn' }
}

/**
 * Capabilities surface for a completed repo scan (`/scans/<run_id>` body).
 *
 * Renders the `.cap-list` of every Skill / MCP / Hook / Plugin / Rules
 * capability discovered in the repo — each with its own security score, a type
 * filter, expand-to-findings, the aggregate-math band (how the consolidated
 * capabilities mean rolls up), and the catalog CTA. No per-capability data is
 * fabricated: every score, finding, and slug comes from the run report DTO.
 */
export default function ScanReportView({ run, shareUrl }: Props) {
  const [filter, setFilter] = useState<FilterKind>('all')

  // Unlisted runs key on per-run SHADOW catalog_items that 404 on /items/<slug>.
  // Hide every public-catalog link + the "added to the catalog"
  // copy for them — those items are not in the public catalog.
  const isUnlisted = run.visibility === 'unlisted'
  const caps = run.capabilities
  // Kinds present, ordered by first appearance, for the filter chips.
  const kindsPresent = useMemo(() => {
    const seen: CapabilityKind[] = []
    for (const c of caps) if (!seen.includes(c.kind)) seen.push(c.kind)
    return seen
  }, [caps])

  const countByKind = (k: CapabilityKind) => caps.filter((c) => c.kind === k).length
  const visible = filter === 'all' ? caps : caps.filter((c) => c.kind === filter)

  function applyFilter(next: FilterKind) {
    setFilter(next)
    track('scan_report_capability_filtered', { kind: next })
  }

  function copyShare() {
    if (!navigator.clipboard) {
      flashToast('Copy failed — please copy manually')
      return
    }
    navigator.clipboard.writeText(shareUrl).then(
      () => flashToast(`Copied · ${shareUrl.length > 38 ? `${shareUrl.slice(0, 38)}…` : shareUrl}`),
      () => flashToast('Copy failed — please copy manually')
    )
  }

  return (
    <>
      <div className="sr-block-head">
        <h3>
          Capabilities discovered
          <span className="sub">— {run.capability_count} in this repo</span>
        </h3>
        {/* biome-ignore lint/a11y/useSemanticElements: segmented toolbar — role=group is the correct ARIA, a fieldset would impose form chrome */}
        <div className="cap-filter" role="group" aria-label="Filter capabilities by type">
          <button
            type="button"
            className={`cf${filter === 'all' ? ' on' : ''}`}
            onClick={() => applyFilter('all')}
          >
            All<span className="ct">{caps.length}</span>
          </button>
          {kindsPresent.map((k) => (
            <button
              key={k}
              type="button"
              className={`cf${filter === k ? ' on' : ''}`}
              onClick={() => applyFilter(k)}
            >
              {kindTag(k)}
              <span className="ct">{countByKind(k)}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="cap-list">
        <div className="cap-row cap-headrow">
          <span>Type</span>
          <span>Capability</span>
          <span>Security summary</span>
          <span>Score</span>
          <span>Catalog</span>
        </div>

        {visible.map((cap) => {
          const band = bandFromTier(cap.tier, cap.aggregate_score) ?? 'r'
          const glyph = GLYPH_CLASS[cap.kind]
          const summary = summaryFor(cap)
          const itemHref = `/items/${cap.catalog_slug}`
          return (
            <details
              key={cap.scan_id}
              onToggle={(e) => {
                if ((e.currentTarget as HTMLDetailsElement).open) {
                  track('scan_report_capability_expanded', { kind: cap.kind })
                }
              }}
            >
              <summary className={`cap-row ${band}`}>
                <span className={`cap-type ${glyph}`}>
                  <span className="g-mk" aria-hidden="true" />
                  {kindTag(cap.kind)}
                </span>
                <div className="cap-id">
                  <span className="nm">{cap.name}</span>
                  {cap.component_path && <span className="pth">{cap.component_path}</span>}
                </div>
                <div className="cap-note">
                  Scored against the {kindTag(cap.kind)} rubric — {cap.findings_summary.total}{' '}
                  finding{cap.findings_summary.total === 1 ? '' : 's'} across 5 categories.
                  <span className={`find ${summary.cls}`}>{summary.label}</span>
                </div>
                <div className="cap-score">
                  <span className="num">
                    {cap.aggregate_score}
                    <i>/100</i>
                  </span>
                </div>
                <div className="cap-action">
                  {isUnlisted ? (
                    <span className="cap-private">Private</span>
                  ) : (
                    <a className="open" href={itemHref}>
                      View in catalog →
                    </a>
                  )}
                </div>
              </summary>
              <div className="cap-body">
                {cap.findings.length === 0 ? (
                  <p className="cap-clear">
                    No findings — every {kindTag(cap.kind)} detector passed for this capability.
                  </p>
                ) : (
                  <FindingExplanation
                    findings={cap.findings}
                    githubUrl={run.github_url}
                    refSha={run.ref_sha}
                    rubricVersion={run.rubric_version}
                    openFirst
                  />
                )}
              </div>
            </details>
          )
        })}
      </div>

      {isUnlisted ? (
        <div className="sr-catalog">
          <div className="cl-l">
            <h4>These capabilities stay private</h4>
            <p>
              This scan is unlisted — its {run.capability_count} capabilit
              {run.capability_count === 1 ? 'y is' : 'ies are'} not in the public catalog and won't
              appear in search. Promote it to public to list them with scores and install commands.
            </p>
          </div>
          <div className="cl-r">
            <ButtonPair>
              <Button variant="paper" size="lg" onClick={copyShare}>
                ⧉ Copy private link
              </Button>
            </ButtonPair>
          </div>
        </div>
      ) : (
        <div className="sr-catalog">
          <div className="cl-l">
            <h4>See these capabilities in the SaferSkills catalog</h4>
            <p>
              All {run.capability_count} discovered capabilit
              {run.capability_count === 1 ? 'y has' : 'ies have'} been added to the public catalog
              with their scores, version history, and install commands.
            </p>
          </div>
          <div className="cl-r">
            <ButtonPair>
              <Button as="a" variant="primary" size="lg" href="/capabilities">
                View {run.capability_count} in catalog →
              </Button>
              <Button variant="paper" size="lg" onClick={copyShare}>
                ⧉ Share report
              </Button>
            </ButtonPair>
          </div>
        </div>
      )}

      <Toast />
    </>
  )
}
