import { describe, expect, it } from 'vitest'

import { agentOgImage, scanOgImage } from '@/lib/seo/og-image'

// SEO-T5. These pin the per-page rule that drives `<Base ogImage={...}>`:
// only a COMPLETED scan / GRADED agent run gets its dynamic score card; any other
// state (pending/running/failed scan, ungraded agent run) falls back to the static
// `/og-image.png` (undefined → Base.astro substitutes the default). The scan gate
// MUST mirror the scan-OG endpoint's `status !== 'completed'` 404 so the advertised
// URL never 404s, and a `failed` run never mints a bogus card.
const SITE = new URL('https://saferskills.ai')

describe('scanOgImage', () => {
  it('a completed run sets og:image to /og/scan/<id>.png', () => {
    expect(scanOgImage('run-123', 'completed', SITE)).toBe(
      'https://saferskills.ai/og/scan/run-123.png'
    )
  })

  it('a non-completed run keeps the default (undefined) — pending/running/failed', () => {
    for (const status of ['pending', 'running', 'failed']) {
      expect(scanOgImage('run-123', status, SITE)).toBeUndefined()
    }
  })
})

describe('agentOgImage', () => {
  it('a graded run sets og:image to /og/agent/<id>.png', () => {
    expect(agentOgImage('agent-9', 88, SITE)).toBe('https://saferskills.ai/og/agent/agent-9.png')
  })

  it('a graded run with score 0 still cards (0 is graded, not null)', () => {
    expect(agentOgImage('agent-9', 0, SITE)).toBe('https://saferskills.ai/og/agent/agent-9.png')
  })

  it('an ungraded run (score null) keeps the default (undefined)', () => {
    expect(agentOgImage('agent-9', null, SITE)).toBeUndefined()
  })
})
