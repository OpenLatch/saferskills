import type { ElementType, ReactNode } from 'react'

interface Props {
  /** Sequence number ("01"..."05") rendered as the leading `.n` column. */
  index: string
  /** Verb tag — find / install / audit / scan / trust — rendered as `.k`. */
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
  /**
   * Multi-destination rows (e.g. privacy + methodology): each entry
   * renders as a REAL `.ml-link` anchor in the meta column and the row root
   * stays a `<div>` (anchors can't nest). Takes precedence over `arrow`.
   */
  links?: { label: string; href: string }[]
}

/**
 * "Five reasons it earns the URL" row — `.reason-row` vocabulary.
 *
 * Four-column grid per the docs-band mockup: `.n` (44px seq) / `.k` (120px verb)
 * / `.d` (1fr body) / `.m` (220px right-rail meta). Hover state pushes the row
 * 10px right and tints `.k` + the trailing arrow in brand-primary. Borders are
 * a dashed bottom rule — the parent `.reasons-list` supplies the top hairline
 * of the first row.
 *
 * The whole row is a single link to the reason's destination (`arrow.href`);
 * the right-rail label is a visual `.ml-link` cue (a `<span>`, not a nested
 * anchor) so the row stays one accessible link target. A row with several
 * destinations passes `links` instead — the root becomes a `<div>` and each
 * entry renders as a real anchor. When neither is given the row degrades to
 * a plain `<div>`.
 */
export default function WhyRow({
  index,
  tag,
  body,
  bodyHtml,
  metaLines = [],
  metaLinesHtml = [],
  arrow,
  links,
}: Props) {
  const multi = (links?.length ?? 0) > 0
  const href = multi ? undefined : arrow?.href
  // Whole-row link when a single destination exists; otherwise a plain div.
  const Root: ElementType = href ? 'a' : 'div'
  return (
    <Root className="reason-row" {...(href ? { href } : {})}>
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
        {multi
          ? links?.map((link) => (
              <a key={link.href} className="ml-link" href={link.href}>
                {link.label} <span aria-hidden="true">→</span>
              </a>
            ))
          : arrow && (
              <span className="ml-link">
                {arrow.label} <span aria-hidden="true">→</span>
              </span>
            )}
      </div>
    </Root>
  )
}
