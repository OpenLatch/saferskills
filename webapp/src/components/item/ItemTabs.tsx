import SegmentedTabs, { panelId } from '@ui/components/atoms/SegmentedTabs'
import { useEffect, useState } from 'react'

import {
  type DiffResponse,
  fetchItemDiff,
  type ManifestSource,
  type VersionPoint,
} from '@/lib/api/items'
import type { ScanReportDetail } from '@/lib/api/scans'
import { renderMarkdown } from '@/lib/markdown'
import { scoredTier, TIER_TO_STRIPE } from '@/lib/tier'

interface Props {
  slug: string
  scan: ScanReportDetail
  versions: VersionPoint[]
  manifest: ManifestSource | null
}

type TabKey = 'score' | 'versions' | 'source'

// 5-axis taxonomy + locked rubric weights (35/20/15/15/15), NOT the mockup's
// 40/20/15/15/10. Detector blurbs are descriptive config.
const CATS: { key: string; name: string; weight: number; detectors: string }[] = [
  { key: 'security', name: 'Security', weight: 35, detectors: 'prompt, exec, net, exfil, eval' },
  {
    key: 'supply_chain',
    name: 'Supply chain',
    weight: 20,
    detectors: 'hash, typosquat, maintainer, lockfile',
  },
  { key: 'maintenance', name: 'Maintenance', weight: 15, detectors: 'staleness, pinning, CI' },
  { key: 'transparency', name: 'Transparency', weight: 15, detectors: 'SKILL.md, perms, README' },
  { key: 'community', name: 'Community', weight: 15, detectors: 'installs, verify, response' },
]

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}
function vband(tier: string): string {
  return TIER_TO_STRIPE[scoredTier(tier) ?? 'red']
}

export default function ItemTabs({ slug, scan, versions, manifest }: Props) {
  const [tab, setTab] = useState<TabKey>('score')
  const [vi, setVi] = useState(0)
  const [mdRaw, setMdRaw] = useState(false)
  const [copied, setCopied] = useState(false)

  const sub = scan.sub_scores
  const findings = scan.findings

  return (
    <div className="sk-col-main">
      <SegmentedTabs
        variant="underline"
        idBase="itemtabs"
        ariaLabel="Item report sections"
        value={tab}
        onChange={(id) => setTab(id as TabKey)}
        tabs={[
          { id: 'score', label: 'Score breakdown', count: findings.length },
          { id: 'versions', label: 'Version history', count: versions.length },
          { id: 'source', label: 'Source' },
        ]}
      />

      {/* ===== SCORE BREAKDOWN ===== */}
      <div
        className="sk-panel"
        data-panel="score"
        id={panelId('itemtabs', 'score')}
        role="tabpanel"
        aria-labelledby="itemtabs-tab-score"
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
                    <em>No findings in this category for the latest scan.</em>
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

      {/* ===== VERSION HISTORY ===== */}
      <div
        className="sk-panel"
        data-panel="versions"
        id={panelId('itemtabs', 'versions')}
        role="tabpanel"
        aria-labelledby="itemtabs-tab-versions"
        hidden={tab !== 'versions'}
      >
        <div className="sk-block-head">
          <p className="panel-desc">
            Every scanned point with the score it earned and what moved between them.
          </p>
          <span className="sk-block-meta">{versions.length} scans · 90 days</span>
        </div>
        {versions.length === 0 ? (
          <p className="panel-desc">No scans recorded yet.</p>
        ) : (
          <div className="diffwrap">
            <div className="ver-rail">
              {versions.map((v, i) => (
                <button
                  type="button"
                  key={v.ref_sha + v.scanned_at}
                  className={`ver-row${i === vi ? ' on' : ''}`}
                  onClick={() => setVi(i)}
                >
                  <div className="v-top">
                    <span className="v-tag">{v.tag ?? v.ref_sha.slice(0, 7)}</span>
                    {i === 0 && <span className="v-latest">latest</span>}
                  </div>
                  <span className="v-date">{fmtDate(v.scanned_at)}</span>
                  <span className={`v-score vs-${vband(v.tier)}`}>
                    <span className="vs-num">{v.aggregate_score}</span>
                    <span className="vs-bar">
                      <i style={{ width: `${v.aggregate_score}%` }} />
                    </span>
                  </span>
                </button>
              ))}
            </div>
            <VersionDiff slug={slug} selected={versions[vi]} older={versions[vi + 1] ?? null} />
          </div>
        )}
      </div>

      {/* ===== SOURCE ===== */}
      <div
        className="sk-panel"
        data-panel="source"
        id={panelId('itemtabs', 'source')}
        role="tabpanel"
        aria-labelledby="itemtabs-tab-source"
        hidden={tab !== 'source'}
      >
        <div className="sk-block-head">
          <p className="panel-desc">
            The primary manifest — the file an agent reads to learn what this artifact does.
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
          <p className="panel-desc">Source manifest not captured for this scan yet.</p>
        )}
      </div>
    </div>
  )
}

// Pre-keyed diff render model — unique stable keys (no array-index keys) for the
// repeated hunk/line lists, assigned once when a DiffResponse arrives.
interface DiffModelLine {
  key: string
  type: 'add' | 'del' | 'ctx'
  text: string
  gutter: string
}
interface DiffModelHunk {
  key: string
  header: string
  lines: DiffModelLine[]
}
interface DiffModelFile {
  key: string
  path: string
  status: string
  note?: string | null
  hunks: DiffModelHunk[]
}

