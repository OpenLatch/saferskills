import type { ReactNode } from 'react'

interface Props {
  /** Sequence number ("01"..."05") rendered as the leading `.n` column. */
  index: string
  /** Verb tag — find / install / verify / monitor / trust — rendered as `.k`. */
  tag: string
  /** Body copy ( supports inline `<b>`/`<span>` for emphasis ). */
  body?: ReactNode
  /** Trusted HTML body (used from Astro templates). Static content only. */
  bodyHtml?: string
  /** Mono right-rail meta lines — usually two stat strings then a link. */
  metaLines?: ReactNode[]
  /** Trusted HTML meta lines (used from Astro templates). Static content only. */
  metaLinesHtml?: string[]
  /** Right-rail link rendered last in the meta column. */
  arrow?: { label: string; href: string }
}

/**
 * "Five reasons it earns the URL" row — Phase A2 vocabulary `.reason-row`.
 *
 * Four-column grid per the docs-band mockup: `.n` (44px seq) / `.k` (120px verb)
 * / `.d` (1fr body) / `.m` (220px right-rail meta). Hover state pushes the row
 * 10px right and tints `.k` + the trailing arrow in brand-primary. Borders are
 * a dashed bottom rule — the parent `.reasons-list` supplies the top hairline
 * of the first row.
 *
 * Per the mockup the row itself is a `<div>` (not a link); only the right-rail
 * `.ml-link` is an `<a>`. This preserves a single accessible link target per
 * row instead of a giant card link.
 */
export default function WhyRow({
  index,
  tag,
  body,
  bodyHtml,
  metaLines = [],
  metaLinesHtml = [],
  arrow,
}: Props) {
  return (
    <div className="reason-row">
      <div className="n">{index}</div>
      <div className="k">
        {tag}
        <span className="arrow" aria-hidden="true">→</span>
      </div>
      {bodyHtml ? (
        <div
          className="d"
          // biome-ignore lint/security/noDangerouslySetInnerHtml: static homepage copy, never user input
          dangerouslySetInnerHTML={{ __html: bodyHtml }}
        />
      ) : (
        <div className="d">{body}</div>
      )}
      <div className="m">
        {metaLinesHtml.length > 0
          ? metaLinesHtml.map((line, i) => (
              <span
                key={i}
                className="stat"
                // biome-ignore lint/security/noDangerouslySetInnerHtml: static homepage copy, never user input
                dangerouslySetInnerHTML={{ __html: line }}
              />
            ))
          : metaLines.map((line, i) => (
              <span key={i} className="stat">{line}</span>
            ))}
        {arrow && (
          <a className="ml-link" href={arrow.href}>
            {arrow.label} <span aria-hidden="true">→</span>
          </a>
        )}
      </div>
    </div>
  )
}
