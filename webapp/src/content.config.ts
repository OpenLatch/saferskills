import { defineCollection, z } from 'astro:content'
import { glob } from 'astro/loaders'

/**
 * Native docs content collection (replaces the separate Starlight app).
 * Markdown/MDX authored under `src/content/docs/**`, rendered by
 * `src/pages/docs/[...slug].astro` inside the main app with the design system.
 *
 * The `glob` loader (not Starlight's `docsLoader`) gives us plain Astro entries:
 * `entry.id` is the extension-less slug with `index` collapsed (e.g.
 * `getting-started/quickstart`, `install/cli-reference`), which maps 1:1 to the
 * `/docs/<id>/` URLs (build.format: 'directory' in astro.config.mjs).
 *
 * Schema: `title` + `description` are required (SEO + the frontmatter CI gate).
 * `updated`/`author` already exist on the content; `order` + `sidebarLabel` are
 * NEW + optional — the auto-derived sidebar (src/lib/docs/nav.ts) sorts by
 * `order ?? Infinity` then filename, so omitting them preserves the shipped order.
 */
export const collections = {
  docs: defineCollection({
    loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/docs' }),
    schema: z.object({
      title: z.string(),
      description: z.string(),
      updated: z.coerce.date().optional(),
      author: z.string().optional(),
      /** Sidebar sort key within a section (lower first); falls back to filename. */
      order: z.number().optional(),
      /** Overrides the sidebar label (defaults to `title`). */
      sidebarLabel: z.string().optional(),
    }),
  }),
}
