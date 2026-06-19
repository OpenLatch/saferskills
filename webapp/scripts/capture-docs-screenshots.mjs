#!/usr/bin/env node
/* capture-docs-screenshots.mjs — scripted, re-runnable product screenshots for
 * the docs.
 *
 * Captures the real product surfaces in BOTH themes (light + dark) and writes
 * them to `webapp/src/assets/docs-screenshots/<surface>.<theme>.png`, where the
 * `Screenshot.astro` component embeds them theme-aware. Re-run any time to keep
 * the shots current — they never go stale because nothing is hand-edited.
 *
 * Target is data-driven + resilient: it resolves a representative item slug /
 * scan-run id / agent-run id from the live API at run time (so report shots
 * survive data changes) and SKIPS — with a logged note — any surface whose data
 * isn't present, rather than emitting a broken shot.
 *
 *   Base URL (default = staging, the durable public refresh target):
 *     SAFERSKILLS_SCREENSHOT_BASE=https://saferskills-webapp-staging.fly.dev
 *   Override for a local rich-data capture (e.g. before staging is scanned):
 *     SAFERSKILLS_SCREENSHOT_BASE=http://127.0.0.1:4399 \
 *       node webapp/scripts/capture-docs-screenshots.mjs
 *
 * NOT a CI lane — it needs a running deployment and is slow; it is an on-demand
 * refresh (see webapp/src/assets/docs-screenshots/README.md). The committed PNGs are
 * what the docs build embeds; this script regenerates them.
 */
import { mkdir, readdir, stat } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const OUT_DIR = path.resolve(HERE, '../src/assets/docs-screenshots')
const BASE = (
  process.env.SAFERSKILLS_SCREENSHOT_BASE || 'https://saferskills-webapp-staging.fly.dev'
).replace(/\/$/, '')

const VIEWPORT = { width: 1440, height: 900 }
const DEVICE_SCALE_FACTOR = 2
const NAV_TIMEOUT = 30_000
const THEMES = ['light', 'dark']

/** Resolve a JSON body from the live API, or null on any failure. */
async function api(pathname) {
  try {
    const res = await fetch(`${BASE}${pathname}`, { headers: { Accept: 'application/json' } })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

/** Resolve the data-driven report targets (item slug / scan-run id / agent-run
 *  id). Each may be null → its surface(s) are skipped + logged. */
async function resolveTargets() {
  const targets = { itemSlug: null, scanId: null, agentId: null }

  // A representative PUBLIC item that has actually been scored (prefer the
  // richest report — highest aggregate score among the first page).
  const items = await api('/api/v1/items?limit=24')
  const candidates = (items?.data ?? []).map((it) => it.slug).filter(Boolean)
  for (const slug of candidates) {
    const detail = await api(`/api/v1/items/${encodeURIComponent(slug)}`)
    const scan = detail?.latest_scan
    if (scan?.id) {
      targets.itemSlug ??= slug
      // The scan-report route (`/scans/<id>`) keys on the scan-run id; the item
      // surfaces the per-capability scan id + (when present) its run id.
      targets.scanId ??= scan.scan_run_id ?? scan.run_id ?? scan.id
      if (targets.itemSlug && targets.scanId) break
    }
  }
  // Fall back to the first item even if unscored, so the item page still shoots.
  targets.itemSlug ??= candidates[0] ?? null

  // A graded/published agent run for the Agent Report.
  const agents = await api('/api/v1/agent-scans?limit=24')
  const agentRun =
    (agents?.data ?? []).find((r) => r?.id && r?.score != null) ?? (agents?.data ?? [])[0]
  targets.agentId = agentRun?.id ?? null

  return targets
}

/** Build the surface list from the resolved targets. A surface with a null id is
 *  dropped here (and reported in the run summary). */
function buildSurfaces(t) {
  const all = [
    { name: 'homepage', path: '/', waitFor: 'nav .brand' },
    { name: 'catalog', path: '/capabilities', waitFor: 'nav .brand' },
    { name: 'scan-form', path: '/scan', waitFor: 'nav .brand' },
    { name: 'agent-directory', path: '/agents', waitFor: 'nav .brand' },
    t.itemSlug && {
      name: 'item-report',
      path: `/items/${encodeURIComponent(t.itemSlug)}`,
      waitFor: 'nav .brand',
    },
    t.scanId && { name: 'scan-report', path: `/scans/${t.scanId}`, waitFor: 'nav .brand' },
    t.agentId && { name: 'agent-report', path: `/agents/${t.agentId}`, waitFor: 'nav .brand' },
  ]
  return all.filter(Boolean)
}

async function capture(browser, surface, theme) {
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: DEVICE_SCALE_FACTOR,
    colorScheme: theme,
  })
  // Seed the theme BEFORE first paint — the FOUC-prevention script reads
  // `localStorage['ss-theme']` and applies `html.dark` accordingly.
  await context.addInitScript((mode) => {
    try {
      localStorage.setItem('ss-theme', mode)
    } catch {
      /* private mode — colorScheme still drives the prefers-color-scheme path */
    }
  }, theme)

  const page = await context.newPage()
  try {
    await page.goto(`${BASE}${surface.path}`, { waitUntil: 'load', timeout: NAV_TIMEOUT })
    if (surface.waitFor) {
      await page.waitForSelector(surface.waitFor, { timeout: NAV_TIMEOUT }).catch(() => {})
    }
    // Settle islands + fonts + any above-the-fold fetches, then a short beat for
    // entrance transitions so shots are deterministic.
    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {})
    await page.evaluate(() => document.fonts?.ready).catch(() => {})
    await page.waitForTimeout(600)
    const file = path.join(OUT_DIR, `${surface.name}.${theme}.png`)
    await page.screenshot({ path: file, animations: 'disabled' })
    const { size } = await stat(file)
    return { ok: true, file, kb: Math.round(size / 1024) }
  } catch (err) {
    return { ok: false, error: String(err?.message ?? err) }
  } finally {
    await context.close()
  }
}

async function main() {
  console.log(`[screenshots] base = ${BASE}`)
  await mkdir(OUT_DIR, { recursive: true })

  const targets = await resolveTargets()
  console.log('[screenshots] targets:', JSON.stringify(targets))
  const surfaces = buildSurfaces(targets)

  const skipped = ['item-report', 'scan-report', 'agent-report'].filter(
    (n) => !surfaces.some((s) => s.name === n)
  )
  if (skipped.length) {
    console.warn(
      `[screenshots] SKIPPED (no data on ${BASE}): ${skipped.join(', ')} — ` +
        're-run against a deployment that has scored items / agent scans.'
    )
  }

  const browser = await chromium.launch()
  let captured = 0
  try {
    for (const surface of surfaces) {
      for (const theme of THEMES) {
        const r = await capture(browser, surface, theme)
        if (r.ok) {
          captured++
          console.log(`  ✓ ${surface.name}.${theme}.png (${r.kb} KB)`)
        } else {
          console.error(`  ✗ ${surface.name}.${theme} — ${r.error}`)
        }
      }
    }
  } finally {
    await browser.close()
  }

  const before = await readdir(OUT_DIR).then((f) => f.filter((x) => x.endsWith('.png')).length)
  console.log(
    `[screenshots] captured ${captured} image(s); ${before} PNG(s) now in src/assets/docs-screenshots/`
  )
}

main().catch((err) => {
  console.error('[screenshots] FAILED:', err)
  process.exit(1)
})