const STATUS_LABEL: Record<string, string> = {
  added: 'added',
  removed: 'removed',
  modified: 'modified',
  binary: 'binary',
}

function toDiffModel(data: DiffResponse): DiffModelFile[] {
  let n = 0
  return data.files.map((f) => ({
    key: `f${n++}`,
    path: f.path,
    status: f.status,
    note: f.note,
    hunks: f.hunks.map((h) => ({
      key: `h${n++}`,
      header: h.header,
      lines: h.lines.map((l) => ({ key: `l${n++}`, type: l.type, text: l.text, gutter: l.gutter })),
    })),
  }))
}

function DiffBody({
  slug,
  selected,
  older,
}: {
  slug: string
  selected: VersionPoint
  older: VersionPoint
}) {
  const [state, setState] = useState<
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'error' }
    | { kind: 'ready'; files: DiffModelFile[]; truncated: boolean }
  >({ kind: 'idle' })

  const bothStored = selected.has_snapshot && older.has_snapshot

  useEffect(() => {
    if (!bothStored) {
      setState({ kind: 'idle' })
      return
    }
    let cancelled = false
    setState({ kind: 'loading' })
    fetchItemDiff(slug, selected.scan_id, older.scan_id)
      .then((data) => {
        if (cancelled) return
        setState({ kind: 'ready', files: toDiffModel(data), truncated: data.truncated })
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [slug, selected.scan_id, older.scan_id, bothStored])

  if (!bothStored) {
    return (
      <div className="diff-body">
        <div className="diff-file">
          No stored snapshot for one of these scans — file diffs appear once both versions are
          captured.
        </div>
      </div>
    )
  }
  if (state.kind === 'loading' || state.kind === 'idle') {
    return (
      <div className="diff-body">
        <div className="diff-file">Computing diff…</div>
      </div>
    )
  }
  if (state.kind === 'error') {
    return (
      <div className="diff-body">
        <div className="diff-file">Could not load the diff for these scans.</div>
      </div>
    )
  }
  if (state.files.length === 0) {
    return (
      <div className="diff-body">
        <div className="diff-file">No file changes between these snapshots.</div>
      </div>
    )
  }
  return (
    <div className="diff-body">
      {state.files.map((f) => (
        <div key={f.key}>
          <div className="diff-file">
            {STATUS_LABEL[f.status] ?? f.status} · {f.path}
            {f.note ? ` — ${f.note}` : ''}
          </div>
          {f.hunks.map((h) => (
            <div key={h.key}>
              <div className="diff-hunk">{h.header}</div>
              {h.lines.map((ln) => (
                <div key={ln.key} className={`diff-line ${ln.type}`}>
                  <span className="gut">{ln.type === 'add' ? '' : ln.gutter}</span>
                  <span className="sign">
                    {ln.type === 'add' ? '+' : ln.type === 'del' ? '-' : ' '}
                  </span>
                  <span className="txt">{ln.text}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      ))}
      {state.truncated && (
        <div className="diff-file">Diff truncated — too large to render in full.</div>
      )}
    </div>
  )
}

function VersionDiff({
  slug,
  selected,
  older,
}: {
  slug: string
  selected: VersionPoint
  older: VersionPoint | null
}) {
  const selTag = selected.tag ?? selected.ref_sha.slice(0, 7)
  if (!older) {
    return (
      <div className="diff-panel">
        <div className="diff-head">
          <div className="dh-top">
            <span className="dh-compare">
              <span className="tag">{selTag}</span>
            </span>
          </div>
          <p className="dh-summary">First recorded scan — no prior version to compare against.</p>
        </div>
      </div>
    )
  }
  const oldTag = older.tag ?? older.ref_sha.slice(0, 7)
  const d = selected.aggregate_score - older.aggregate_score
  const dCls = d > 0 ? 'up' : d < 0 ? 'dn' : 'flat'
  const chips = CATS.map((c) => {
    const cd = (selected.sub_scores[c.key] ?? 0) - (older.sub_scores[c.key] ?? 0)
    return { name: c.name.toLowerCase(), cd }
  }).filter((x) => x.cd !== 0)

  return (
    <div className="diff-panel">
      <div className="diff-head">
        <div className="dh-top">
          <span className="dh-compare">
            <span className="tag">{oldTag}</span>
            <span className="arrow">→</span>
            <span className="tag">{selTag}</span>
          </span>
          <span className="dh-score">
            {older.aggregate_score} → <b>{selected.aggregate_score}</b>
            <span className={`dh-delta ${dCls}`}>
              {d > 0 ? '+' : ''}
              {d === 0 ? '±0' : d}
            </span>
          </span>
        </div>
        <p className="dh-summary">
          {d > 0
            ? `Score rose ${d} point${d === 1 ? '' : 's'} between these scans.`
            : d < 0
              ? `Score fell ${-d} point${d === -1 ? '' : 's'} between these scans.`
              : 'Aggregate score unchanged between these scans.'}
        </p>
        <div className="dh-tags">
          {chips.length === 0 ? (
            <span className="chip">no category movement</span>
          ) : (
            chips.map((x) => (
              <span key={x.name} className={`chip ${x.cd > 0 ? 'sec-up' : 'sec-dn'}`}>
                {x.name} {x.cd > 0 ? '+' : ''}
                {x.cd}
              </span>
            ))
          )}
        </div>
      </div>
      <DiffBody slug={slug} selected={selected} older={older} />
    </div>
  )
}
