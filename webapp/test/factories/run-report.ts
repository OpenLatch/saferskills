import type { CapabilityRow, Finding, ScanRunReportDetail } from '@/lib/api/scans'

/** Stable builders for the run-report DTO — upload + unlisted fixtures (D-UP-33).
 * Hand-rolled (not snapshot) so tests stay resilient to unrelated field churn. */

export function makeFinding(over: Partial<Finding> = {}): Finding {
  return {
    id: 'f-1',
    rule_id: 'SS-SKILL-INJECT-FENCED-RUN-01',
    severity: 'medium',
    sub_score: 'security',
    penalty: 8,
    status_at_scan: 'active',
    file_path: 'SKILL.md',
    line_start: 12,
    line_end: 12,
    matched_content_sha256: 'abc123',
    remediation_link: 'https://saferskills.ai/methodology#SS-SKILL-INJECT-FENCED-RUN-01',
    rubric_version: 'eae45a8',
    ...over,
  }
}

export function makeCapability(over: Partial<CapabilityRow> = {}): CapabilityRow {
  return {
    kind: 'skill',
    name: 'my-skill',
    component_path: null,
    aggregate_score: 91,
    tier: 'green',
    scan_id: 'scan-1',
    catalog_slug: 'upload--a7b3c2d1--skill-my-skill',
    sub_scores: {
      security: 91,
      supply_chain: 88,
      maintenance: 90,
      transparency: 95,
      community: 80,
    },
    findings_summary: { critical: 0, high: 0, medium: 1, low: 1, info: 0, total: 2 },
    findings: [makeFinding()],
    ...over,
  }
}

/** A PUBLIC single-capability UPLOAD run (github_url null) — mockup 3. */
export function makeUploadRun(over: Partial<ScanRunReportDetail> = {}): ScanRunReportDetail {
  return {
    id: '11111111-2222-3333-4444-555555555555',
    github_url: null,
    repo_aggregate_score: 91,
    repo_tier: 'green',
    kind_tally: { skill: 1 },
    capability_count: 1,
    capabilities: [makeCapability()],
    scanned_at: '2026-06-01T14:32:00Z',
    rubric_version: 'eae45a8',
    engine_version: 'eae45a8',
    latency_ms: 27000,
    source: 'submission',
    status: 'completed',
    ref_sha: null,
    visibility: 'public',
    source_kind: 'upload',
    artifact_sha256: 'a7b3c2d1e5f4a7b3c2d1e5f4a7b3c2d1e5f4a7b3c2d1e5f4a7b3c2d1e5f4e5f4',
    uploaded_filename: 'my-skill.zip',
    expires_at: null,
    share_url: null,
    manifest: { path: 'SKILL.md', content: '# my-skill\n\nDoes a thing.', bytes: 2150 },
    download: { scan_id: 'scan-1', byte_size: 2400 },
    ...over,
  }
}

/** A PUBLIC multi-file UPLOAD run (3 loose files fanned to 3 capabilities, each
 * with its own manifest + download) — the per-file tabs report (I-3.5). */
export function makeMultiFileUploadRun(
  over: Partial<ScanRunReportDetail> = {}
): ScanRunReportDetail {
  return makeUploadRun({
    capability_count: 3,
    repo_aggregate_score: 74,
    repo_tier: 'yellow',
    kind_tally: { skill: 1, hook: 1, mcp_server: 1 },
    uploaded_filename: '3 files',
    capabilities: [
      makeCapability({
        name: 'prompt',
        kind: 'skill',
        aggregate_score: 91,
        tier: 'green',
        scan_id: 'mf-1',
        component_path: 'prompt.md',
        catalog_slug: 'upload--a7b3c2d1--skill-prompt',
        manifest: { path: 'prompt.md', content: '# Prompt\nbody', bytes: 18 },
        download: { scan_id: 'mf-1', byte_size: 18 },
        content_hash: '1111aaaa2222bbbb3333cccc4444dddd5555eeee6666ffff7777000088889999',
      }),
      makeCapability({
        name: 'install',
        kind: 'hook',
        aggregate_score: 52,
        tier: 'orange',
        scan_id: 'mf-2',
        component_path: 'install.sh',
        catalog_slug: 'upload--a7b3c2d1--hook-install',
        manifest: { path: 'install.sh', content: '#!/bin/sh\necho hi', bytes: 17 },
        download: { scan_id: 'mf-2', byte_size: 17 },
        content_hash: 'aaaa1111bbbb2222cccc3333dddd4444eeee5555ffff6666000077778888beef',
      }),
      makeCapability({
        name: 'server',
        kind: 'mcp_server',
        aggregate_score: 80,
        tier: 'green',
        scan_id: 'mf-3',
        component_path: 'server.json',
        catalog_slug: 'upload--a7b3c2d1--mcp-server-server',
        manifest: { path: 'server.json', content: '{"name":"srv"}', bytes: 14 },
        download: { scan_id: 'mf-3', byte_size: 14 },
      }),
    ],
    ...over,
  })
}

/** An UNLISTED single-capability upload run — mockup 4. */
export function makeUnlistedRun(over: Partial<ScanRunReportDetail> = {}): ScanRunReportDetail {
  return makeUploadRun({
    visibility: 'unlisted',
    expires_at: '2026-08-30T14:32:00Z',
    share_url: 'https://saferskills.ai/scans/r/8f3a2c1d9e',
    ...over,
  })
}

/** An UNLISTED multi-capability GitHub run — mockup 6 (cap-list body). */
export function makeUnlistedGithubRun(
  over: Partial<ScanRunReportDetail> = {}
): ScanRunReportDetail {
  return {
    ...makeUploadRun(),
    github_url: 'https://github.com/acme/devtools-agent-kit',
    source_kind: 'github',
    uploaded_filename: null,
    artifact_sha256: null,
    manifest: null,
    download: null,
    capability_count: 2,
    kind_tally: { skill: 1, hook: 1 },
    capabilities: [
      makeCapability({
        name: 'pdf-extract',
        scan_id: 's1',
        catalog_slug: 'acme--kit--skill-pdf-extract',
      }),
      makeCapability({
        kind: 'hook',
        name: 'pre-commit-guard',
        scan_id: 's2',
        catalog_slug: 'acme--kit--hook-pre-commit-guard',
      }),
    ],
    visibility: 'unlisted',
    expires_at: '2026-08-30T14:32:00Z',
    share_url: 'https://saferskills.ai/scans/r/9f2e4b7a1c',
    ...over,
  }
}
