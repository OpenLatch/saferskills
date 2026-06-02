import posthog from 'posthog-js'

type EventMap = {
  homepage_search_submitted: { query_length_bucket: '<10' | '<25' | '<50' | '>=50' }
  homepage_scan_submitted: { url_domain_class: 'github' | 'other' }
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
  item_detail_chart_explored: { interaction: 'hover' | 'click_point' }
  // I-3.5 — unlisted (capability-URL) manage-bar actions. Closed-enum action
  // only; NEVER the share_token, slug, filename, or any path content (telemetry.md).
  unlisted_manage_action: { action: 'copy_link' | 'promote' | 'delete' }
}

export type AnalyticsEvent = keyof EventMap
export type AnalyticsProps<E extends AnalyticsEvent> = EventMap[E]

export function track<E extends AnalyticsEvent>(event: E, props: AnalyticsProps<E>): void {
  if (typeof window === 'undefined') return
  posthog.capture(event, props)
}
