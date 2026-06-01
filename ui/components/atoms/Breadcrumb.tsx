import { Fragment, type ReactNode } from 'react'

export interface Crumb {
  label: ReactNode
  /** Omit on the final (current-page) crumb. */
  href?: string
}

/**
 * Mono-uppercase breadcrumb trail — the first crumb carries a `←` back-arrow,
 * the last renders as the current page (`aria-current`). Renders to static HTML
 * (no hydration needed). CSS: `ui/styles/components.css::.breadcrumb`. Shared by
 * the item-detail head and the vendor-respond PageHead (one level deeper).
 */
export default function Breadcrumb({
  items,
  className = '',
}: {
  items: Crumb[]
  className?: string
}) {
  return (
    <nav className={`breadcrumb ${className}`.trim()} aria-label="Breadcrumb">
      {items.map((c, i) => {
        const isLast = i === items.length - 1
        return (
          <Fragment key={c.href ?? `cur-${i}`}>
            {i > 0 && (
              <span className="sep" aria-hidden="true">
                /
              </span>
            )}
            {c.href && !isLast ? (
              <a href={c.href}>
                {i === 0 && (
                  <span className="bc-arrow" aria-hidden="true">
                    ←
                  </span>
                )}
                {c.label}
              </a>
            ) : (
              <span className="cur" aria-current="page">
                {c.label}
              </span>
            )}
          </Fragment>
        )
      })}
    </nav>
  )
}
