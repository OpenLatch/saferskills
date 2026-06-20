import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ScanRunReportDetail } from '@/lib/api/scans'

import { makeUploadRun } from '../factories/run-report'

// Mock the data layer + the (heavy, font-loading) OG renderer so the endpoint's
// guard logic is the unit under test — never the satori/resvg pipeline.
vi.mock('@/lib/api/scans', () => ({ fetchScanRunById: vi.fn() }))
vi.mock('@/lib/og', () => ({
  OG_HEADERS: { 'Content-Type': 'image/png' },
  renderOgCard: vi.fn(async () => Buffer.from([0x89, 0x50, 0x4e, 0x47])),
}))

const { fetchScanRunById } = await import('@/lib/api/scans')
const { renderOgCard } = await import('@/lib/og')
const { GET } = await import('@/pages/og/scan/[scan_id].png')

type Ctx = Parameters<typeof GET>[0]
const ctx = (scan_id: string): Ctx => ({ params: { scan_id } }) as unknown as Ctx

function run(over: Partial<ScanRunReportDetail> = {}): ScanRunReportDetail {
  return makeUploadRun({
    github_url: 'https://github.com/openai/skills',
    source_kind: 'github',
    visibility: 'public',
    status: 'completed',
    repo_aggregate_score: 87,
    repo_tier: 'green',
    capabilities: [],
    uploaded_filename: null,
    ...over,
  })
}

const mockRun = vi.mocked(fetchScanRunById)
const mockRender = vi.mocked(renderOgCard)

describe('GET /og/scan/<id>.png', () => {
  beforeEach(() => {
    mockRun.mockReset()
    mockRender.mockClear()
  })
  afterEach(() => vi.restoreAllMocks())

  it('renders a 200 PNG for a COMPLETED public run', async () => {
    mockRun.mockResolvedValue(run({ status: 'completed' }))
    const res = await GET(ctx('01a0c671-1028-4286-b2fc-791c21419657'))
    expect(res.status).toBe(200)
    expect(res.headers.get('content-type')).toBe('image/png')
  })

  it('404s a non-completed run (pending / running / failed) — no bogus card', async () => {
    for (const status of ['pending', 'running', 'failed'] as const) {
      mockRun.mockResolvedValue(run({ status }))
      const res = await GET(ctx('01a0c671-1028-4286-b2fc-791c21419657'))
      expect(res.status).toBe(404)
    }
    expect(mockRender).not.toHaveBeenCalled()
  })

  it('404s an unlisted run (never card a token-only run)', async () => {
    mockRun.mockResolvedValue(run({ visibility: 'unlisted', status: 'completed' }))
    const res = await GET(ctx('01a0c671-1028-4286-b2fc-791c21419657'))
    expect(res.status).toBe(404)
    expect(mockRender).not.toHaveBeenCalled()
  })

  it('404s a missing run', async () => {
    mockRun.mockResolvedValue(null)
    const res = await GET(ctx('00000000-0000-0000-0000-000000000000'))
    expect(res.status).toBe(404)
  })

  it('400s a request with no scan_id param', async () => {
    const res = await GET(ctx(''))
    expect(res.status).toBe(400)
    expect(mockRun).not.toHaveBeenCalled()
  })
})
