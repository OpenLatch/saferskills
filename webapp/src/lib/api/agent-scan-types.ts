/**
 * Hand-written wire types + runtime validator for the Agent Scan report DTO.
 *
 * The authoritative shape is `services/api/app/schemas/agent_scan.py`
 * (`AgentScanReportDetail` & friends, all `OrmBaseModel` → snake_case wire keys).
 * We hand-write it here because the generated agent Zod is a `z.unknown()`
 * placeholder (`webapp/src/generated/zod` — the generator emits a stub for the
 * agent schema), so the generated types give us no compile- or run-time guard.
 * Keep this in lockstep with the Python DTO.
 */

export type AgentBand = 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'
export type AgentRunStatus =
  | 'created'
  | 'fetched'
  | 'submitted'
  | 'graded'
  | 'published'
  | 'aborted'
export type AgentSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical'
export type AgentVerdict = 'vulnerable' | 'not_observed' | 'n_a' | 'error'
export type AgentVisibility = 'public' | 'unlisted'
export type AgentConfidence = 'high' | 'medium' | 'low'
export type AgentCapabilityKind = 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'

/** Every test the pack applied — the Report-tab (proof-of-tests) rows. `title` is
 * the check description (there is no `description` field). */
export interface AgentCheckRow {
  test_id: string
  family: string
  title: string
  verdict: AgentVerdict
  severity: AgentSeverity
}

export interface AgentSaferPattern {
  before: string
  after: string
}

export interface AgentRemediation {
  action: string
  steps: string[] | null
  safer_pattern: AgentSaferPattern | null
}

/** A redacted transcript window for ONE finding (token route only; `null` on the
 * public route). Flat line-window, NOT role-tagged turns; `hit:true` marks the
 * line that leaked the canary. */
export interface AgentEvidenceExcerpt {
  file: string
  lang: string | null
  truncated: boolean
  lines: { line_no: number; text: string; hit: boolean }[]
}

export interface AgentFindingRow {
  id: string
  test_id: string
  severity: AgentSeverity
  verdict: AgentVerdict
  family: string
  owasp_refs: string[]
  atlas_refs: string[]
  nist_refs: string[]
  score_delta: number
  detection_rule: string
  /** Slot name only — never a raw canary value. */
  leaked_canary_slot: string | null
  title: string
  explanation: string
  severity_rationale: string | null
  category_label: string | null
  remediation: AgentRemediation
  /** Token-route-only; the public route guarantees `null` (route-driven split). */
  evidence_excerpt: AgentEvidenceExcerpt | null
}

/** Context-only capability score — never fused into the behavioral score. Shape
 * `{kind,name,path,score,tier,slug}`; the all-clear/needs-review chip derives from
 * `tier`, the "View report →" deep-links to `/items/<slug>`. */
export interface AgentComponentScoreRow {
  kind: AgentCapabilityKind
  name: string
  path: string | null
  score: number
  tier: AgentBand
  slug: string
}

export interface AgentScoreBreakdown {
  findings: { test_id: string; severity: AgentSeverity; score_delta: number }[]
  raw_score: number
  ceiling: number | null
  ceiling_applied: boolean
  final_score: number
  band_mapping: string
}

export interface AgentScanReportDetail {
  id: string
  status: AgentRunStatus
  agent_name: string
  runtime: string
  score: number | null
  band: AgentBand
  verdict_label: string | null
  cap_callout: string | null
  confidence: AgentConfidence | null
  score_breakdown: AgentScoreBreakdown | null
  trust_labels: string[]
  pack_id: string
  pack_version: string
  pack_signature_verified: boolean | null
  capabilities_present: string[]
  capabilities_absent: string[]
  family_tally: Record<string, number>
  checks: AgentCheckRow[]
  findings: AgentFindingRow[]
  component_scores: AgentComponentScoreRow[]
  /** Unlisted runs only: every Component-Scores row deep-links here (the unlisted
   * component scan_run's `/scans/r/<token>` report) instead of `/items/<slug>`,
   * whose shadow items 404 on the public catalog. Null for public runs. */
  component_report_url: string | null
  visibility: AgentVisibility
  expires_at: string | null
  /** Token route only; never logged. */
  share_url: string | null
  report_url: string | null
  rubric_version: string
  engine_version: string
  latency_ms: number
  scanned_at: string | null
  /** Capability-token holder's ≤500-char public right-of-reply (read-only on the
   * report); null when none attached. */
  vendor_reply: string | null
  vendor_reply_at: string | null
}

// ── Directory list summary + aggregate stats ──────────

/** Directory sort keys: latest-first default + score asc/desc. */
export type AgentSort = 'newest' | 'score_asc' | 'score_desc'

export interface AgentFindingsSummary {
  critical: number
  high: number
  info: number
  total: number
}

export interface AgentCapabilityTally {
  skill: number
  hook: number
  mcp: number
  plugin: number
  rules: number
}

/** One `/agents` directory dossier row (a public, graded agent run). */
export interface AgentScanSummary {
  id: string
  agent_name: string
  runtime: string
  score: number | null
  band: AgentBand
  visibility: 'public'
  report_url: string | null
  scanned_at: string | null
  capability_tally: AgentCapabilityTally
  findings_summary: AgentFindingsSummary
  trust_tier: string | null
}

export interface AgentScanListEnvelope {
  data: AgentScanSummary[]
  total_count: number
  page: number
  page_size: number
  total_pages: number
}

export interface AgentBandShare {
  pct: number
  count: number
}

export interface AgentBandDistribution {
  red: AgentBandShare
  orange: AgentBandShare
  yellow: AgentBandShare
  green: AgentBandShare
}

export interface AgentAggregateStats {
  corpus_count: number
  gate_target: number
  gate_met: boolean
  /** Null until the corpus reaches the gate — the frontend blanks the stat to "—". */
  pct_with_critical: number | null
  band_distribution: AgentBandDistribution
  window_label: string
}

const STATUSES: ReadonlySet<string> = new Set([
  'created',
  'fetched',
  'submitted',
  'graded',
  'published',
  'aborted',
])
const BANDS: ReadonlySet<string> = new Set(['green', 'yellow', 'orange', 'red', 'unscoped'])

/**
 * Minimal runtime validator: confirms the handful of fields the report shell hard
 * depends on are present + well-typed (the generated Zod can't, being a stub). A
 * malformed payload returns `null` so the route can generic-404 rather than throw a
 * cryptic render error. Not a full schema check — the backend Pydantic round-trip
 * (`tests/agent_scan/test_fixture.py`) is the authoritative shape guard.
 */
export function asAgentScanReportDetail(value: unknown): AgentScanReportDetail | null {
  if (typeof value !== 'object' || value === null) return null
  const v = value as Record<string, unknown>
  if (typeof v.id !== 'string') return null
  if (typeof v.status !== 'string' || !STATUSES.has(v.status)) return null
  if (typeof v.band !== 'string' || !BANDS.has(v.band)) return null
  if (typeof v.agent_name !== 'string') return null
  if (!Array.isArray(v.checks) || !Array.isArray(v.findings)) return null
  if (v.visibility !== 'public' && v.visibility !== 'unlisted') return null
  return value as AgentScanReportDetail
}

/** Pre-grade statuses render the polling "auditing…" board, not the report. */
export function isPreGrade(status: AgentRunStatus): boolean {
  return status === 'created' || status === 'fetched' || status === 'submitted'
}

/** Statuses that render a report. `aborted` renders neither (generic 404). */
export function isReportable(status: AgentRunStatus): boolean {
  return status === 'graded' || status === 'published'
}
