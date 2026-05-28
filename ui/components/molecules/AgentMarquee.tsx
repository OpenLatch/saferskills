interface Agent {
  id: string
  name: string
  glyph: string
}

interface Props {
  agents?: Agent[]
}

const DEFAULT_AGENTS: Agent[] = [
  { id: 'claude-code', name: 'Claude Code', glyph: 'CC' },
  { id: 'cursor', name: 'Cursor', glyph: 'C' },
  { id: 'codex-cli', name: 'Codex CLI', glyph: '><' },
  { id: 'copilot', name: 'GitHub Copilot', glyph: 'GH' },
  { id: 'windsurf', name: 'Windsurf', glyph: 'W' },
  { id: 'cline', name: 'Cline', glyph: 'CL' },
  { id: 'gemini-cli', name: 'Gemini CLI', glyph: 'G' },
  { id: 'openclaw', name: 'OpenClaw', glyph: 'OC' },
]

/**
 * Horizontal scrolling marquee of agent chips. 36s linear infinite, pauses on
 * hover (handled in components.css::.marquee). Mobile (<768px) + reduced-motion
 * short-circuit to a wrapping static list. Duplicated track so the animation
 * loops seamlessly.
 */
export default function AgentMarquee({ agents = DEFAULT_AGENTS }: Props) {
  const track = [...agents, ...agents]
  return (
    <div className="marquee" aria-label="Supported agents">
      <div className="marquee-track">
        {track.map((agent, i) => (
          <span className="agent-chip" key={`${agent.id}-${i}`}>
            <span className="gly" aria-hidden="true">{agent.glyph}</span>
            {agent.name}
          </span>
        ))}
      </div>
    </div>
  )
}
