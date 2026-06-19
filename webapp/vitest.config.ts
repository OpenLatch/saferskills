import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['test/**/*.test.{ts,tsx}'],
  },
  resolve: {
    alias: {
      '@/': new URL('./src/', import.meta.url).pathname,
      '@ui/': new URL('../ui/', import.meta.url).pathname,
      // `astro:content` is a virtual module that only exists in the Astro build;
      // tests that touch it `vi.mock` it, but Vite still needs to RESOLVE the
      // specifier — point it at a stub so import-analysis passes.
      'astro:content': new URL('./test/stubs/astro-content.ts', import.meta.url).pathname,
    },
  },
})
