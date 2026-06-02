import SegmentedTabs, { panelId } from '@ui/components/atoms/SegmentedTabs'
import { useState } from 'react'

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
  const [mdRaw, setMdRaw] = useState(false)
  const [copied, setCopied] = useState(false)

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
        <div className="score-cats">
          <div className="sc-row sc-head">
            <span>Category</span>
            <span>Weight</span>
            <span>Category score</span>
            <span style={{ textAlign: 'right' }}>Contribution</span>
          </div>
          {CATS.map((c) => {
            const cs = sub[c.key] ?? 0
            const contrib = ((cs * c.weight) / 100).toFixed(1)
            return (
              <div className="sc-row" key={c.key}>
                <div className="sc-cat">
                  <b>{c.name}</b>
                  <span>{c.detectors}</span>
                </div>
                <div className="sc-weight">{c.weight}%</div>
                <div className="sc-bar">
                  <span className="num">{cs}</span>
                  <span className="track">
                    <i style={{ width: `${cs}%` }} />
                  </span>
                </div>
                <div className="sc-contrib">
                  <b>{contrib}</b> pts
                </div>
              </div>
            )
          })}
        </div>

        <p className="score-checks-head">Findings &amp; checks · {findings.length} flagged</p>
        {CATS.map((c) => {
          const catFindings = findings.filter((f) => f.sub_score === c.key)
          return (
            <div className="chk-group" key={c.key}>
              <div className="chk-head">
                <span className="cg-name">{c.name}</span>
                <span className="cg-meta">
                  score {sub[c.key] ?? 0} · {catFindings.length} finding
                  {catFindings.length === 1 ? '' : 's'}
                </span>
              </div>
              {catFindings.length === 0 ? (
                <div className="chk-row pass">
                  <span className="chk-st">✓</span>
                  <span className="chk-id">—</span>
                  <span className="chk-tt">
                    All {c.name.toLowerCase()} checks passed
                    <em>No findings in this category for this scan.</em>
                  </span>
                  <span className="chk-res">pass</span>
                </div>
              ) : (
                catFindings.map((f) => {
                  const fail = f.severity === 'high' || f.severity === 'critical'
                  return (
                    <div className={`chk-row ${fail ? 'fail' : 'warn'}`} key={f.id}>
                      <span className="chk-st">{fail ? '✕' : '⚠'}</span>
                      <span className="chk-id">{f.rule_id}</span>
                      <span className="chk-tt">
                        {f.severity} finding
                        <em>
                          {f.file_path}:{f.line_start}
                        </em>
                      </span>
                      <span className="chk-res">{f.severity}</span>
                    </div>
                  )
                })
              )}
            </div>
          )
        })}
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
          <div className="md-viewer">
            <div className="md-bar">
              <span className="md-dot r" />
              <span className="md-dot y" />
              <span className="md-dot g" />
              <span className="md-file">{manifest.path}</span>
              <span className="md-bytes">{(manifest.bytes / 1024).toFixed(1)} KB · Markdown</span>
              <div className="md-tools">
                <button
                  type="button"
                  className={`md-tab${mdRaw ? '' : ' on'}`}
                  onClick={() => setMdRaw(false)}
                >
                  Rendered
                </button>
                <button
                  type="button"
                  className={`md-tab${mdRaw ? ' on' : ''}`}
                  onClick={() => setMdRaw(true)}
                >
                  Raw
                </button>
                <button
                  type="button"
                  className="md-copy"
                  onClick={() => {
                    navigator.clipboard?.writeText(manifest.content)
                    setCopied(true)
                    setTimeout(() => setCopied(false), 1500)
                  }}
                >
                  {copied ? '✓ Copied' : '⧉ Copy'}
                </button>
              </div>
            </div>
            {mdRaw ? (
              <pre className="md-raw">{manifest.content}</pre>
            ) : (
              <div className="md-body">{renderMarkdown(manifest.content)}</div>
            )}
          </div>
        ) : (
          <p className="panel-desc">Source manifest not captured for this scan.</p>
        )}
      </div>
    </div>
  )
}
