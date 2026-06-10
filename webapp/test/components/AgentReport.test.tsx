import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import AgentReport from '@/components/agent/AgentReport'
import { track } from '@/lib/analytics'
import type { AgentScanReportDetail } from '@/lib/api/agent-scan-types'

vi.mock('@/lib/analytics', () => ({ track: vi.fn() }))

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = vi.fn()
  HTMLDialogElement.prototype.close = vi.fn()
})

const RED = {
  id: 'r1',
  status: 'published',
  agent_name: 'acme-coding-agent',
  runtime: 'claude-code',
  score: 10,
  band: 'red',
  verdict_label: 'Do Not Deploy',
  cap_callout: 'Capped to Red — 1 critical finding observed.',
  confidence: 'high',
  score_breakdown: null,
  trust_labels: ['cloud-validated', 'client-administered'],
  pack_id: 'saferskills-agent-baseline',
  pack_version: '2026.06.09',
  pack_signature_verified: true,
  capabilities_present: ['agent_response', 'tool_calls', 'file_read', 'code_exec'],
  capabilities_absent: [],
  family_tally: {},
  checks: [
    {
      test_id: 'AS-01',
      family: 'Direct injection',
      title: 'Direct prompt injection',
      verdict: 'not_observed',
      severity: 'high',
    },
    {
      test_id: 'AS-06',
      family: 'Tool-description poisoning',
      title: 'Hidden directive leaked a secret',
      verdict: 'vulnerable',
      severity: 'critical',
    },
    {
      test_id: 'AS-09',
      family: 'Unsafe code execution',
      title: 'Ran an unsafe shell chain',
      verdict: 'vulnerable',
      severity: 'high',
    },
  ],
  findings: [
    { id: 'f1', test_id: 'AS-06', evidence_excerpt: null },
    { id: 'f2', test_id: 'AS-09', evidence_excerpt: null },
  ],
  component_scores: [],
  visibility: 'public',
  expires_at: null,
  share_url: null,
  report_url: 'https://saferskills.ai/agents/r1',
  rubric_version: 'a',
  engine_version: 'b',
  latency_ms: 40,
  scanned_at: '2026-06-09T12:00:00Z',
} as unknown as AgentScanReportDetail

describe('AgentReport', () => {
  it('renders the score hero, facts, tab shell and proof-of-tests', () => {
    render(<AgentReport run={RED} shareUrl="http://x/agents/r1" ruleCount={42} />)
    expect(screen.getByText('10')).toBeTruthy()
    expect(screen.getByText('Do-Not-Deploy')).toBeTruthy()
    expect(screen.getByText('Capped to Red — 1 critical finding observed.')).toBeTruthy()
    expect(screen.getByRole('tab', { name: /Report/ })).toBeTruthy()
    expect(screen.getByText('Rules & checks applied · 3 total')).toBeTruthy()
    expect(screen.getAllByText('View finding →')).toHaveLength(2)
    expect(screen.getByText('Want a second opinion?')).toBeTruthy()
  })

  it('public report shows the share/export bar but NO delete', () => {
    render(<AgentReport run={RED} shareUrl="http://x/agents/r1" ruleCount={42} />)
    expect(screen.getByText('⧉ Share with your security team')).toBeTruthy()
    expect(screen.getByText('↧ Export Markdown')).toBeTruthy()
    expect(screen.queryByText('Delete')).toBeNull()
    expect(screen.queryByText('↥ Promote to public')).toBeNull()
  })

  it('switching to Findings fires telemetry + shows the placeholder', () => {
    render(<AgentReport run={RED} shareUrl="http://x/agents/r1" ruleCount={42} />)
    fireEvent.click(screen.getByRole('tab', { name: /Findings/ }))
    expect(track).toHaveBeenCalledWith('agent_report_tab_selected', { tab: 'findings' })
  })

  it('unlisted report adds the manage actions + right-of-reply', () => {
    render(
      <AgentReport
        run={{ ...RED, visibility: 'unlisted' } as AgentScanReportDetail}
        shareUrl="http://x/agents/r/tok"
        ruleCount={42}
        unlisted
        token="tok"
      />
    )
    expect(screen.getByText('↥ Promote to public')).toBeTruthy()
    expect(screen.getByText('Delete')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Add a public reply' })).toBeTruthy()
  })
})
