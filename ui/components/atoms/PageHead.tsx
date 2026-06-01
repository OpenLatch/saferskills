import type { ReactNode } from 'react'
import Breadcrumb, { type Crumb } from './Breadcrumb'

interface Props {
  /** Optional — omit when a breadcrumb already carries the page path. */
  eyebrow?: string
  title: ReactNode
  lede?: ReactNode
  className?: string
  /**
   * Optional breadcrumb trail rendered above the eyebrow. Pass plain data (not a
   * rendered element) so the Astro→React boundary can serialize it; PageHead
   * renders the shared `<Breadcrumb>` itself.
   */
  breadcrumbItems?: Crumb[]
}

/**
 * Signature page-head strip — eyebrow + giant title + optional lede. Topped
 * with the 12px tick-ruler accent + 40×40 plus-grid background pattern
 * (handled in components.css::.page-head).
 *
 * On every non-homepage page a `<PageRidge>` is placed directly below this
 * strip — it provides the header→body transition (replacing the old flat
 * border) and carries the page-path cue in its centered label.
 *
 * Title supports inline `<mark>` (teal-tint underline) + `<span className="script">`
 * (orange Nanum Pen Script accent). Pass via `title` as ReactNode for those.
 */
export default function PageHead({
  eyebrow,
  title,
  lede,
  className = '',
  breadcrumbItems,
}: Props) {
  return (
    <section className={`page-head ${className}`.trim()}>
      <div className="container">
        {breadcrumbItems && <Breadcrumb items={breadcrumbItems} />}
        {eyebrow && <div className="ph-eyebrow">{eyebrow}</div>}
        <h1 className="ph-title">{title}</h1>
        {lede && <p className="ph-lede">{lede}</p>}
      </div>
    </section>
  )
}
