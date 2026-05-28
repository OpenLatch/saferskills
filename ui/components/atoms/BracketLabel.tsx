import type { ReactNode } from 'react'

/**
 * `[ FOO ]` bracket-wrapped mono kicker. Brackets injected via `::before`/`::after`
 * so the text content stays clean.
 */
export default function BracketLabel({
  children,
  className = '',
}: { children: ReactNode; className?: string }) {
  return <span className={`bracket-label ${className}`.trim()}>{children}</span>
}
