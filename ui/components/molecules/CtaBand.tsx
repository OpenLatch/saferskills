import type { ReactNode } from 'react'

interface Action {
  label: string
  href: string
}

interface Props {
  title: ReactNode
  lead?: ReactNode
  primaryAction: Action
  secondaryAction?: Action
}

/**
 * Dark-slate CTA band (96px y-padding, diag-hatching texture, orange tick-ruler
 * top edge). Lives below content + above footer on most A2/B/C pages.
 */
export default function CtaBand({
  title,
  lead,
  primaryAction,
  secondaryAction,
}: Props) {
  return (
    <section className="cta-band">
      <div className="container">
        <div className="cta-row">
          <div>
            <h2>{title}</h2>
            {lead && <p className="lead">{lead}</p>}
          </div>
          <div style={{ display: 'inline-flex', gap: 12, flexWrap: 'wrap' }}>
            <a href={primaryAction.href} className="btn primary">
              {primaryAction.label}
            </a>
            {secondaryAction && (
              <a href={secondaryAction.href} className="btn paper">
                {secondaryAction.label}
              </a>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
