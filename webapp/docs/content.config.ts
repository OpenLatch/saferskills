import { defineCollection, z } from 'astro:content'
import { docsLoader } from '@astrojs/starlight/loaders'
import { docsSchema } from '@astrojs/starlight/schema'

// Starlight content collection (D-8, D-11). `docsSchema()` already provides the
// Starlight frontmatter (title, description, draft, sidebar, …). We extend it
// with the two SEO-layer fields the docs author byline + freshness tooling
// reads (Plan 2 SEO-D3): `author` and `updated`. Both optional at the schema
// level — the stricter "required on methodology/analytical pages" rule is a
// content-review gate, not a build gate.
//
// `scripts/validate-docs-frontmatter.cjs` (CI) enforces the harder contract:
// every page MUST carry `title` + `description`.
export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        author: z.string().optional(),
        updated: z.coerce.date().optional(),
      }),
    }),
  }),
}
