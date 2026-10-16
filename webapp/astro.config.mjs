import mdx from '@astrojs/mdx'
import node from '@astrojs/node'
import react from '@astrojs/react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, passthroughImageService } from 'astro/config'
import remarkDirective from 'remark-directive'
import { remarkAsides } from './src/lib/docs/remark-asides.mjs'

const release = /^[a-f\d]{40}$/.test(process.env.PUBLIC_GIT_SHA ?? '')
  ? process.env.PUBLIC_GIT_SHA
  : undefined
if (process.env.SOURCEMAP_UPLOAD === '1' && !release) {
  throw new Error('Source-map uploads require PUBLIC_GIT_SHA to be a full Git commit SHA')
}

// Astro 6 — `output: 'server'` with per-page `export const prerender = true` opt-in
// for SSG. Astro v5+ removed `hybrid`; this is the supported equivalent.
// See plan/01a-design-system-foundation.md §1.6 (D-FE-22).
export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  site: 'https://saferskills.ai',
  // Astro's CSRF guard (`checkOrigin`, default-on for SSR) rejects multipart/
  // form-urlencoded/text POSTs whose `Origin` doesn't match the reconstructed
  // request origin. Behind Fly's TLS-terminating edge the Node server sees the
  // request as `http://` internally, so a genuinely same-origin upload (browser
  // `Origin: https://…`) is mis-judged cross-site → "Cross-site POST form
  // submissions are forbidden" 403 on `/api/v1/scans/upload` (multipart) while
  // JSON repo-scan POSTs slip through. We have NO native Astro form handlers —
  // every mutation goes through the `/api/*` proxy to the backend, which is
  // directly reachable and guarded by Turnstile + per-IP rate limits, not by
  // origin. So this check only breaks legitimate uploads; turn it off.
  security: { checkOrigin: false },
  // The dev toolbar's client entrypoint persistently 504s ("Outdated Optimize
  // Dep") under Astro 6.4.3 + Vite — dev-only console noise with no app impact.
  // The toolbar is optional tooling; disable it so the dev console stays clean.
  devToolbar: { enabled: false },
  integrations: [react(), mdx()],
  // Native docs (I-06) are prerendered into dist/client/docs as directory-format
  // pages → served at `/docs/<section>/<page>/` (trailing-slash parity with the
  // retired Starlight build). `format: 'directory'` is also fine for the existing
  // marketing pages (about/methodology) which already build to <name>/index.html.
  // Source-map injection changes JS after Vite computes its content hashes.
  // Version the asset directory so immutable browser/CDN caches cannot reuse
  // an older, uninstrumented bundle under the same pre-injection filename.
  build: { format: 'directory', assets: release ? `_astro/${release}` : '_astro' },
  // Sharp-free image service: the docs Screenshot component optimizes PNGs via
  // astro:assets, but the webapp Docker builder is node:alpine (musl) where Sharp
  // fails. The app uses no other <Image>, so passthrough is collateral-free.
  image: { service: passthroughImageService() },
  // Docs `:::note`/`:::tip` asides stay markdown-native: remark-directive parses
  // them, remarkAsides maps them to design-system <aside> callouts. Scoped to
  // MD/MDX content — the generated methodology MDX has no `:::` directives.
  markdown: {
    remarkPlugins: [remarkDirective, remarkAsides],
    // Always-dark code blocks (matches the site's terminal aesthetic). The
    // default `github-dark` fails WCAG AA on comment tokens (3.04:1); the
    // high-contrast GitHub theme clears AA — gated by the docs axe spec in the
    // lighthouse-a11y lane.
    shikiConfig: { theme: 'github-dark-high-contrast' },
  },
  vite: {
    plugins: [tailwindcss()],
    build: { sourcemap: process.env.SOURCEMAP_UPLOAD === '1' ? 'hidden' : false },
  },
  server: {
    port: 5173,
    host: true,
  },
  experimental: {
    clientPrerender: true,
  },
})
