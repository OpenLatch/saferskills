import type { ReactNode } from 'react'

type Variant = 'default' | 'g' | 'y' | 'o' | 'r'

/**
 * Small hex-cap chip — 24px h, 10px caps. Mono font 11px.
 * Used for filter tags + scan-tier labels.
 */
export default function Chip({
  children,
  variant = 'default',
  className = '',
}: {
  children: ReactNode
  variant?: Variant
  className?: string
}) {
  const classes = ['chip', variant !== 'default' ? variant : '', className]
    .filter(Boolean).join(' ')
  return <span className={classes}>{children}</span>
}
