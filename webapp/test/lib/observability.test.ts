import { describe, expect, it } from 'vitest'
import { redactCapabilityToken } from '@/lib/observability'

const TOKEN = 'Hh3y6Qk2pN8fT0aZ1cV9bWx'

describe('redactCapabilityToken', () => {
  // I-5.6 Codex P0-2 / matrix-22 — the possession-is-auth token must be redacted
  // for the scan capability URL, the agent report PAGE URL, AND the agent API URL.
  it.each([
    ['/scans/r/', 'https://saferskills.ai/scans/r/'],
    ['/agents/r/', 'https://saferskills.ai/agents/r/'],
    ['/agent-scans/r/', 'https://saferskills.ai/api/v1/agent-scans/r/'],
  ])('redacts the token after %s', (prefix, base) => {
    const out = redactCapabilityToken(`${base}${TOKEN}?ref=x`)
    expect(out).toBeDefined()
    expect(out).not.toContain(TOKEN)
    expect(out).toContain(`${prefix}<redacted>`)
  })

  it('leaves a public /agents/{id} page URL untouched (no secret)', () => {
    const url = 'https://saferskills.ai/agents/018e7c8b-aaaa-7000-8000-000000000001'
    expect(redactCapabilityToken(url)).toBe(url)
  })

  it('passes undefined through', () => {
    expect(redactCapabilityToken(undefined)).toBeUndefined()
  })
})
