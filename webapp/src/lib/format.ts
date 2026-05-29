/** Shared number formatting for display metrics. */

/** Thousands-separated integer string, e.g. `12847` → `"12,847"`. */
export function formatCount(n: number): string {
  return n.toLocaleString('en-US')
}

/** Latency in ms → compact seconds string, e.g. `30000` → `"30s"`, `1200` → `"1.2s"`. */
export function formatSeconds(ms: number): string {
  const s = ms / 1000
  const rounded = s >= 10 ? Math.round(s) : Math.round(s * 10) / 10
  return `${rounded}s`
}
