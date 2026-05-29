import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright config for the `lighthouse-a11y` CI lane's axe smoke suite
 * (`webapp/test/a11y/*.spec.ts`). Targets a webapp already running on :5173
 * (started by the CI lane against the compose-provided API). No webServer
 * block — the lane owns process lifecycle.
 */
export default defineConfig({
  testDir: './test/a11y',
  fullyParallel: true,
  reporter: 'list',
  timeout: 30_000,
  use: {
    baseURL: process.env.PUBLIC_SITE_URL ?? 'http://localhost:5173',
    headless: true,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
