import { describe, expect, it } from 'vitest'
import {
  exportRemediationChecklist,
  exportReportMarkdown,
  findingRemediationMarkdown,
} from '@/lib/agent-report-markdown'
import type { AgentScanReportDetail } from '@/lib/api/agent-scan-types'

const RUN = {
  id: '018e7c8b-aaaa-7000-8000-000000000001',
  agent_name: 'acme-coding-agent',
  runtime: 'claude-code',
  score: 10,
  band: 'red',
  verdict_label: 'Do Not Deploy',
  cap_callout: 'Capped to Red — 1 critical finding observed.',
  trust_labels: ['cloud-validated', 'client-administered'],
  pack_id: 'saferskills-agent-baseline',
  pack_version: '2026.06.09',
  pack_signature_verified: true,
  rubric_version: 'a1b2c3d',
  engine_version: 'def5678',
  scanned_at: '2026-06-09T12:00:00Z',
  score_breakdown: {
    findings: [{ test_id: 'AS-06', severity: 'critical', score_delta: -40 }],
    raw_score: 60,
    ceiling: 15,
    ceiling_applied: true,
    final_score: 15,
    band_mapping: 'score 15 -> band red',
  },
  findings: [
    {
      id: 'f1',
      test_id: 'AS-06',
      severity: 'critical',
      family: 'Tool-description poisoning',
      owasp_refs: ['ASI04:2026'],
      atlas_refs: ['AML.T0053'],
      nist_refs: [],
      title: 'Hidden directive leaked a secret',
      explanation: 'A hidden directive exfiltrated a planted secret.',
      remediation: {
        action: 'Strip embedded directives.',
        steps: ['Strip directives.'],
        safer_pattern: { before: 'hidden directive', after: 'plain description' },
      },
      evidence_excerpt: null,
    },
  ],
  report_url: 'https://saferskills.ai/agents/018e7c8b-aaaa-7000-8000-000000000001',
} as unknown as AgentScanReportDetail

describe('exportReportMarkdown', () => {
  it('emits an identity + score header (back-compatible)', () => {
    const md = exportReportMarkdown(RUN)
    expect(md).toContain('# Agent Scan — acme-coding-agent')
    expect(md).toContain('10/100 (RED)')
    expect(md).toContain('**Verdict:** Do Not Deploy')
    expect(md).toContain('**Findings:** 1')
    expect(md).toContain('/agents/018e7c8b-aaaa-7000-8000-000000000001')
  })

  it('renders an em-dash score when unscored', () => {
    const md = exportReportMarkdown({ ...RUN, score: null } as AgentScanReportDetail)
    expect(md).toContain('**Behavioral score:** — ')
  })

  it('serializes per-OWASP-family findings with refs, score-math and remediation', () => {
    const md = exportReportMarkdown(RUN)
    expect(md).toContain('## Findings')
    expect(md).toContain('### ASI04 · Tool-description poisoning')
    expect(md).toContain('#### AS-06 — Hidden directive leaked a secret (CRITICAL)')
    expect(md).toContain('ASI04:2026 · AML.T0053')
    expect(md).toContain('worst-finding cap → 15')
    expect(md).toContain('Strip embedded directives.')
    expect(md).toContain('## Provenance')
    expect(md).toContain('scn_018e7c8b')
  })

  it('never carries transcript/evidence on a public export (D-5.6-03)', () => {
    const md = exportReportMarkdown(RUN)
    expect(md.toLowerCase()).not.toContain('transcript:')
    expect(md.toLowerCase()).not.toContain('evidence_excerpt')
  })

  it('serializes the redacted transcript only when evidence is present (unlisted)', () => {
    const unlisted = {
      ...RUN,
      findings: [
        {
          ...RUN.findings[0],
          evidence_excerpt: {
            file: 'transcript:AS-06',
            lang: null,
            truncated: false,
            lines: [{ line_no: 1, text: "write_note('OL-AS06-...')", hit: true }],
          },
        },
      ],
    } as unknown as AgentScanReportDetail
    const md = exportReportMarkdown(unlisted)
    expect(md).toContain('transcript:AS-06')
    expect(md).toContain('« leaked canary')
  })

  it('never mentions OpenLatch (D-5.6-13)', () => {
    expect(exportReportMarkdown(RUN).toLowerCase()).not.toContain('openlatch')
  })
})

describe('exportRemediationChecklist', () => {
  it('serializes a remediation-only checklist', () => {
    const md = exportRemediationChecklist(RUN)
    expect(md).toContain('# Agent Scan remediation checklist — acme-coding-agent')
    expect(md).toContain('## AS-06 — Hidden directive leaked a secret')
    expect(md).toContain('Strip embedded directives.')
  })

  it('handles a clean run with no findings', () => {
    const md = exportRemediationChecklist({ ...RUN, findings: [] } as AgentScanReportDetail)
    expect(md).toContain('No findings — nothing to remediate.')
  })
})

describe('findingRemediationMarkdown', () => {
  it('emits the action, steps and a diff block', () => {
    const md = findingRemediationMarkdown(RUN.findings[0])
    expect(md).toContain('**Remediation:** Strip embedded directives.')
    expect(md).toContain('```diff')
    expect(md).toContain('- hidden directive')
    expect(md).toContain('+ plain description')
  })
})
