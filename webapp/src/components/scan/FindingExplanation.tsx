import FindingDetail from '@ui/components/molecules/FindingDetail'

import { track } from '@/lib/analytics'
import type { Finding } from '@/lib/api/scans'
import { groupFindings, resolveFindingDetail } from '@/lib/findings/explain'

interface Props {
  /** Flat findings for one capability (or one category) — grouped + deduped here. */
  findings: Finding[]
  /** Repo coordinates for the GitHub evidence link (omit for uploads). */
  githubUrl?: string | null
  refSha?: string | null
  rubricVersion?: string | null
  /** Expand the first card (the repo cap-body opens its first finding). */
  openFirst?: boolean
}

/**
 * Composes the shared DS `FindingDetail` (the v3 `.find-card`) from a capability's
 * findings + the generated `RULE_CONTENT` map. THE one place the content map is
 * imported — `ui/` stays pure. Used by both surfaces: the repo scan cap-bodies
 * (`ScanReportView`) and the per-capability checklist (`CheckGroupList`'s
 * flagged-category slot). Renders one deduped card per `(rule_id, file)`.
 */
export default function FindingExplanation({
  findings,
  githubUrl,
  refSha,
  rubricVersion,
  openFirst = false,
}: Props) {
  const groups = groupFindings(findings)
  if (groups.length === 0) return null
  return (
    <div className="find-cards">
      {groups.map((group, i) => {
        const props = resolveFindingDetail(group, { githubUrl, refSha, rubricVersion })
        return (
          <FindingDetail
            key={`${group.ruleId}@@${group.file}`}
            {...props}
            defaultOpen={openFirst && i === 0}
            onExpand={() => track('scan_report_finding_expanded', { rule_id: group.ruleId })}
          />
        )
      })}
    </div>
  )
}
