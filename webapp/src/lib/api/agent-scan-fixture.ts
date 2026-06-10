/**
 * DEV-ONLY Agent Scan fixture loader (I-5.6 D-5.6-04 — build against the fixture
 * before the live grader is wired).
 *
 * SERVER-ONLY: uses `node:fs`, so it must be imported ONLY from `.astro`
 * frontmatter (never an island), and ONLY behind an `import.meta.env.DEV` guard —
 * which Vite statically replaces with `false` in a prod build, dead-code-eliminating
 * the dynamic `import()` of this module entirely. The fixture never reaches the
 * client bundle and never ships to production.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { type AgentScanReportDetail, asAgentScanReportDetail } from './agent-scan-types'

export type AgentFixtureKey = 'red_public' | 'red_private' | 'green_pass'

const FIXTURE_KEYS: ReadonlySet<string> = new Set(['red_public', 'red_private', 'green_pass'])

export function isAgentFixtureKey(value: string | null): value is AgentFixtureKey {
  return value !== null && FIXTURE_KEYS.has(value)
}

/** Load one keyed projection from the repo-root fixture, validated through the
 * same runtime guard the live fetch uses. Returns `null` on any failure (missing
 * file, bad key, malformed shape) so the route falls through to the live fetch. */
export function loadAgentFixture(key: AgentFixtureKey): AgentScanReportDetail | null {
  try {
    // Resolve relative to THIS module → repo-root/fixtures, independent of cwd.
    const path = fileURLToPath(
      new URL('../../../../fixtures/agent-scan-report.sample.json', import.meta.url)
    )
    const raw = JSON.parse(readFileSync(path, 'utf-8')) as Record<string, unknown>
    return asAgentScanReportDetail(raw[key])
  } catch {
    return null
  }
}
