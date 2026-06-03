import SegmentedTabs, { panelId } from '@ui/components/atoms/SegmentedTabs'
import CheckGroupList from '@ui/components/molecules/CheckGroupList'
import MarkdownSourceViewer from '@ui/components/molecules/MarkdownSourceViewer'
import ScoreBreakdownTable from '@ui/components/molecules/ScoreBreakdownTable'
import { useState } from 'react'

import FindingExplanation from '@/components/scan/FindingExplanation'

import type { ManifestSource } from '@/lib/api/items'
import type { CapabilityRow } from '@/lib/api/scans'
import { renderMarkdown } from '@/lib/markdown'
import { SCORE_CATEGORIES } from '@/lib/scoring'

/**
 * Left column of the rich single-capability report (mockups 3 + 4): a
 * `Score breakdown | Source` tab pair driven by the run's single capability.
 *
 * This is the upload/unlisted analogue of `ItemTabs` minus version history
 * (uploads have no catalog version rail). It renders entirely from the run
 * report DTO — `cap.sub_scores` + `cap.findings` for the breakdown, `manifest`
 * for the source viewer — so it works for public uploads (`/scans/<run_id>`)
 * and unlisted ones (`/scans/r/<token>`) identically.
 */

// 5-axis taxonomy + locked weights — shared with the item-detail breakdown
// (`ItemTabs`) so the two surfaces score-explain identically.
const CATS = SCORE_CATEGORIES

interface Props {
  cap: CapabilityRow
  manifest?: ManifestSource | null
}

type TabKey = 'score' | 'source'

export default function CapabilityReportTabs({ cap, manifest }: Props) {
  const [tab, setTab] = useState<TabKey>('score')

  const sub = cap.sub_scores
  const findings = cap.findings

  function onChange(id: string) {
    setTab(id as TabKey)
  }

  return (
    <div className="sk-col-main">
      <SegmentedTabs
        variant="underline"
        idBase="captabs"
        ariaLabel="Report sections"
        value={tab}
        onChange={onChange}
        tabs={[
          { id: 'score', label: 'Score breakdown', count: findings.length },
          { id: 'source', label: 'Source' },
        ]}
      />

      {/* ===== SCORE BREAKDOWN ===== */}
      <div
        className="sk-panel"
        data-panel="score"
        id={panelId('captabs', 'score')}
        role="tabpanel"
        aria-labelledby="captabs-tab-score"
        hidden={tab !== 'score'}
      >
        <ScoreBreakdownTable categories={CATS} subScores={sub} />

        <CheckGroupList
          categories={CATS}
          subScores={sub}
          findings={findings.map((f) => ({
            id: f.id,
            ruleId: f.rule_id,
            severity: f.severity,
            subScore: f.sub_score,
            filePath: f.file_path,
            lineStart: f.line_start,
          }))}
          renderCategoryFindings={(key) => (
            <FindingExplanation
              findings={findings.filter((f) => f.sub_score === key)}
              rubricVersion={findings[0]?.rubric_version}
            />
          )}
        />
      </div>

      {/* ===== SOURCE ===== */}
      <div
        className="sk-panel"
        data-panel="source"
        id={panelId('captabs', 'source')}
        role="tabpanel"
        aria-labelledby="captabs-tab-source"
        hidden={tab !== 'source'}
      >
        <div className="sk-block-head">
          <p className="panel-desc">
            The primary manifest found in the scanned artifact — the file an agent reads to learn
            what this {cap.kind === 'mcp_server' ? 'MCP server' : cap.kind} does.
          </p>
          {manifest && <span className="sk-block-meta">{manifest.path} · 1 file</span>}
        </div>
        {manifest ? (
          <MarkdownSourceViewer
            path={manifest.path}
            bytes={manifest.bytes}
            content={manifest.content}
            renderedHtml={renderMarkdown(manifest.content)}
          />
        ) : (
          <p className="panel-desc">Source manifest not captured for this scan.</p>
        )}
      </div>
    </div>
  )
}
