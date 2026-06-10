import { describe, expect, it } from 'vitest'
import { asAgentScanReportDetail, isPreGrade, isReportable } from '@/lib/api/agent-scan-types'

const VALID = {
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
}

describe('asAgentScanReportDetail', () => {
  it('accepts a well-formed report', () => {
    expect(asAgentScanReportDetail(VALID)).not.toBeNull()
  })

  it.each([
    ['null', null],
    ['a string', 'nope'],
    ['missing id', { ...VALID, id: 123 }],
    ['bad status', { ...VALID, status: 'weird' }],
    ['bad band', { ...VALID, band: 'purple' }],
    ['bad visibility', { ...VALID, visibility: 'secret' }],
    ['checks not array', { ...VALID, checks: {} }],
  ])('rejects %s → null', (_label, value) => {
    expect(asAgentScanReportDetail(value)).toBeNull()
  })
})

describe('status helpers', () => {
  it('classifies pre-grade vs reportable', () => {
    expect(isPreGrade('created')).toBe(true)
    expect(isPreGrade('submitted')).toBe(true)
    expect(isPreGrade('graded')).toBe(false)
    expect(isReportable('graded')).toBe(true)
    expect(isReportable('published')).toBe(true)
    expect(isReportable('aborted')).toBe(false)
  })
})
