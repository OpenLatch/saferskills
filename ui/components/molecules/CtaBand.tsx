import { Fragment, type ReactNode } from 'react'

interface Action {
  label: string
  href: string
}

interface Props {
  title: ReactNode
  titleLines?: string[]
  lead?: ReactNode
  primaryAction: Action
  secondaryAction?: Action
}

/**
 * Dark-slate CTA band. Pass `titleLines` for an explicit hard-wrapped title
 * (preferred for hero CTA copy that must always break the same way) or
 * `title` for a single ReactNode.
 */
export default function CtaBand({
  title,
  titleLines,
  lead,
  primaryAction,
  secondaryAction,
}: Props) {
  return (
    <section className="cta-band">
      <div className="container">
        <div className="cta-row">
          <div>
            <h2>
              {titleLines
                ? titleLines.map((line, i) => (
                    <Fragment key={i}>
                      {line}
                      {i < titleLines.length - 1 ? <br /> : null}
                    </Fragment>
                  ))
                : title}
            </h2>
            {lead && <p className="lead">{lead}</p>}
          </div>
          <div className="cta-actions btn-pair">
            <a href={primaryAction.href} className="btn primary lg">
              {primaryAction.label}
            </a>
            {secondaryAction && (
              <a href={secondaryAction.href} className="btn paper lg">
                {secondaryAction.label}
              </a>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
