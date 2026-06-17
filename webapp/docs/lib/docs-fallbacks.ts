/**
 * Docs-build fallback constants.
 *
 * Re-exported from the canonical webapp source (`@/data/launch-fallbacks`) so
 * the value can never drift from the main site. The `@/*` alias resolves in the
 * docs build too — both Astro configs share `webapp/tsconfig.json`'s path map.
 *
 * The docs Header renders this as the NavBar GhStar *SSR placeholder* (so the
 * chip is never empty before hydration); the `NavStars` island then patches the
 * live repo star count on the client, exactly as on the main site.
 */
export { FALLBACK_GITHUB_STARS } from '@/data/launch-fallbacks'
