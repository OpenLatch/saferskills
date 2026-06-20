/**
 * Pure JSON-LD builders (Schema.org structured data) for the SSR surfaces.
 *
 * SEO-T4 / D-07-05. These are plain-object builders called from Astro
 * frontmatter at render time and serialized by `components/seo/JsonLd.astro`
 * (which XSS-escapes the output). They emit ONLY the schema types the launch
 * decision ratified:
 *
 *   Organization          — site-wide (Base.astro)
 *   SoftwareApplication   — the SaferSkills scanner itself (homepage)
 *   SoftwareApplication / SoftwareSourceCode — a scanned catalog item
 *   BreadcrumbList        — pages with a VISIBLE breadcrumb trail (item page)
 *   Dataset               — the open scan-data corpus (consumed by plan 03's /research)
 *
 * **D-07-05 — NO fabricated AggregateRating / Review.** The 0-100 scan score is
 * an algorithmic audit, not user reviews; Google issues structured-data manual
 * actions for `AggregateRating`/`Review` not backed by genuine user reviews. The
 * score lives in the page's VISIBLE HTML (where AI engines read it anyway), never
 * as a schema rating. `capabilityAppJsonLd` deliberately carries no rating key —
 * `jsonld.test.ts` is the regression guard.
 *
 * The `schema-dts` types make a malformed object fail `tsc --noEmit` (typecheck-fe).
 */
import type {
  BreadcrumbList,
  Dataset,
  Organization,
  SoftwareApplication,
  SoftwareSourceCode,
  Thing,
  WithContext,
} from 'schema-dts'

const ORIGIN = 'https://saferskills.ai'
const CONTEXT = 'https://schema.org' as const

const LS = String.fromCharCode(0x2028) // U+2028 LINE SEPARATOR
const PS = String.fromCharCode(0x2029) // U+2029 PARAGRAPH SEPARATOR

/**
 * XSS-safe serialization of a builder's output (or an array of them → `@graph`)
 * into the string body of a `<script type="application/ld+json">`. The `@context`
 * is injected here so the builders stay typed by bare `schema-dts` Things.
 *
 * `JSON.stringify` does NOT escape `</script>`, and a scanned repo's name / author
 * / slug is attacker-controlled (anonymous submissions flow into
 * `capabilityAppJsonLd`/`breadcrumbJsonLd`). An un-escaped `</script>` would break
 * out of the script element; a raw U+2028 / U+2029 is invalid inside a JS string.
 * We escape all three. Consumed by `components/seo/JsonLd.astro`; pure + tested.
 */
export function serializeJsonLd(schema: Thing | Thing[]): string {
  const payload: WithContext<Thing> | { '@context': typeof CONTEXT; '@graph': Thing[] } =
    Array.isArray(schema)
      ? { '@context': CONTEXT, '@graph': schema }
      : ({ '@context': CONTEXT, ...(schema as object) } as WithContext<Thing>)
  return JSON.stringify(payload)
    .replace(/</g, '\\u003c')
    .replaceAll(LS, '\\u2028')
    .replaceAll(PS, '\\u2029')
}

/** Site-wide publisher identity. Rendered once in `Base.astro`. */
export const organizationJsonLd = (): Organization => ({
  '@type': 'Organization',
  name: 'SaferSkills',
  url: ORIGIN,
  logo: `${ORIGIN}/og-image.png`,
  description: 'Every AI capability, independently audited.',
  sameAs: ['https://github.com/openlatch/saferskills'],
})

/**
 * The SaferSkills scanner itself — a free, cross-platform security application.
 * Emit on the HOMEPAGE only (it describes the site-wide product, not a per-page entity).
 */
export const scannerAppJsonLd = (): SoftwareApplication => ({
  '@type': 'SoftwareApplication',
  name: 'SaferSkills',
  applicationCategory: 'SecurityApplication',
  operatingSystem: 'macOS, Windows, Linux',
  url: ORIGIN,
  description:
    'Public, open-source trust scoring for skills, MCP servers, hooks, plugins, and rules across every agent platform.',
  // Free + open source.
  offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
})

export interface CapabilityAppInput {
  slug: string
  name: string
  kind: string
  repoUrl?: string
}

/**
 * A scanned catalog capability (item page). An MCP server is a runnable
 * application (`SoftwareApplication`); everything else is source code
 * (`SoftwareSourceCode`). **NO AggregateRating / Review (D-07-05)** — the score
 * lives in the page's visible HTML, never as a schema rating.
 */
export const capabilityAppJsonLd = (
  item: CapabilityAppInput
): SoftwareApplication | SoftwareSourceCode => ({
  '@type': item.kind === 'mcp_server' ? 'SoftwareApplication' : 'SoftwareSourceCode',
  name: item.name,
  url: `${ORIGIN}/items/${item.slug}`,
  applicationCategory: 'DeveloperApplication',
  ...(item.repoUrl ? { codeRepository: item.repoUrl } : {}),
  // The 0-100 audit score is deliberately NOT a schema rating — see D-07-05.
})

export interface Crumb {
  name: string
  path: string
}

/**
 * A breadcrumb trail. Build it from the SAME crumb array the visible
 * `<Breadcrumb>` atom renders (adapt `{label, href}` → `{name, path}` and give
 * the trailing current-page crumb its own path). Only emit on pages that render
 * a visible breadcrumb — fabricating a trail with no visible counterpart is
 * dishonest structured data.
 */
export const breadcrumbJsonLd = (crumbs: Crumb[]): BreadcrumbList => ({
  '@type': 'BreadcrumbList',
  itemListElement: crumbs.map((c, i) => ({
    '@type': 'ListItem',
    position: i + 1,
    name: c.name,
    item: `${ORIGIN}${c.path}`,
  })),
})

export interface DatasetInput {
  name: string
  description: string
  url: string
}

/**
 * The open scan-data corpus / State-of report. Exported for plan 03's
 * `/research` page (not rendered by any plan-02 surface).
 */
export const datasetJsonLd = (d: DatasetInput): Dataset => ({
  '@type': 'Dataset',
  name: d.name,
  description: d.description,
  url: d.url,
  license: 'https://www.apache.org/licenses/LICENSE-2.0',
  creator: { '@type': 'Organization', name: 'SaferSkills' },
})
