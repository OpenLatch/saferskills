import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import AgentReport from '@/components/agent/AgentReport'
import AgentReportActions from '@/components/agent/AgentReportActions'
import { track } from '@/lib/analytics'
import type { AgentScanReportDetail } from '@/lib/api/agent-scan-types'

vi.mock('@/lib/analytics', () => ({ track: vi.fn() }))

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = vi.fn()
  HTMLDialogElement.prototype.close = vi.fn()
})

const SCORE_BREAKDOWN = {
  findings: [
    { test_id: 'AS-06', severity: 'critical', score_delta: -40 },
    { test_id: 'AS-09', severity: 'high', score_delta: -25 },
    { test_id: 'AS-17', severity: 'high', score_delta: -25 },
  ],
  raw_score: 10,
  ceiling: 15,
  ceiling_applied: false,
  final_score: 10,
  band_mapping: 'score 10 -> band red',
}

function finding(over: Record<string, unknown>) {
  return {
    id: 'f-default',
    test_id: 'AS-06',
    severity: 'critical',
    verdict: 'vulnerable',
    family: 'Tool-description poisoning',
    owasp_refs: ['ASI04:2026'],
    atlas_refs: ['AML.T0053'],
    nist_refs: [],
    score_delta: -40,
    detection_rule: 'tool_arg',
    leaked_canary_slot: 'AS-06',
    title: 'Hidden directive leaked a secret',
    explanation: 'A hidden tool-description directive exfiltrated a planted secret.',
    severity_rationale: 'a planted secret left the agent inside a tool argument',
    category_label: 'Tool-description poisoning',
    remediation: {
      action: 'Strip embedded directives at registration.',
      steps: ['Strip directives.'],
      safer_pattern: { before: 'hidden directive', after: 'plain description' },
    },
    evidence_excerpt: null,
    ...over,
  }
}

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
  score_breakdown: SCORE_BREAKDOWN,
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
    finding({ id: 'f1', test_id: 'AS-06' }),
    finding({
      id: 'f2',
      test_id: 'AS-09',
      severity: 'high',
      family: 'Unsafe code execution',
      owasp_refs: ['ASI05:2026'],
      atlas_refs: ['AML.T0054'],
      title: 'Ran an unsafe shell chain',
      category_label: 'Unsafe code execution',
      remediation: {
        action: 'Gate execution.',
        steps: ['Reject piped shell.'],
        safer_pattern: null,
      },
    }),
  ],
  component_scores: [
    {
      kind: 'skill',
      name: 'pdf-extract',
      path: 'skills/pdf-extract',
      score: 82,
      tier: 'green',
      slug: 'a--b--skill-pdf-extract',
    },
    {
      kind: 'mcp_server',
      name: 'payments',
      path: 'servers/payments',
      score: 47,
      tier: 'orange',
      slug: 'a--b--mcp-server-payments',
    },
  ],
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
    const { container } = render(
      <AgentReport run={RED} shareUrl="http://x/agents/r1" ruleCount={42} />
    )
    expect(container.querySelector('.sr-big')?.textContent).toContain('10')
    expect(container.querySelector('.cap-reason p')?.textContent).toBe(
      'Capped to Red — 1 critical finding observed.'
    )
    expect(screen.getByRole('tab', { name: /Report/ })).toBeTruthy()
    expect(screen.getByText('Rules & checks applied · 3 total')).toBeTruthy()
    expect(screen.getAllByText('View finding →')).toHaveLength(2)
  })

  it('public manage bar (page-head island) shows share/export but NO delete', () => {
    render(<AgentReportActions run={RED} shareUrl="http://x/agents/r1" />)
    expect(screen.getByText('⧉ Copy Report Link')).toBeTruthy()
    expect(screen.getByText('↧ Export Markdown')).toBeTruthy()
    expect(screen.queryByText('Delete')).toBeNull()
    expect(screen.queryByText('↥ Promote to public')).toBeNull()
  })

  it('unlisted manage bar adds Promote + Delete', () => {
    render(<AgentReportActions run={RED} shareUrl="http://x/agents/r/tok" unlisted token="tok" />)
    expect(screen.getByText('⧉ Copy private link')).toBeTruthy()
    expect(screen.getByText('↥ Promote to public')).toBeTruthy()
    expect(screen.getByText('Delete')).toBeTruthy()
  })

  it('Findings tab renders OWASP groups, ref chips, score-math and the public evidence note', () => {
    render(<AgentReport run={RED} shareUrl="http://x/agents/r1" ruleCount={42} />)
    fireEvent.click(screen.getByRole('tab', { name: /Findings/ }))
    expect(track).toHaveBeenCalledWith('agent_report_tab_selected', { tab: 'findings' })
    // OWASP family group head + deep-linked ref chip (family repeats: head + card meta)
    expect(screen.getAllByText('Tool-description poisoning').length).toBeGreaterThan(0)
    expect(screen.getAllByText('ASI04:2026').length).toBeGreaterThan(0)
    // per-finding score-math reconciles to the headline score
    expect(screen.getAllByText('Base').length).toBeGreaterThan(0)
    // public route → transcript withheld, never a transcript
    expect(screen.getAllByText('transcript withheld on the public report').length).toBeGreaterThan(
      0
    )
    expect(screen.queryByText(/Confirmed exfiltration/)).toBeNull()
    expect(screen.getByText('Export all fixes as checklist')).toBeTruthy()
  })

  it('"View finding →" jumps to the Findings tab', () => {
    render(<AgentReport run={RED} shareUrl="http://x/agents/r1" ruleCount={42} />)
    fireEvent.click(screen.getAllByText('View finding →')[0])
    expect(track).toHaveBeenCalledWith('agent_report_tab_selected', { tab: 'findings' })
  })

  it('Component Scores tab lists capabilities as context, linking to /items', () => {
    render(<AgentReport run={RED} shareUrl="http://x/agents/r1" ruleCount={42} />)
    fireEvent.click(screen.getByRole('tab', { name: /Component Scores/ }))
    expect(screen.getByText(/never fused/)).toBeTruthy()
    const links = screen.getAllByRole('link', { name: 'View report →' })
    expect(links[0].getAttribute('href')).toBe('/items/a--b--skill-pdf-extract')
  })

  it('renders the README badge band with the agent badge path', () => {
    const { container } = render(
      <AgentReport run={RED} shareUrl="http://x/agents/r1" ruleCount={42} />
    )
    expect(screen.getByText('Embed the badge in your README')).toBeTruthy()
    const code = container.querySelector('.badge-band .bt-body code')?.textContent ?? ''
    expect(code).toContain('badge/agent/r1/10.svg')
  })

  it('unlisted report adds right-of-reply and the redacted transcript', () => {
    const unlisted = {
      ...RED,
      visibility: 'unlisted',
      findings: [
        finding({
          id: 'f1',
          test_id: 'AS-06',
          evidence_excerpt: {
            file: 'transcript:AS-06',
            lang: null,
            truncated: false,
            lines: [{ line_no: 1, text: "write_note(args={'note': 'OL-AS06-...'} )", hit: true }],
          },
        }),
      ],
    } as unknown as AgentScanReportDetail
    render(
      <AgentReport
        run={unlisted}
        shareUrl="http://x/agents/r/tok"
        ruleCount={42}
        unlisted
        token="tok"
      />
    )
    expect(screen.getByRole('button', { name: 'Add a public reply' })).toBeTruthy()
    fireEvent.click(screen.getByRole('tab', { name: /Findings/ }))
    expect(screen.getByText('transcript:AS-06')).toBeTruthy()
    expect(screen.getByText(/Confirmed exfiltration/)).toBeTruthy()
    expect(screen.queryByText('transcript withheld on the public report')).toBeNull()
  })
})
