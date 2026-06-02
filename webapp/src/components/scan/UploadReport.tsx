import BandPill from '@ui/components/atoms/BandPill'
import CopyIconButton from '@ui/components/atoms/CopyIconButton'
import { useState } from 'react'
import { kindTag } from '@/components/catalog/constants'
import CapabilityReportTabs from '@/components/scan/CapabilityReportTabs'
import FileTabStrip from '@/components/scan/FileTabStrip'
import ShareResultBand from '@/components/scan/ShareResultBand'
import { track } from '@/lib/analytics'
import { itemDownloadUrl } from '@/lib/api/items'
import type { CapabilityKind, CapabilityRow, ScanRunReportDetail } from '@/lib/api/scans'
import { unlistedDownloadUrl } from '@/lib/api/scans'
import { scanIdShort, shortHash } from '@/lib/report-identity'
import { scoredTier, TIER_TO_STRIPE } from '@/lib/tier'

/**
 * The rich upload report body (mockups 3/4) for EVERY upload — single OR
 * multi-file. One capability ⇒ no tab strip, byte-identical to the prior Astro
 * rich layout (the single-file regression gate). Two or more ⇒ a file-tab strip
 * (`FileTabStrip`) above the body; switching tabs swaps the whole per-file body
 * (score box · provenance · breakdown/Source tabs · side cards · badge band).
 *
 * Each tab shows its own file's provenance SHA-256 (`cap.content_hash`) with a
 * discreet copy icon; a single-file upload shows the run-level `artifact_sha256`.
 */

interface Props {
  run: ScanRunReportDetail
  ruleCount: number
  unlisted?: boolean
  token?: string
}

const PANEL_ID = 'mf-panel'
const TAB_ID_BASE = 'mf-tab'

function kindLabelOf(kind: CapabilityKind): string {
  if (kind === 'mcp_server') return 'MCP server'
  if (kind === 'skill') return 'Agent Skill'
  return kindTag(kind)
}

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })

