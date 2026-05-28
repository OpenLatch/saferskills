import { useState } from 'react'
import CopyButton from '../atoms/CopyButton'

interface Agent {
  id: string
  name: string
  glyph: string
  installPath: string
  configPath?: string
  preview?: string[]
}

interface Props {
  agents?: Agent[]
  defaultAgent?: string
  scanSlug?: string
}

const DEFAULT_AGENTS: Agent[] = [
  { id: 'claude-code', name: 'Claude Code', glyph: 'CC', installPath: 'claude-code', configPath: '~/.config/claude/skills/' },
  { id: 'cursor', name: 'Cursor', glyph: 'C', installPath: 'cursor', configPath: '~/.cursor/extensions/' },
  { id: 'codex-cli', name: 'Codex CLI', glyph: '><', installPath: 'codex-cli', configPath: '~/.codex/skills/' },
  { id: 'copilot', name: 'Copilot', glyph: 'GH', installPath: 'copilot', configPath: '~/.copilot/extensions/' },
  { id: 'windsurf', name: 'Windsurf', glyph: 'W', installPath: 'windsurf', configPath: '~/.windsurf/skills/' },
  { id: 'cline', name: 'Cline', glyph: 'CL', installPath: 'cline', configPath: '~/.cline/skills/' },
  { id: 'gemini-cli', name: 'Gemini CLI', glyph: 'G', installPath: 'gemini-cli', configPath: '~/.gemini/skills/' },
  { id: 'openclaw', name: 'OpenClaw', glyph: 'OC', installPath: 'openclaw', configPath: '~/.openclaw/extensions/' },
]

/**
 * 8-agent tab strip + terminal output. Each tab swaps the install command +
 * the per-agent terminal preview (mono font, syntax-coded). Copy-to-clipboard
 * button copies the current agent's install command.
 *
 * Cursor blink animation honors `prefers-reduced-motion: reduce`.
 */
export default function InstallTabs({
  agents = DEFAULT_AGENTS,
  defaultAgent,
  scanSlug = 'github-mcp',
}: Props) {
  const [active, setActive] = useState(defaultAgent ?? agents[0].id)
  const agent = agents.find((a) => a.id === active) ?? agents[0]
  const command = `npx saferskills install ${scanSlug} --agent ${agent.installPath}`

  return (
    <div>
      <div className="tabs" role="tablist" aria-label="Choose your agent">
        {agents.map((a) => (
          <button
            type="button"
            key={a.id}
            role="tab"
            aria-selected={a.id === active}
            aria-controls={`install-pane-${a.id}`}
            className={`tab-btn ${a.id === active ? 'active' : ''}`.trim()}
            onClick={() => setActive(a.id)}
          >
            <span className="tg" aria-hidden="true">{a.glyph}</span>
            <span className="tn">{a.name}</span>
          </button>
        ))}
      </div>
      <div
        className="term"
        role="tabpanel"
        id={`install-pane-${agent.id}`}
        aria-label={`${agent.name} install preview`}
      >
        <div className="term-head">
          <span className="lights" aria-hidden="true">
            <span /><span /><span />
          </span>
          <span className="who">~/projects · {agent.name}</span>
          <CopyButton value={command} label="Copy" variant="dark" size="sm" />
        </div>
        <div className="term-body">
          <div className="cmd">$ npx saferskills install <span className="arg">{scanSlug}</span> --agent <span className="arg">{agent.installPath}</span></div>
          <div className="info">→ Resolving package…</div>
          <div className="info">→ Fetching scan report…</div>
          <div className="ok">✓ Score 87/100 (green) — methodology open source</div>
          <div className="info">→ Installing into <span className="path">{agent.configPath}</span></div>
          <div className="done">✓ Ready. Restart {agent.name} to load.<span className="cursor-blink" /></div>
        </div>
      </div>
    </div>
  )
}
