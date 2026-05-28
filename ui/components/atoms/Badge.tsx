import type { ReactNode } from 'react'

type Variant = 'default' | 'live'

/**
 * Hex-cap badge — 28px h, 12px caps, mono uppercase 10px 700.
 * `live` variant adds a pulsing dot + teal background.
 */
export default function Badge({
  children,
  variant = 'default',
  className = '',
}: {
  children: ReactNode
  variant?: Variant
  className?: string
}) {
  const classes = ['badge', variant !== 'default' ? variant : '', className]
    .filter(Boolean).join(' ')
  return (
    <span className={classes}>
      {variant === 'live' && <span className="dot" aria-hidden="true" />}
      {children}
    </span>
  )
}
