/**
 * CapabilityStack — the per-kind capability count row on a directory dossier card
 * (I-5.6 §12.3). One glyph+count chip per non-zero capability kind. Driven by the
 * summary `capability_tally`; renders nothing when the agent has no assembled
 * capabilities yet (the I-5.5 `component_scores` builder is data-starved at launch
 * — until it populates, every tally is empty and the stack is silent). CSS
 * (`.caps-stack` / `.cap2`) is in `page-agent-directory.css`.
 */

export interface CapabilityTally {
  skill: number
  hook: number
  mcp: number
  plugin: number
  rules: number
}

type CapKind = keyof CapabilityTally

// Single-glyph affordance per kind (the directory cards are dense; the title
// attribute carries the full label for hover + a11y).
const GLYPH: Record<CapKind, string> = {
  skill: '◆',
  mcp: '⚙',
  hook: '⎇',
  plugin: '⧉',
  rules: '§',
}
const LABEL: Record<CapKind, string> = {
  skill: 'Skill',
  mcp: 'MCP server',
  hook: 'Hook',
  plugin: 'Plugin',
  rules: 'Rules',
}
const ORDER: CapKind[] = ['skill', 'mcp', 'hook', 'plugin', 'rules']

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
        <span key={k} className="cap2" title={`${tally[k]} ${LABEL[k]}`}>
          <span className="cap2-glyph" aria-hidden="true">
            {GLYPH[k]}
          </span>
          <span className="cap2-n">{tally[k]}</span>
          <span className="sr-only">
            {tally[k]} {LABEL[k]}
          </span>
        </span>
      ))}
    </span>
  )
}
