import type { ReactNode } from 'react'

/**
 * Pair of adjacent hex buttons. The second `.btn` child receives the
 * `mask-hex-notch-left` cap so the silhouettes lock together.
 *
 * The notch styling lives in `components.css::.btn-pair > * + .btn`.
 * Mobile (<640px) reverts both buttons to normal caps + 12px gap.
 */
export default function ButtonPair({
  children,
  className = '',
}: { children: ReactNode; className?: string }) {
  return <div className={`btn-pair ${className}`.trim()}>{children}</div>
}
