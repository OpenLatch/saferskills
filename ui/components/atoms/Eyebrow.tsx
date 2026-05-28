import type { ReactNode } from 'react'

/**
 * Mono-uppercase prefix line above section titles. Optional 24px hairline rule.
 */
export default function Eyebrow({
  children,
  withRule = true,
  className = '',
}: {
  children: ReactNode
  withRule?: boolean
  className?: string
}) {
  const classes = ['eyebrow', withRule ? '' : 'no-rule', className]
    .filter(Boolean).join(' ')
  return <span className={classes}>{children}</span>
}
