import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  deleteAgentUnlisted,
  fetchAgentScanRunById,
  fetchAgentScanUnlistedReport,
  promoteAgentUnlisted,
} from '@/lib/api/agent-scans'

function report(extra: Record<string, unknown> = {}) {
  return {
    id: 'r1',
    status: 'published',
    agent_name: 'acme',
    runtime: 'claude-code',
    score: 10,
    band: 'red',
    checks: [],
    findings: [],
    component_scores: [],
    visibility: 'public',
    ...extra,
  }
}

function mockFetch(res: Response) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res))
}

afterEach(() => vi.unstubAllGlobals())

describe('fetchAgentScanRunById', () => {
  it('returns the parsed report on 200', async () => {
    mockFetch(new Response(JSON.stringify(report()), { status: 200 }))
    const r = await fetchAgentScanRunById('r1')
    expect(r?.id).toBe('r1')
  })

  it('returns null on 404', async () => {
    mockFetch(new Response('', { status: 404 }))
    expect(await fetchAgentScanRunById('missing')).toBeNull()
  })

  it('defensively strips any evidence_excerpt the public route should not carry', async () => {
    const leaky = report({
      findings: [
        {
          id: 'f1',
          test_id: 'AS-06',
          evidence_excerpt: { file: 'transcript:AS-06', lang: null, truncated: false, lines: [] },
        },
      ],
    })
    mockFetch(new Response(JSON.stringify(leaky), { status: 200 }))
    const r = await fetchAgentScanRunById('r1')
    expect(r?.findings[0].evidence_excerpt).toBeNull()
  })
})

describe('fetchAgentScanUnlistedReport', () => {
  it('returns ok with the report', async () => {
    mockFetch(new Response(JSON.stringify(report({ visibility: 'unlisted' })), { status: 200 }))
    const r = await fetchAgentScanUnlistedReport('tok')
    expect(r.status).toBe('ok')
  })

  it('maps a 307 promote redirect to the /agents web path', async () => {
    mockFetch(
      new Response(null, { status: 307, headers: { Location: '/api/v1/agent-scans/abc123' } })
    )
    const r = await fetchAgentScanUnlistedReport('tok')
    expect(r).toEqual({ status: 'promoted', reportPath: '/agents/abc123' })
  })

  it('returns not_found on 404 (no oracle)', async () => {
    mockFetch(new Response('', { status: 404 }))
    expect((await fetchAgentScanUnlistedReport('tok')).status).toBe('not_found')
  })
})

describe('mutations', () => {
  it('promote returns the new run id', async () => {
    mockFetch(new Response(JSON.stringify({ id: 'pub1' }), { status: 200 }))
    expect(await promoteAgentUnlisted('tok')).toEqual({ id: 'pub1' })
  })

  it('delete resolves on 404 (already purged)', async () => {
    mockFetch(new Response('', { status: 404 }))
    await expect(deleteAgentUnlisted('tok')).resolves.toBeUndefined()
  })
})
