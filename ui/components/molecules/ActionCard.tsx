import type { ReactNode } from 'react'

interface Props {
  index: '01' | '02'
  kicker: string
  liveLabel?: string
  title: string
  lede: string
  children: ReactNode
}

/**
 * Numbered hero action card (FIND / AUDIT pattern from homepage).
 *
 * Dark slate top-bar with index + kicker on the left, optional pulsing
 * live-label on the right. Body holds title + lede + the provided children
 * (the action surface — search input, scan input, etc.).
 */
export default function ActionCard({
  index,
  kicker,
  liveLabel,
  title,
  lede,
  children,
}: Props) {
  return (
    <div className="action-card">
      <div className="ac-bar">
        <span className="ac-index">{index}</span>
        <span className="ac-kicker">{kicker}</span>
        {liveLabel && (
          <span className="ac-live">
            <span className="dot" aria-hidden="true" />
            {liveLabel}
          </span>
        )}
      </div>
      <div className="ac-body">
        <h3 className="ac-title">{title}</h3>
        <p className="ac-lede">{lede}</p>
        <div className="ac-action">{children}</div>
      </div>
    </div>
  )
}
