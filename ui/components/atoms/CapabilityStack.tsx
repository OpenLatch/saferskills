/**
 * CapabilityStack — the per-kind capability count stack on a directory dossier
 * card. One stroke-icon + count per non-zero capability kind,
 * right-aligned on the score row, with a hover tooltip carrying the kind label
 * (mirrors the mockup `.caps-stack` / `.cap2` markup, including the
 * per-kind SVG glyphs). Driven by the summary `capability_tally`; renders
 * nothing when the agent has no assembled capabilities yet (the
 * `component_scores` builder is data-starved at launch — until it populates,
 * every tally is empty and the stack is silent). CSS is in
 * `page-agent-directory.css`.
 */

export interface CapabilityTally {
  skill: number
  hook: number
  mcp: number
  plugin: number
  rules: number
}

type CapKind = keyof CapabilityTally

// The locked mockup's stroke icons (24×24, stroked via CSS currentColor).
const ICON: Record<CapKind, React.ReactNode> = {
  skill: <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />,
  hook: (
    <>
      <circle cx="12" cy="5" r="3" />
      <line x1="12" y1="22" x2="12" y2="8" />
      <path d="M5 12H2a10 10 0 0 0 20 0h-3" />
    </>
  ),
  mcp: (
    <>
      <rect x="2" y="3" width="20" height="8" rx="2" />
      <rect x="2" y="13" width="20" height="8" rx="2" />
      <line x1="6" y1="7" x2="6.01" y2="7" />
      <line x1="6" y1="17" x2="6.01" y2="17" />
    </>
  ),
  plugin: (
    <>
      <path d="M9 8V3" />
      <path d="M15 8V3" />
      <path d="M6 8h12v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4z" />
      <path d="M12 17v4" />
    </>
  ),
  rules: (
    <>
      <path d="m3 8 2 2 4-4" />
      <path d="m3 17 2 2 4-4" />
      <line x1="13" y1="7" x2="21" y2="7" />
      <line x1="13" y1="17" x2="21" y2="17" />
    </>
  ),
}

const LABEL: Record<CapKind, string> = {
  skill: 'Skill',
  mcp: 'MCP',
  hook: 'Hook',
  plugin: 'Plugin',
  rules: 'Rules',
}
const ORDER: CapKind[] = ['mcp', 'skill', 'hook', 'plugin', 'rules']

export default function CapabilityStack({
  tally,
  className = '',
}: {
  tally: CapabilityTally
  className?: string
}) {
  const present = ORDER.filter((k) => (tally[k] ?? 0) > 0)
  if (present.length === 0) return null
  return (
    <span className={`caps-stack ${className}`.trim()}>
      {present.map((k) => (
        <span key={k} className="cap2">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            {ICON[k]}
          </svg>
          <b className="ct" aria-hidden="true">
            {tally[k]}
          </b>
          <span className="lbl" aria-hidden="true">
            {LABEL[k]}
          </span>
          <span className="sr-only">
            {tally[k]} {LABEL[k]}
          </span>
        </span>
      ))}
    </span>
  )
}
