import type { TerminalLine } from '@ui/components/molecules/ScanTerminal'

/** Minimal shape of a streamed scan-progress event (cf. useScanProgress). */
export interface FeedEvent {
  stage: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  payload?: Record<string, unknown>
}

/** Human label for each known stage key; unknown keys are title-cased. */
const STAGE_LABEL: Record<string, string> = {
  fetch: 'Fetch',
  index: 'Index',
  security: 'Security',
  supply_chain: 'Supply chain',
  maintenance: 'Maintenance',
  transparency: 'Transparency',
  community: 'Community',
  score: 'Score',
  sign: 'Score & sign',
}

function titleize(key: string): string {
  return key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

function stageLabel(key: string): string {
  return STAGE_LABEL[key] ?? titleize(key)
}

/**
 * Turn a scanned-repo target into a host-relative display string + ref.
 * `https://github.com/anthropics/skills/tree/main` → `{ host: "github.com/anthropics/skills", ref: "main" }`.
 * Non-URL targets (upload filenames) pass through as the host.
 */
export function formatTarget(target?: string): { host: string; ref?: string } {
  if (!target) return { host: '—' }
  try {
    const u = new URL(target)
    const parts = u.pathname.split('/').filter(Boolean)
    if (parts.length < 2) return { host: `${u.host}${u.pathname}`.replace(/\/$/, '') }
    const ref = parts[2] === 'tree' || parts[2] === 'blob' ? parts[3] : undefined
    return { host: `${u.host}/${parts[0]}/${parts[1]}`, ref }
  } catch {
    // Not a URL (e.g. an uploaded filename) — show as-is.
    return { host: target }
  }
}

/** Keep file paths short in the terminal — drop a leading slash, cap length. */
function shortPath(p: string): string {
  const clean = p.replace(/^\//, '')
  return clean.length > 48 ? `…${clean.slice(-47)}` : clean
}

/**
 * Reduce the live SSE event stream into ordered terminal lines for `ScanTerminal`.
 *
 * Lines are derived purely from real events, so the terminal stays in lock-step
 * with stage progress: a per-detector event (carrying `rule_id`) renders a
 * detector line within its stage; a stage-level event renders a stage start /
 * complete line. Repeated progress ticks for the same (stage, status, rule) are
 * de-duplicated so percent-tick spam never reaches the screen.
 */
export function buildTerminalLines(events: FeedEvent[], target?: string): TerminalLine[] {
  const { host } = formatTarget(target)
  const lines: TerminalLine[] = [
    {
      id: 'cmd',
      kind: 'cmd',
      segments: [{ text: 'saferskills scan ', tone: 'cmd' }, { text: host }],
    },
  ]
  const seen = new Set<string>()

  for (const ev of events) {
    const ruleId = typeof ev.payload?.rule_id === 'string' ? ev.payload.rule_id : undefined
    const evTarget = typeof ev.payload?.target === 'string' ? ev.payload.target : undefined

    if (ruleId) {
      const key = `rule:${ruleId}:${ev.status}`
      if (seen.has(key)) continue
      seen.add(key)
      if (ev.status === 'running') {
        lines.push({
          id: key,
          kind: 'run',
          segments: [
            { text: ruleId, tone: 'rule' },
            ...(evTarget
              ? [{ text: '  ' }, { text: shortPath(evTarget), tone: 'path' as const }]
              : []),
          ],
        })
      } else if (ev.status === 'failed') {
        lines.push({
          id: key,
          kind: 'warn',
          segments: [{ text: ruleId, tone: 'rule' }, { text: '  flagged' }],
        })
      } else if (ev.status === 'completed') {
        lines.push({ id: key, kind: 'ok', segments: [{ text: ruleId, tone: 'rule' }] })
      }
      continue
    }

    if (ev.stage === 'done') {
      if (ev.status === 'completed' && !seen.has('done')) {
        seen.add('done')
        lines.push({
          id: 'done',
          kind: 'done',
          segments: [{ text: 'scan complete — loading report…' }],
        })
      }
      continue
    }

    const key = `stage:${ev.stage}:${ev.status}`
    if (seen.has(key)) continue
    seen.add(key)
    const label = stageLabel(ev.stage)
    if (ev.status === 'running') {
      lines.push({ id: key, kind: 'run', segments: [{ text: label }] })
    } else if (ev.status === 'completed') {
      lines.push({ id: key, kind: 'ok', segments: [{ text: `${label} complete` }] })
    } else if (ev.status === 'failed') {
      lines.push({ id: key, kind: 'warn', segments: [{ text: `${label} failed` }] })
    }
  }

  return lines
}
