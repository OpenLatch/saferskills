import type { ReactNode } from 'react'

/**
 * Portable keyboard-chip atom — hairline border + mono caps.
 * Callers control the content (e.g. "⌘K" on Mac, "Ctrl+K" on Windows).
 */
export default function Kbd({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  const classes = ['kbd-chip', className].filter(Boolean).join(' ')
  return <kbd className={classes}>{children}</kbd>
}
