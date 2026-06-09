import type { ReactNode } from 'react'

import CopyIconButton from '../atoms/CopyIconButton'
import FrameworkBadges, { type FrameworkRef } from '../atoms/FrameworkBadges'
import SeverityPill, { type Severity } from '../atoms/SeverityPill'
import { revealInvisible } from '../../lib/reveal-invisible'

export type FindingSeverity = Severity

/** One line of the matched-line window (mirrors the report `evidence_excerpt`). */
export interface EvidenceLine {
  lineNo: number
  text: string
  hit: boolean
}

export interface EvidenceExcerpt {
  file: string
  lang?: string | null
  truncated?: boolean
  lines: EvidenceLine[]
}

export interface FindingOccurrence {
  line: number
  file: string
  /** Best-effort column; omitted when not derivable (our findings have none). */
  col?: number | null
}

export interface FindingSaferPattern {
  before: string
  after: string
}

/** Resolved framework-reference badge — re-exported from the shared atom so the
 *  rendering (family-label maps + markup) lives in exactly one place. */
export type FindingFrameworkRef = FrameworkRef

/** Closed set of placeholder values interpolated into the explanation/steps. */
export interface FindingPlaceholders {
  match?: string
  path?: string
  line?: string | number
  count?: number
}

export interface FindingDetailProps {
  ruleId: string
  severity: FindingSeverity
  /** Plain-English headline (no rule_id). */
  title: string
  /** Human category label for the `.fc-rule` meta line. */
  categoryLabel: string
  /** Primary file the finding lives in (meta line + excerpt header). */
  file: string
  /** Optional severity→outcome clause (the `.fc-rationale`); omitted for info. */
  severityRationale?: string
  /** 'Why it matters' template; may carry `<code>` + {match}/{path}/{line}/{count}. */
  explanation: string
  /** Values filled into the explanation/steps placeholders (graceful if empty). */
  placeholders?: FindingPlaceholders
  /** Matched-line window from the stored snapshot, or null when bytes are absent. */
  evidence?: EvidenceExcerpt | null
  /** De-duplicated occurrences of this (rule, file) group. */
  occurrences: FindingOccurrence[]
  remediation: { action: string; steps?: string[]; saferPattern?: FindingSaferPattern }
  /** Optional resolved framework-reference badges (OWASP LLM / MITRE ATLAS / CWE). */
  frameworks?: FindingFrameworkRef[]
  /** matched_content_sha256 of the representative occurrence (trace footer copy). */
  sha?: string | null
  /** Permalink to the rule in the methodology (finding.remediation_link). */
  methodologyHref?: string
  /** GitHub blob link for the primary occurrence (omitted for uploads). */
  githubHref?: string | null
  /** Trace label for the active rubric, e.g. `rubric a1b2c3d` or `rubric · dev`. */
  rubricLabel?: string
  /** Expand on first render (the report opens its first card). */
  defaultOpen?: boolean
  /** Fired whenever the card is expanded (telemetry hook — wired in the webapp). */
  onExpand?: () => void
}

const PH_KEYS = new Set(['match', 'path', 'line', 'count'])
const TOKEN_RE = /<code>([\s\S]*?)<\/code>|\{(match|path|line|count)\}/g
const MAX_LINE_DISPLAY = 92 // chars shown before eliding (the v3 `.ex` budget)

/**
 * Render a TRUSTED template (rubric prose) into React nodes, interpolating the
 * closed placeholder set. The only markup recognised is our own `<code>…</code>`;
 * everything else — including placeholder values, which may be verbatim scanned
 * bytes — is emitted as escaped React text. No innerHTML, so nothing can inject.
 */
function renderTemplate(
  tpl: string,
  placeholders: FindingPlaceholders,
  keyPrefix: string
): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  let i = 0
  TOKEN_RE.lastIndex = 0
  let m: RegExpExecArray | null = TOKEN_RE.exec(tpl)
  while (m !== null) {
    if (m.index > last) nodes.push(tpl.slice(last, m.index))
    if (m[1] !== undefined) {
      nodes.push(<code key={`${keyPrefix}-c${i}`}>{m[1]}</code>)
    } else if (m[2] && PH_KEYS.has(m[2])) {
      const raw = placeholders[m[2] as keyof FindingPlaceholders]
      const val = raw === undefined || raw === null ? '' : String(raw)
      if (val.length > 0) {
        nodes.push(
          <code className="ph" key={`${keyPrefix}-p${i}`}>
            {val}
          </code>
        )
      }
    }
    last = TOKEN_RE.lastIndex
    i += 1
    m = TOKEN_RE.exec(tpl)
  }
  if (last < tpl.length) nodes.push(tpl.slice(last))
  return nodes
}

