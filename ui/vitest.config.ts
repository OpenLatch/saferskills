import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['test/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      thresholds: { lines: 70, statements: 70, functions: 60, branches: 60 },
    },
  },
  resolve: {
    alias: {
      '@/': new URL('./', import.meta.url).pathname,
    },
  },
});
