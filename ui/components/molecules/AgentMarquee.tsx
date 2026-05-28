import { AGENT_LOGOS } from './agent-logos'

interface Agent {
  id: string
  name: string
  glyph?: string
}

interface Props {
  agents?: Agent[]
}

const DEFAULT_AGENTS: Agent[] = [
  { id: 'claude-code', name: 'Claude Code' },
  { id: 'cursor', name: 'Cursor' },
  { id: 'codex-cli', name: 'Codex CLI' },
  { id: 'copilot', name: 'GitHub Copilot' },
  { id: 'windsurf', name: 'Windsurf' },
  { id: 'cline', name: 'Cline' },
  { id: 'gemini-cli', name: 'Gemini CLI' },
  { id: 'openclaw', name: 'OpenClaw' },
]

/**
 * Number of times the agent list is repeated end-to-end inside the track.
 * The CSS keyframe translates by `-100/TRACK_COPIES%` per loop, so this
 * MUST stay in sync with `--marquee-copies` in components.css. We use 4
 * copies so the track is wider than any standard viewport (≥1920px) —
 * 2 copies leaves a visible gap on wide screens between loops.
 */
const TRACK_COPIES = 4

/**
 * Horizontal scrolling marquee of agent brand logos. 36s linear infinite,
 * pauses on hover (handled in components.css::.marquee). Mobile (<768px) +
 * reduced-motion short-circuit to a wrapping static list.
 *
 * Each chip renders a monochrome brand mark from `agent-logos.tsx`. The
 * agent's display name lives on `aria-label` for screen readers only —
 * the marquee is a visual "works with" strip, not a navigation row.
 * Agents missing a known logo fall back to the legacy initials chip.
 */
export default function AgentMarquee({ agents = DEFAULT_AGENTS }: Props) {
  const track = Array.from({ length: TRACK_COPIES }, () => agents).flat()
  return (
    <div className="marquee" aria-label="Supported agents">
      <div className="marquee-track">
        {track.map((agent, i) => {
          const Logo = AGENT_LOGOS[agent.id]
          return (
            <span
              className="agent-chip"
              key={`${agent.id}-${i}`}
              role="img"
              aria-label={agent.name}
              title={agent.name}
            >
              {Logo ? (
                <Logo className="gly" />
              ) : (
                <span className="gly gly-text" aria-hidden="true">
                  {agent.glyph ?? agent.name.slice(0, 2).toUpperCase()}
                </span>
              )}
            </span>
          )
        })}
      </div>
    </div>
  )
}
