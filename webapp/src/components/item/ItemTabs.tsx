import SegmentedTabs, { panelId } from '@ui/components/atoms/SegmentedTabs'
import CheckGroupList from '@ui/components/molecules/CheckGroupList'
import MarkdownSourceViewer from '@ui/components/molecules/MarkdownSourceViewer'
import ScoreBreakdownTable from '@ui/components/molecules/ScoreBreakdownTable'
import { useEffect, useState } from 'react'
import FindingExplanation from '@/components/scan/FindingExplanation'
import {
  type DiffResponse,
  fetchItemDiff,
  type ManifestSource,
  type VersionPoint,
} from '@/lib/api/items'
import type { ScanReportDetail } from '@/lib/api/scans'
import { renderMarkdown } from '@/lib/markdown'
import { SCORE_CATEGORIES } from '@/lib/scoring'
import { scoredTier, TIER_TO_STRIPE } from '@/lib/tier'

interface Props {
  slug: string
  scan: ScanReportDetail
  versions: VersionPoint[]
  manifest: ManifestSource | null
}

/** Short label for a version row: release tag → short ref SHA → short scan id
 *  (uploads have neither tag nor ref SHA, so they fall back to the scan id). */
function versionTag(v: VersionPoint): string {
  return v.tag ?? (v.ref_sha ? v.ref_sha.slice(0, 7) : v.scan_id.slice(0, 7))
}

type TabKey = 'score' | 'versions' | 'source'

// 5-axis taxonomy + locked weights — shared with the upload report breakdown
// (`CapabilityReportTabs`). NOT the mockup's 40/20/15/15/10.
const CATS = SCORE_CATEGORIES

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
          emptyScanNoun="the latest scan"
          renderCategoryFindings={(key) => (
            <FindingExplanation
              findings={findings.filter((f) => f.sub_score === key)}
              githubUrl={scan.github_url}
              refSha={scan.ref_sha}
              rubricVersion={scan.rubric_version}
            />
          )}
        />
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
                  key={v.scan_id}
                  className={`ver-row${i === vi ? ' on' : ''}`}
                  onClick={() => setVi(i)}
                >
                  <div className="v-top">
                    <span className="v-tag">{versionTag(v)}</span>
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
          <MarkdownSourceViewer
            path={manifest.path}
            bytes={manifest.bytes}
            content={manifest.content}
            renderedHtml={renderMarkdown(manifest.content)}
          />
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
  const selTag = versionTag(selected)
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
  const oldTag = versionTag(older)
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