export default function UploadReport({ run, ruleCount, unlisted = false, token }: Props) {
  const caps = run.capabilities
  const multi = run.capability_count > 1
  const [active, setActive] = useState(0)
  const cap: CapabilityRow | undefined = caps[Math.min(active, caps.length - 1)] ?? caps[0]

  function selectFile(i: number) {
    setActive(i)
    const next = caps[i]
    if (next) track('scan_report_file_selected', { kind: next.kind })
  }

  // ── run-level provenance (shared across all file tabs) ──────────────────────
  const runShaFull = run.artifact_sha256 ?? ''
  const scanIdLabel = scanIdShort(run.id)
  const uploadExt = (run.uploaded_filename ?? '').toLowerCase().endsWith('.zip') ? '.zip' : 'file'
  const rubricShort = run.rubric_version.slice(0, 7)
  const scannedOn = fmtDate(run.scanned_at)

  if (!cap) return null

  // ── per active capability ──────────────────────────────────────────────────
  const score = cap.aggregate_score
  const scored = scoredTier(cap.tier)
  const tierLetter = scored ? TIER_TO_STRIPE[scored] : ''
  const tierName = scored ? scored.charAt(0).toUpperCase() + scored.slice(1) : 'Unscored'
  const dotsFilled = Math.max(0, Math.min(10, Math.round(score / 10)))
  const kindLabel = kindLabelOf(cap.kind)

  const highFindings = cap.findings_summary.critical + cap.findings_summary.high
  const warnFindings = cap.findings_summary.total - highFindings

  // Per-file provenance hash on a multi-file upload (each tab = its own file's
  // sha256); the run-level combined hash for a single-file upload.
  const shaFull = multi ? (cap.content_hash ?? runShaFull) : runShaFull
  const shaShort = shortHash(shaFull)

  const fileLabel = cap.name || run.uploaded_filename || 'uploaded artifact'
  const zipHref =
    unlisted && token
      ? unlistedDownloadUrl(token)
      : itemDownloadUrl(cap.catalog_slug, cap.download?.scan_id ?? undefined)
  const zipSizeKb = cap.download ? (cap.download.byte_size / 1024).toFixed(1) : null

  // ── share/badge band copy (upload variant) ──────────────────────────────────
  const shareSub =
    'Public uploads are permanent and reproducible — the badge resolves to this scan by its content hash.'
  const shareFoot = `Identified by content hash; reproducible by re-running rubric ${rubricShort} against the same bytes.`

  const body = (
    <>
      <section className="sk-stat-band">
        <div className="container">
          <div className="sk-stat-grid">
            <div className="sk-scorebox">
              <div className="sb-score">
                <span className="sb-eyebrow">Security score</span>
                <div className="sb-big">
                  {score}
                  <span className="sb-denom">/100</span>
                </div>
                <div className="dots">
                  {tierLetter && (
                    <span className={`dot-${tierLetter}`}>{'●'.repeat(dotsFilled)}</span>
                  )}
                  <span className="dot-off">{'○'.repeat(10 - dotsFilled)}</span>
                </div>
                {scored ? (
                  <BandPill tier={scored} label={`${tierName} band`} />
                ) : (
                  <span className="band-pill unscoped">UNSCORED</span>
                )}
              </div>
              <div className="sb-facts">
                <span className="sb-eyebrow">This scan</span>
                <div className="fact">
                  <span>Source</span>
                  <b>Uploaded artifact</b>
                </div>
                <div className="fact">
                  <span>Scanned</span>
                  <b>{scannedOn}</b>
                </div>
                <div className="fact">
                  <span>Detectors</span>
                  <b>{ruleCount} checks · 5 categories</b>
                </div>
                <div className="fact">
                  <span>Findings</span>
                  <b>
                    {warnFindings} warning{warnFindings === 1 ? '' : 's'} · {highFindings} high
                  </b>
                </div>
                <div className="fact">
                  <span>Engine</span>
                  <b>rubric {rubricShort}</b>
                </div>
                <a className="sb-method" href="/methodology">
                  View methodology →
                </a>
              </div>
            </div>

            <div className="sk-installbox sk-installbox--meta">
              <span className="sb-eyebrow">Provenance</span>
              <div className="ins-row">
                <span>Source</span>
                <b>Uploaded&nbsp;{uploadExt}</b>
              </div>
              <div className="ins-row">
                <span>SHA-256</span>
                <b className="sha-cell">
                  {shaShort}
                  {shaFull && <CopyIconButton value={shaFull} label="Copy SHA-256" />}
                </b>
              </div>
              <div className="ins-row">
                <span>Scan ID</span>
                <b>{scanIdLabel}</b>
              </div>
              <div className="ins-row">
                <span>Signed by</span>
                <b>openlatch-audit-key-v1</b>
              </div>
              <div className="ins-distrib">
                <div className="legend" style={{ justifyContent: 'flex-start', gap: 0 }}>
                  <span>Content-addressed · permanent · re-scan only by re-upload</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="sk-main">
        <div className="container">
          <div className="sk-grid">
            <CapabilityReportTabs cap={cap} manifest={cap.manifest ?? null} />

            <aside className="sk-col-side">
              <div className="side-card install-card">
                <h4>Scanned artifact</h4>
                <p className="install-note">
                  Scanned from an uploaded artifact — no install command. Download the exact bytes
                  we scored:
                </p>
                <div className="install-cta">
                  <a className="btn primary sm" href={zipHref} download>
                    ⤓ Download scanned bytes (.zip)
                  </a>
                  <span className="zip-meta">
                    {fileLabel}
                    {zipSizeKb ? ` · ${zipSizeKb} KB` : ''}
                  </span>
                </div>
                <div className="install-count">
                  <span className="ic-num">90d+</span>
                  <span className="ic-lbl">
                    {unlisted
                      ? 'unlisted uploads expire after 90 days'
                      : 'public uploads are permanent & reproducible'}
                  </span>
                </div>
              </div>

              <div className="side-card pkg-card">
                <h4>Artifact</h4>
                <dl className="pkg-dl">
                  <div>
                    <dt>Detected</dt>
                    <dd>{kindLabel}</dd>
                  </div>
                  <div>
                    <dt>SHA-256</dt>
                    <dd className="sha-cell">
                      {shaShort}
                      {shaFull && <CopyIconButton value={shaFull} label="Copy SHA-256" />}
                    </dd>
                  </div>
                  {zipSizeKb && (
                    <div>
                      <dt>Size</dt>
                      <dd>{zipSizeKb} KB</dd>
                    </div>
                  )}
                  <div>
                    <dt>Uploaded</dt>
                    <dd>{scannedOn}</dd>
                  </div>
                  <div>
                    <dt>Repository</dt>
                    <dd>N/A — uploaded artifact</dd>
                  </div>
                  <div>
                    <dt>Scan ID</dt>
                    <dd>{scanIdLabel}</dd>
                  </div>
                </dl>
                <a className="pkg-gh" href="/methodology">
                  How scoring works →
                </a>
              </div>
            </aside>
          </div>
        </div>
      </section>

      {/* Share/badge band — the SAME DS component the repo report uses, here
            keyed on the active file (per-file slug + score). */}
      <ShareResultBand
        unlisted={unlisted}
        scanId={run.id}
        score={score}
        tier={scored}
        slug={cap.catalog_slug}
        sub={shareSub}
        foot={shareFoot}
        scanIdShort={scanIdLabel}
      />
    </>
  )

  return (
    <>
      {multi ? (
        <>
          <FileTabStrip
            caps={caps}
            active={active}
            onSelect={selectFile}
            panelId={PANEL_ID}
            tabIdBase={TAB_ID_BASE}
          />
          <div id={PANEL_ID} role="tabpanel" aria-labelledby={`${TAB_ID_BASE}-${active}`}>
            {body}
          </div>
        </>
      ) : (
        body
      )}
    </>
  )
}
