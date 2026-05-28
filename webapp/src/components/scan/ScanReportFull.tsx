import EmbedBadgeBox from '@ui/components/molecules/EmbedBadgeBox'
import InstallCommandBox from '@ui/components/molecules/InstallCommandBox'
import ScanReportHero from '@ui/components/molecules/ScanReportHero'
import SubScoreAccordion from '@ui/components/molecules/SubScoreAccordion'

import { track } from '@/lib/analytics'
import type { ScanReportDetail } from '@/lib/api/scans'

const SUB_SCORE_LABELS: Record<string, string> = {
  security: 'Security',
  supply_chain: 'Supply chain',
  maintenance: 'Maintenance',
  transparency: 'Transparency',
  community: 'Community',
}

const SUB_SCORE_KEYS = [
  'security',
  'supply_chain',
  'maintenance',
  'transparency',
  'community',
] as const

function _tierForScore(score: number): 'green' | 'yellow' | 'orange' | 'red' {
  if (score >= 80) return 'green'
  if (score >= 60) return 'yellow'
  if (score >= 40) return 'orange'
  return 'red'
}

interface Props {
  scan: ScanReportDetail
}

export default function ScanReportFull({ scan }: Props) {
  const subScores = SUB_SCORE_KEYS.map((key) => {
    const breakdown = (scan.score_breakdown as Record<string, Record<string, unknown>>)[key] ?? {}
    return {
      label: SUB_SCORE_LABELS[key],
      key,
      value: scan.sub_scores[key] ?? 0,
      weight: key === 'security' ? 35 : key === 'supply_chain' ? 20 : 15,
      finalSubScore: (breakdown.final_sub_score as number) ?? scan.sub_scores[key],
      criticalFloorApplied: Boolean(breakdown.critical_floor_applied),
    }
  })

  return (
    <section className="scan-report-full" aria-label="Scan report">
      <ScanReportHero
        score={scan.aggregate_score}
        tier={scan.tier}
        eyebrow="AGGREGATE"
        subScores={subScores}
        rightSlot={
          <InstallCommandBox
            slug={scan.slug}
            onCopy={(t) => track('scan_report_install_copied', { command_type: t })}
          />
        }
        mathSlot={
          <div className="report-hero-math-panel">
            <span className="eyebrow eyebrow-rule">AGGREGATE MATH</span>
            <pre>
              {String(
                (scan.score_breakdown as Record<string, Record<string, unknown>>)?.aggregate_math
                  ?.formula ?? ''
              )}
            </pre>
            <span>
              {String(
                (scan.score_breakdown as Record<string, Record<string, unknown>>)?.aggregate_math
                  ?.tier_mapping ?? ''
              )}
            </span>
          </div>
        }
      />

      <div className="scan-report-full-accordions">
        {SUB_SCORE_KEYS.map((key) => {
          const value = scan.sub_scores[key] ?? 0
          const findingsForKey = scan.findings.filter((f) => f.sub_score === key)
          return (
            <SubScoreAccordion
              key={key}
              label={SUB_SCORE_LABELS[key]}
              subScoreKey={key}
              value={value}
              weight={key === 'security' ? 35 : key === 'supply_chain' ? 20 : 15}
              tier={_tierForScore(value)}
              criticalFloorApplied={findingsForKey.some((f) => f.severity === 'critical')}
              defaultOpen={
                key === 'security' || findingsForKey.some((f) => f.severity === 'critical')
              }
              onExpand={(s) =>
                track('scan_report_subscore_expanded', {
                  sub_score: s as
                    | 'security'
                    | 'supply_chain'
                    | 'maintenance'
                    | 'transparency'
                    | 'community',
                })
              }
              findings={findingsForKey.map((f) => ({
                ruleId: f.rule_id,
                severity: f.severity,
                category: SUB_SCORE_LABELS[f.sub_score],
                finding: `${f.rule_id} fired against ${f.file_path}`,
                matchedContentSha256: f.matched_content_sha256,
                evidence: {
                  filePath: f.file_path,
                  lineStart: f.line_start,
                  lineEnd: f.line_end,
                  href: scan.github_url
                    ? `${scan.github_url.replace(/\/$/, '')}/blob/${scan.ref_sha}/${f.file_path}#L${f.line_start}`
                    : undefined,
                },
                remediationLink: f.remediation_link,
              }))}
            />
          )
        })}
      </div>

      <EmbedBadgeBox
        scanId={scan.id}
        score={scan.aggregate_score}
        slug={scan.slug}
        onCopy={(format) => track('scan_report_badge_copied', { format })}
      />

      <footer className="scan-report-full-footer">
        <span>
          Source: <a href={scan.github_url}>{scan.github_url}</a>
        </span>
        <span>
          Scan ID: <code>{scan.id}</code>
        </span>
        <span>
          Scanned:{' '}
          <time dateTime={scan.scanned_at}>{new Date(scan.scanned_at).toLocaleString()}</time>
        </span>
        <span>
          Methodology: <a href="/methodology">saferskills.ai/methodology</a>
        </span>
      </footer>
    </section>
  )
}
