import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

// L-7 / D-07-08. `500.astro` is the branded SSR error page Astro's Node adapter
// renders on any uncaught render error. The CRITICAL invariant: it must fetch
// NOTHING (a 500 happens exactly when the backend is unreachable, so any live
// fetch would re-fail). `.astro` files can't be unit-rendered in vitest, so we
// assert on the page source as text — the same convention the repo uses for
// static-structure guards. We assert:
//   - NO API fetch (no getHomepageData / fetch / getCollection import or call);
//   - prerender = true (fully static);
//   - Base noindex (an error page must never be indexed);
//   - Base noStats (suppresses the site-wide NavStars live-fetch island);
//   - a "Check status" link to status.saferskills.ai.
// vitest runs with cwd = the webapp package root; resolve the page source from
// there (jsdom's `import.meta.url` is not a usable file: URL for readFileSync).
const SOURCE = readFileSync(resolve(process.cwd(), 'src/pages/500.astro'), 'utf8')
const BASE = readFileSync(resolve(process.cwd(), 'src/layouts/Base.astro'), 'utf8')

describe('500.astro branded error page', () => {
  it('is fully static — never fetches the API or any live data', () => {
    // The 404 page imports getHomepageData (fine for a 404); the 500 must NOT —
    // it renders when the API may be down.
    expect(SOURCE).not.toContain('getHomepageData')
    expect(SOURCE).not.toContain('getCollection')
    // No bare fetch( and no top-level await of any data call in the frontmatter.
    expect(SOURCE).not.toMatch(/\bfetch\s*\(/)
    expect(SOURCE).not.toMatch(/\bawait\b/)
  })

  it('is prerendered (static, no SSR data dependency)', () => {
    expect(SOURCE).toMatch(/export const prerender = true/)
  })

  it('is noindex — an error page must never be indexed', () => {
    expect(SOURCE).toMatch(/<Base[^>]*\bnoindex=\{true\}/s)
  })

  // The site-wide NavStars island (mounted in Base) fetches the GitHub-star count
  // in the browser. On a 500 the backend may be down, so the page suppresses it
  // via `noStats` — otherwise a doomed live fetch fires, violating the page's
  // "depends on no live data" invariant.
  it('suppresses the live-data NavStars island (Base noStats)', () => {
    // The 500 page opts in.
    expect(SOURCE).toMatch(/<Base[^>]*\bnoStats=\{true\}/s)
    // Base actually gates the NavStars mount on the prop (not just accepts it).
    expect(BASE).toMatch(/\{!noStats &&\s*<NavStars/)
  })

  it('has a "Check status" link to the public status page', () => {
    expect(SOURCE).toContain('https://status.saferskills.ai')
    expect(SOURCE).toContain('Check status')
  })

  it('has a "Back to home" action', () => {
    expect(SOURCE).toMatch(/href="\/"/)
    expect(SOURCE).toContain('Back to home')
  })
})
