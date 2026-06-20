import { getCollection } from 'astro:content'

import { type DocsEntry, idToSlug } from '@/lib/docs/nav'

/**
 * The webapp-owned `static` sitemap shard.
 *
 * The backend sitemap enumerates the DB corpus (items / scans / agents) but
 * cannot see the webapp's own prerendered marketing routes or its docs
 * collection. This shard supplies exactly those URLs.
 *
 * EXCLUDED on purpose: `/catalog` (301 → `/capabilities`), the token routes
 * `/scans/r/*` + `/agents/r/*`, and the non-page surfaces `/api/*`, `/og/*`,
 * `/badge/*`, `/404`, `/500`.
 */

/** Canonical origin for absolute `<loc>` URLs (matches `astro.config.mjs` `site`). */
export const SITE_ORIGIN = 'https://saferskills.ai'

/** Hand-maintained prerendered marketing/browse routes.
 * NOTE: `/research/state-of-ai-agent-skill-security` is intentionally absent —
 * that page doesn't exist until plan 03 ships it. Plan 03 re-adds the route here. */
export const STATIC_ROUTES: readonly string[] = [
  '/',
  '/about',
  '/methodology',
  '/privacy',
  '/terms',
  '/cookies',
  '/capabilities',
  '/scan',
  '/agents',
  '/agents/scan',
]

/** Collect every docs route from the `docs` content collection. */
export async function docsRoutes(): Promise<string[]> {
  const entries = await getCollection('docs')
  return entries.map((d: DocsEntry) => {
    const slug = idToSlug(d.id)
    return slug ? `/docs/${slug}/` : '/docs/'
  })
}

/** All static-shard paths (marketing + docs), de-duplicated, in order. */
export async function staticPaths(): Promise<string[]> {
  const docs = await docsRoutes()
  return [...STATIC_ROUTES, ...docs]
}

/** Render the static shard `<urlset>`. No `<lastmod>`: build-time is not a real
 * content-mtime, and a synthetic lastmod makes Google ignore the field (R6). The
 * DB shards carry the meaningful lastmod (`scanned_at`); these static URLs do not. */
export async function renderStaticShard(origin: string = SITE_ORIGIN): Promise<string> {
  const base = origin.replace(/\/+$/, '')
  const paths = await staticPaths()
  const urls = paths.map((p) => `<url><loc>${escapeXml(`${base}${p}`)}</loc></url>`).join('')
  return `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}
