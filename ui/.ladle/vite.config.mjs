import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// Auto-merged with Ladle's internal Vite config. Adds Tailwind v4 so the
// `@import "tailwindcss"` in `ui/styles/globals.css` resolves and the @theme
// block in `tokens.css` produces real utility classes — same pipeline the
// webapp uses, so what renders in Ladle matches what ships.
export default defineConfig({
  plugins: [tailwindcss()],
})
