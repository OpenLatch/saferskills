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
