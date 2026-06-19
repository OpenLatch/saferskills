import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AgentScanReportDetail } from '@/lib/api/agent-scan-types'

// Mock the data layer + the (heavy, font-loading) OG renderer so the endpoint's
// guard logic is the unit under test — never the satori/resvg pipeline.
vi.mock('@/lib/api/agent-scans', () => ({ fetchAgentScanRunById: vi.fn() }))
vi.mock('@/lib/og', () => ({
  OG_HEADERS: { 'Content-Type': 'image/png' },
  renderOgCard: vi.fn(async () => Buffer.from([0x89, 0x50, 0x4e, 0x47])),
}))

const { fetchAgentScanRunById } = await import('@/lib/api/agent-scans')
const { renderOgCard } = await import('@/lib/og')
const { GET } = await import('@/pages/og/agent/[id].png')

type Ctx = Parameters<typeof GET>[0]
const ctx = (id: string): Ctx => ({ params: { id } }) as unknown as Ctx

/** A graded PUBLIC agent run — only the fields the OG endpoint reads. */
function run(over: Partial<AgentScanReportDetail> = {}): AgentScanReportDetail {
  return {
    id: '01a0c671-1028-4286-b2fc-791c21419657',
    agent_name: 'acme-agent',
    band: 'green',
    score: 88,
    visibility: 'public',
    ...over,
  } as AgentScanReportDetail
}

const mockRun = vi.mocked(fetchAgentScanRunById)
const mockRender = vi.mocked(renderOgCard)

describe('GET /og/agent/<id>.png', () => {
  beforeEach(() => {
    mockRun.mockReset()
    mockRender.mockClear()
  })
  afterEach(() => vi.restoreAllMocks())

  it('renders a 200 PNG for a graded public run', async () => {
    mockRun.mockResolvedValue(run())
    const res = await GET(ctx('01a0c671-1028-4286-b2fc-791c21419657'))
    expect(res.status).toBe(200)
    expect(res.headers.get('content-type')).toBe('image/png')
    // The card is fed the agent name, score + band (tier param).
    expect(mockRender).toHaveBeenCalledWith(
      expect.objectContaining({ displayName: 'acme-agent', score: 88, tier: 'green' })
    )
  })

  it('404s an unlisted run (never card a token-only run)', async () => {
    mockRun.mockResolvedValue(run({ visibility: 'unlisted' }))
    const res = await GET(ctx('01a0c671-1028-4286-b2fc-791c21419657'))
    expect(res.status).toBe(404)
    expect(mockRender).not.toHaveBeenCalled()
  })

  it('404s an ungraded run (score null — nothing to render)', async () => {
    mockRun.mockResolvedValue(run({ score: null }))
    const res = await GET(ctx('01a0c671-1028-4286-b2fc-791c21419657'))
    expect(res.status).toBe(404)
    expect(mockRender).not.toHaveBeenCalled()
  })

  it('404s a missing run', async () => {
    mockRun.mockResolvedValue(null)
    const res = await GET(ctx('00000000-0000-0000-0000-000000000000'))
    expect(res.status).toBe(404)
  })

  it('400s a request with no id param', async () => {
    const res = await GET(ctx(''))
    expect(res.status).toBe(400)
    expect(mockRun).not.toHaveBeenCalled()
  })
})
