import { describe, expect, it } from 'vitest'
import { exportReportMarkdown } from '@/lib/agent-report-markdown'
import type { AgentScanReportDetail } from '@/lib/api/agent-scan-types'

const RUN = {
  id: '018e7c8b-aaaa-7000-8000-000000000001',
  agent_name: 'acme-coding-agent',
  runtime: 'claude-code',
  score: 10,
  band: 'red',
  verdict_label: 'Do Not Deploy',
  pack_id: 'saferskills-agent-baseline',
  pack_version: '2026.06.09',
  findings: [{ test_id: 'AS-06' }, { test_id: 'AS-09' }],
  report_url: 'https://saferskills.ai/agents/018e7c8b-aaaa-7000-8000-000000000001',
} as unknown as AgentScanReportDetail

describe('exportReportMarkdown', () => {
  it('emits an identity + score header', () => {
    const md = exportReportMarkdown(RUN)
    expect(md).toContain('# Agent Scan — acme-coding-agent')
    expect(md).toContain('10/100 (RED)')
    expect(md).toContain('**Verdict:** Do Not Deploy')
    expect(md).toContain('**Findings:** 2')
    expect(md).toContain('/agents/018e7c8b-aaaa-7000-8000-000000000001')
  })

  it('renders an em-dash score when unscored', () => {
    const md = exportReportMarkdown({ ...RUN, score: null } as AgentScanReportDetail)
    expect(md).toContain('**Behavioral score:** — ')
  })

  it('never carries transcript/evidence (public export, D-5.6-03)', () => {
    const md = exportReportMarkdown(RUN)
    expect(md.toLowerCase()).not.toContain('transcript:')
    expect(md.toLowerCase()).not.toContain('evidence_excerpt')
  })
})
