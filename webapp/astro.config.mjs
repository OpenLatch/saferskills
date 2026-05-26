import mdx from '@astrojs/mdx'
import react from '@astrojs/react'
import { defineConfig } from 'astro/config'

// https://astro.build/config
export default defineConfig({
  output: 'static',
  site: 'https://saferskills.ai',
  integrations: [react(), mdx()],
  vite: {
    plugins: [],
  },
  server: {
    port: 5173,
    host: true,
  },
})