function Segments({ text }: { text: string }) {
  return (
    <>
      {revealInvisible(text).map((seg, idx) =>
        seg.kind === 'text' ? (
          // biome-ignore lint/suspicious/noArrayIndexKey: stable order, immutable text
          <span key={idx}>{seg.text}</span>
        ) : (
          <span
            // biome-ignore lint/suspicious/noArrayIndexKey: stable order, immutable text
            key={idx}
            className={`ic ${seg.cls}`}
            title={
              seg.cls === 'homo'
                ? `homoglyph ${seg.codepoint} — looks like an ASCII letter`
                : `invisible character ${seg.codepoint}`
            }
          >
            {seg.glyph ? `${seg.glyph} ${seg.codepoint}` : seg.codepoint}
          </span>
        )
      )}
    </>
  )
}

function ExcerptBlock({ evidence }: { evidence: EvidenceExcerpt }) {
  return (
    <div className="ex">
      <div className="ex-meta">
        <span>excerpt</span>
        <span className="ex-file">{evidence.file}</span>
        {evidence.lang ? <span>· {evidence.lang}</span> : null}
      </div>
      {evidence.lines.map((line) => {
        const elided = line.text.length > MAX_LINE_DISPLAY ? line.text.length - MAX_LINE_DISPLAY : 0
        const shown = elided > 0 ? line.text.slice(0, MAX_LINE_DISPLAY) : line.text
        return (
          <div key={line.lineNo}>
            <div className={`ex-line${line.hit ? ' hit' : ''}`}>
              <span className="ln">{line.lineNo}</span>
              <span className="code">{shown.length ? <Segments text={shown} /> : ' '}</span>
            </div>
            {elided > 0 ? (
              <div className="ex-elide">
                … ({elided} chars elided on L{line.lineNo})
              </div>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function occurrenceLine(occs: FindingOccurrence[]): ReactNode {
  const lines = occs.map((o) => o.line)
  if (occs.length === 1) {
    return (
      <span className="fc-occ-line">
        <b>1 occurrence</b> · at <span className="lref">L{lines[0]}</span>
      </span>
    )
  }
  const rest = lines.slice(1)
  const shown = rest.slice(0, 2)
  return (
    <span className="fc-occ-line">
      <b>{occs.length} occurrences</b> · first at <span className="lref">L{lines[0]}</span>
      {shown.length > 0 ? <>, also {shown.map((l, i) => <span key={l}>{i > 0 ? ', ' : ''}<span className="lref">L{l}</span></span>)}</> : null}
      {rest.length > 2 ? ` +${rest.length - 2} more` : null}
    </span>
  )
}

const Chevron = () => (
  <svg className="fc-chev" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
    <path d="M4 6l4 4 4-4" />
  </svg>
)

const SmallChevron = () => (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
    <path d="M4 6l4 4 4-4" />
  </svg>
)

/**
 * The v3 `.find-card` — one expandable finding, shared by every scan surface
 * (repo scan cap-bodies + the upload/item checklist). Collapsed summary
 * (severity pill · title · rule meta · occurrence count) expands to: severity
 * rationale → why-it-matters → the exact-value excerpt (line gutter, hit line,
 * revealed invisibles) → occurrences → how-to-fix (action · steps · Avoid→Safer)
 * → a collapsed trace footer (rule link · sha256 copy · rubric · GitHub).
 *
 * Fully presentational: every prop is already resolved by the caller (the webapp
 * composes from the generated `RULE_CONTENT` map + the backend evidence). The
 * `ui/` layer never imports that map. Uses native `<details>` for the
 * collapse (chevron rotation is the only motion — reduced-motion guarded in CSS).
 */
export default function FindingDetail({
  ruleId,
  severity,
  title,
  categoryLabel,
  file,
  severityRationale,
  explanation,
  placeholders = {},
  evidence,
  occurrences,
  remediation,
  frameworks,
  sha,
  methodologyHref,
  githubHref,
  rubricLabel,
  defaultOpen = false,
  onExpand,
}: FindingDetailProps) {
  const sevLabel = severity.toUpperCase()
  const count = occurrences.length

  return (
    <details
      className="find-card"
      open={defaultOpen}
      onToggle={(e) => {
        if ((e.currentTarget as HTMLDetailsElement).open) onExpand?.()
      }}
    >
      <summary>
        <SeverityPill severity={severity} label={sevLabel} />
        <span className="fc-titlewrap">
          <span className="fc-title">{title}</span>
          <span className="fc-rule">
            {ruleId} · {categoryLabel} · {file}
          </span>
        </span>
        <span className="fc-right">
          {count > 1 ? <span className="fc-count">×{count}</span> : null}
          <Chevron />
        </span>
      </summary>

      <div className="fc-detail">
        {severityRationale ? (
          <div className={`fc-rationale ${severity}`}>
            <b>{sevLabel}</b> — {severityRationale}
          </div>
        ) : null}

        <div className="fc-why">
          <div className="fc-lbl">Why it matters</div>
          <p>{renderTemplate(explanation, placeholders, 'why')}</p>
        </div>

        {evidence && evidence.lines.length > 0 ? (
          <div className="fc-evidence">
            <div className="fc-lbl">The exact value spotted</div>
            <ExcerptBlock evidence={evidence} />
          </div>
        ) : (
          <div className="fc-evidence">
            <div className="fc-lbl">The exact value spotted</div>
            <p className="fc-novalue">
              The matching bytes aren't stored for this scan (binary, oversize, or an
              expired snapshot). See the location below.
            </p>
          </div>
        )}

        <div className="fc-occ">
          <div className="fc-lbl">Occurrences</div>
          {occurrenceLine(occurrences)}
          {occurrences.length > 1 ? (
            <details className="fc-occ-more">
              <summary>Show all {occurrences.length} locations</summary>
              <div className="fc-occ-grid no-col">
                <div className="oc head">Line</div>
                <div className="oc head">File</div>
                {occurrences.map((o, i) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: occurrences are positional + immutable
                  <span key={i} style={{ display: 'contents' }}>
                    <div className="oc ln">L{o.line}</div>
                    <div className="oc">{o.file}</div>
                  </span>
                ))}
              </div>
            </details>
          ) : null}
        </div>

        <div className="fc-fix">
          <div className="fc-lbl">How to fix</div>
          <div className="fc-action">{renderTemplate(remediation.action, placeholders, 'act')}</div>
          {remediation.steps && remediation.steps.length > 0 ? (
            <ol>
              {remediation.steps.map((step, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: steps are an ordered immutable list
                <li key={i}>{renderTemplate(step, placeholders, `step${i}`)}</li>
              ))}
            </ol>
          ) : null}
          {remediation.saferPattern ? (
            <div className="fc-safer">
              <div className="sp before">
                <span className="sp-tag">
                  <span className="mk" aria-hidden="true" />
                  Avoid
                </span>
                <code className="sp-code">{remediation.saferPattern.before}</code>
              </div>
              <div className="sp after">
                <span className="sp-tag">
                  <span className="mk" aria-hidden="true" />
                  Safer pattern
                </span>
                <code className="sp-code">{remediation.saferPattern.after}</code>
              </div>
            </div>
          ) : null}
        </div>

        {frameworks && frameworks.length > 0 ? (
          <div className="fc-frameworks">
            <div className="fc-lbl">Framework references</div>
            <FrameworkBadges frameworks={frameworks} />
          </div>
        ) : null}

        <details className="fc-trace">
          <summary>
            Trace &amp; refs
            <SmallChevron />
          </summary>
          <div className="fc-trace-body">
            {methodologyHref ? (
              <a className="tr" href={methodologyHref} target="_blank" rel="noreferrer noopener">
                <span className="k">rule</span>
                <span className="v">{ruleId}</span>
              </a>
            ) : (
              <span className="tr">
                <span className="k">rule</span>
                <span className="v">{ruleId}</span>
              </span>
            )}
            {sha ? (
              <span className="tr">
                <span className="k">sha256</span>
                <span className="v sha" title={`sha256:${sha}`}>
                  {sha.slice(0, 16)}…
                </span>
                <CopyIconButton value={`sha256:${sha}`} label="Copy SHA-256" />
              </span>
            ) : null}
            {rubricLabel ? (
              <span className="tr">
                <span className="k">{rubricLabel}</span>
              </span>
            ) : null}
            {githubHref ? (
              <a className="tr" href={githubHref} target="_blank" rel="noreferrer noopener">
                <span className="v">View on GitHub</span>
              </a>
            ) : null}
          </div>
        </details>
      </div>
    </details>
  )
}
