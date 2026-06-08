import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ScanRunReportDetail } from '@/lib/api/scans'

import { makeCapability, makeUploadRun } from '../factories/run-report'

// Regression: the public `/scans` list (and every share/feed surface) exposes a
// RUN id, not a per-capability scan id. The badge route must resolve the run via
// `fetchScanRunById` — resolving it as a capability scan 404'd the e2e
// `badge-endpoint` check once staging had its first scan. See `tools/e2e`.
vi.mock('@/lib/api/scans', () => ({ fetchScanRunById: vi.fn() }))

const { fetchScanRunById } = await import('@/lib/api/scans')
const { GET } = await import('@/pages/badge/[scan_id]/[score].svg')

type BadgeContext = Parameters<typeof GET>[0]

function ctx(scanId: string, score: string): BadgeContext {
  return { params: { scan_id: scanId, score } } as unknown as BadgeContext
}

/** A PUBLIC single-capability GitHub run (the badge/feed shape), built on the
 * shared factory so it tracks the DTO — mirrors `makeUnlistedGithubRun`. */
function run(overrides: Partial<ScanRunReportDetail> = {}): ScanRunReportDetail {
  return makeUploadRun({
    github_url: 'https://github.com/openai/skills',
    source_kind: 'github',
    visibility: 'public',
    repo_aggregate_score: 87,
    repo_tier: 'green',
    capabilities: [],
    uploaded_filename: null,
    ...overrides,
  })
}

const mockRun = vi.mocked(fetchScanRunById)

describe('GET /badge/<run_id>/<score>.svg', () => {
  beforeEach(() => mockRun.mockReset())
  afterEach(() => vi.restoreAllMocks())

  it('renders an SVG when the score matches the run repo aggregate score', async () => {
    mockRun.mockResolvedValue(run({ repo_aggregate_score: 87, repo_tier: 'green' }))
    const res = await GET(ctx('01a0c671-1028-4286-b2fc-791c21419657', '87'))
    expect(res.status).toBe(200)
    expect(res.headers.get('content-type')).toContain('image/svg+xml')
    expect(await res.text()).toContain('<svg')
  })

  it('renders for a failed/unscored run (score 0, unscoped) — the e2e case', async () => {
    mockRun.mockResolvedValue(run({ repo_aggregate_score: 0, repo_tier: 'unscoped' }))
    const res = await GET(ctx('01a0c671-1028-4286-b2fc-791c21419657', '0'))
    expect(res.status).toBe(200)
    expect(await res.text()).toContain('UNSCOPED')
  })

  it('accepts a capability score (per-file upload badge)', async () => {
    mockRun.mockResolvedValue(
      run({
        repo_aggregate_score: 50,
        capabilities: [makeCapability({ aggregate_score: 91, tier: 'green' })],
      })
    )
    const res = await GET(ctx('01a0c671-1028-4286-b2fc-791c21419657', '91'))
    expect(res.status).toBe(200)
  })

  it('rejects a tampered score with 400', async () => {
    mockRun.mockResolvedValue(run({ repo_aggregate_score: 87 }))
    const res = await GET(ctx('01a0c671-1028-4286-b2fc-791c21419657', '999'))
    expect(res.status).toBe(400)
  })

  it('404s a missing run', async () => {
    mockRun.mockResolvedValue(null)
    const res = await GET(ctx('00000000-0000-0000-0000-000000000000', '50'))
    expect(res.status).toBe(404)
  })

  it('never badges an unlisted run (404)', async () => {
    mockRun.mockResolvedValue(run({ visibility: 'unlisted', repo_aggregate_score: 87 }))
    const res = await GET(ctx('01a0c671-1028-4286-b2fc-791c21419657', '87'))
    expect(res.status).toBe(404)
  })
})
