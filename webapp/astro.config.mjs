import mdx from '@astrojs/mdx'
import node from '@astrojs/node'
import react from '@astrojs/react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'astro/config'

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
  integrations: [react(), mdx()],
  vite: {
    plugins: [tailwindcss()],
  },
  server: {
    port: 5173,
    host: true,
  },
  experimental: {
    clientPrerender: true,
  },
})
