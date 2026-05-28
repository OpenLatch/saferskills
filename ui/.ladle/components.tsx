import type { GlobalProvider } from '@ladle/react'
import { useEffect } from 'react'
import '../styles/globals.css'

/**
 * Ladle global provider.
 *
 * Two jobs:
 *   1. Load the full SaferSkills design-system stylesheet chain (Tailwind v4 +
 *      tokens + fonts + page-vocabulary CSS) so stories render with the same
 *      chrome the webapp ships.
 *   2. Mirror Ladle's built-in theme toolbar onto `<html class="dark">` —
 *      same signal the production webapp uses (D-FE-08). Tokens.css declares
 *      `@custom-variant dark (&:where(.dark, .dark *));` and an `html.dark`
 *      override block, so flipping the class is enough to swap every
 *      `--fg-*` / `--bg-*` / `--brand-*` token to its dark-mode value.
 */
export const Provider: GlobalProvider = ({ children, globalState }) => {
  useEffect(() => {
    document.documentElement.classList.toggle('dark', globalState.theme === 'dark')
  }, [globalState.theme])

  return <>{children}</>
}
