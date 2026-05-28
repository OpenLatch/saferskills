import type { GlobalProvider } from '@ladle/react'
import '../styles/globals.css'

/**
 * Ladle global provider — loads the full SaferSkills design-system stylesheet
 * chain (Tailwind v4 + tokens + fonts + page-vocabulary CSS) so every story
 * renders with the same chrome the webapp ships.
 */
export const Provider: GlobalProvider = ({ children }) => <>{children}</>
