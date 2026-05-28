import type { ReactNode } from 'react'

interface Foot {
  cta: { label: string; href: string }
  /** Render-tree meta — preferred when called from React. */
  meta?: ReactNode
  /** Trusted HTML meta — preferred when called from Astro templates that
   *  can't construct ReactNode children inline due to JSX-shorthand parsing
   *  limits. Static content only; never plumb user input through this. */
  metaHtml?: string
}

interface Props {
  /** Sequence index ("01" / "02") rendered as the head pill. */
  index: string
  /** Short label after the sequence pill — "Find" / "Audit" / "Verify". */
  kicker: string
  /** Optional pulsing live indicator on the right of the head bar. */
  liveLabel?: string
  title: string
  lede: string
  /** Slot that holds the rich input + action affordances (search/scan/etc.). */
  children: ReactNode
  /** Optional foot with a CTA + meta line. */
  foot?: Foot
  /** Tints the pulse + focus accents. */
  variant?: 'find' | 'audit'
}

/**
 * Numbered hero action card (FIND / AUDIT pattern from the homepage hi-fi).
 *
 * Three regions per the mockup `.p1-card`:
 *   - `.p1-head`  : slim ink machine-bar with `.seq` (01/02) + kicker + `.pulse`
 *   - `.p1-body`  : title + blurb + slot for the rich input + chips/progress
 *   - `.p1-foot`  : CTA link + meta strip (kept inside the card border)
 *
 * The variant decides the pulse animation: find = green (`p1-pulse`),
 * audit = yellow (`p1-pulse-y`). Both keyframes ship in page-home.css.
 */
export default function ActionCard({
  index,
  kicker,
  liveLabel,
  title,
  lede,
  children,
  foot,
  variant,
}: Props) {
  return (
    <div className={`p1-card ${variant ?? ''}`.trim()}>
      <div className="p1-head">
        <span className="seq">{index}</span>
        <span>{kicker}</span>
        {liveLabel && <span className="pulse">{liveLabel}</span>}
      </div>
      <div className="p1-body">
        <div>
          <h3 className="p1-title">{title}</h3>
          <p className="p1-blurb">{lede}</p>
        </div>
        {children}
      </div>
      {foot && (
        <div className="p1-foot">
          <a className="p1-cta" href={foot.cta.href}>{foot.cta.label}</a>
          {foot.metaHtml ? (
            <span
              className="meta"
              // biome-ignore lint/security/noDangerouslySetInnerHtml: static homepage copy, never user input
              dangerouslySetInnerHTML={{ __html: foot.metaHtml }}
            />
          ) : foot.meta ? (
            <span className="meta">{foot.meta}</span>
          ) : null}
        </div>
      )}
    </div>
  )
}
