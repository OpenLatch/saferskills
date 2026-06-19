import type { CollectionEntry } from 'astro:content'
import { getCollection } from 'astro:content'
import { DOCS_SECTIONS, titleCaseDir } from './sections'

/**
 * Auto-derived docs navigation.
 *
 * Builds the sidebar tree + the flat reading order from the `docs` content
 * collection — adding a markdown file auto-joins its section, no config edit.
 * Sections come from the top-level folder (ordered by DOCS_SECTIONS); pages
 * within a section sort: section-index first, then frontmatter `order`, then
 * slug — which reproduces the shipped order when no `order` is set.
 */
export type DocsEntry = CollectionEntry<'docs'>

export interface DocsNavItem {
  title: string
  href: string
  /** Nesting depth beyond the section root (0 = direct child) — for indent. */
  depth: number
}

export interface DocsNavGroup {
  label: string
  dir: string
  items: DocsNavItem[]
}

/** glob-loader id → route slug. Collapses `index` / `<path>/index` to the parent. */
export function idToSlug(id: string): string {
  if (id === 'index') return ''
  return id.replace(/\/index$/, '')
}

/** Route slug → canonical `/docs/<slug>/` URL (trailing slash; root = `/docs/`). */
export function docsHref(id: string): string {
  const slug = idToSlug(id)
  return slug ? `/docs/${slug}/` : '/docs/'
}

/** Section folder → display label (known section, else title-cased dir). */
export function sectionLabel(dir: string): string {
  return DOCS_SECTIONS.find((s) => s.dir === dir)?.label ?? titleCaseDir(dir)
}

function sortKey(entry: DocsEntry, slug: string, dir: string): [number, number, string] {
  // section index first, then frontmatter order, then slug (alpha)
  return [slug === dir ? 0 : 1, entry.data.order ?? Number.POSITIVE_INFINITY, slug]
}

export async function buildDocsNav(): Promise<DocsNavGroup[]> {
  const entries = await getCollection('docs')
  const byDir = new Map<string, DocsEntry[]>()
  for (const e of entries) {
    const slug = idToSlug(e.id)
    if (slug === '') continue // the root index is the /docs overview, not a leaf
    const dir = slug.split('/')[0]
    const list = byDir.get(dir) ?? []
    list.push(e)
    byDir.set(dir, list)
  }

  const knownDirs = DOCS_SECTIONS.map((s) => s.dir)
  const extraDirs = [...byDir.keys()].filter((d) => !knownDirs.includes(d)).sort()
  const orderedDirs = [...knownDirs, ...extraDirs]

  const groups: DocsNavGroup[] = []
  for (const dir of orderedDirs) {
    const list = byDir.get(dir)
    if (!list?.length) continue
    const label = sectionLabel(dir)
    const items = list
      .map((e) => ({ e, slug: idToSlug(e.id) }))
      .sort((a, b) => {
        const ka = sortKey(a.e, a.slug, dir)
        const kb = sortKey(b.e, b.slug, dir)
        return ka[0] - kb[0] || ka[1] - kb[1] || a.slug.localeCompare(b.slug)
      })
      .map(({ e, slug }) => ({
        title: e.data.sidebarLabel ?? e.data.title,
        href: docsHref(e.id),
        // depth beyond the section: install/cli-reference/install → depth 1
        depth: Math.max(0, slug.split('/').length - 2),
      }))
    groups.push({ label, dir, items })
  }
  return groups
}

/** Flatten the nav to the linear reading order (drives prev/next pagination). */
export function flattenNav(groups: DocsNavGroup[]): DocsNavItem[] {
  return groups.flatMap((g) => g.items)
}
