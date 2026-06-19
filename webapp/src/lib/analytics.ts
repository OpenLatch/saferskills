import posthog from 'posthog-js'

type EventMap = {
  homepage_search_submitted: { query_length_bucket: '<10' | '<25' | '<50' | '>=50' }
  // Dual-mode scan submit from the /scan console. Closed-enum only —
  // never the URL, filename, bytes, or share_token (telemetry.md). The backend
  // emits the authoritative `scan_submitted`; this is the FE intent signal.
  homepage_scan_submitted: {
    artifact_source: 'github' | 'upload'
    visibility: 'public' | 'unlisted'
  }
  // Homepage audit-panel affordance: the user picked a file / hit ↵ and is being
  // navigated to /scan to confirm (the panel never submits inline).
  homepage_scan_panel_started: {
    artifact_source: 'github' | 'upload'
    visibility: 'public' | 'unlisted'
  }
  catalog_filter_changed: {
    filter_type: 'type' | 'agent' | 'score_range' | 'scan_tier' | 'recency'
    action: 'add' | 'remove'
  }
  catalog_item_clicked: {
    tier: 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'
    kind: 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'
  }
  scan_report_subscore_expanded: {
    sub_score: 'security' | 'supply_chain' | 'maintenance' | 'transparency' | 'community'
  }
  scan_report_install_copied: { command_type: 'npx' | 'web' | 'zip' }
  scan_report_badge_copied: { format: 'markdown' | 'html' | 'preview' }
  scan_report_capability_filtered: {
    kind: 'all' | 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'
  }
  scan_report_capability_expanded: {
    kind: 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'
  }
  // A finding card was expanded on a scan report. `rule_id` is a permitted
  // closed-enum value (the active rubric — a bounded set) per telemetry.md.
  scan_report_finding_expanded: {
    rule_id: string
  }
  // Multi-file upload report — a file tab was selected. Closed-enum kind only;
  // NEVER the filename, slug, content hash, or token (telemetry.md).
  scan_report_file_selected: {
    kind: 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'
  }
  item_detail_chart_explored: { interaction: 'hover' | 'click_point' }
  // Methodology rules → CSV export. Bucketed count of the exported (currently
  // visible) rules; never a rule_id list or any raw count (telemetry.md).
  rule_csv_exported: { count_bucket: '0' | '1' | '2-5' | '6-20' | '21+' }
  // /methodology mode control — which scan-mode catalog a reader switches to.
  // Closed-enum only; no PII (telemetry.md, rule_* prefix).
  rule_methodology_tab_selected: { tab: 'capability' | 'agent' }
  // Unlisted (capability-URL) manage-bar actions. Closed-enum action
  // only; NEVER the share_token, slug, filename, or any path content (telemetry.md).
  unlisted_manage_action: { action: 'copy_link' | 'promote' | 'delete' }
  // A bootstrap prompt was minted + copied (homepage card 02 / /scan
  // agent pane / platform picker). Closed-enum only; NEVER the run_id, the
  // one-time token, or any prompt content (telemetry.md).
  agent_scan_prompt_minted: {
    surface: 'homepage' | 'scan' | 'picker'
    visibility: 'public' | 'unlisted'
  }
  // Agent Report surface interactions. Closed-enum only; NEVER the
  // share_token, agent name, runtime, or any transcript content (telemetry.md).
  agent_report_tab_selected: { tab: 'report' | 'findings' | 'component' }
  agent_report_shared: Record<string, never>
  agent_report_exported: Record<string, never>
  agent_report_reply_submitted: Record<string, never>
}

export type AnalyticsEvent = keyof EventMap
export type AnalyticsProps<E extends AnalyticsEvent> = EventMap[E]

export function track<E extends AnalyticsEvent>(event: E, props: AnalyticsProps<E>): void {
  if (typeof window === 'undefined') return
  posthog.capture(event, props)
}
