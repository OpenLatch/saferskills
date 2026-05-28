import { useState } from 'react'
import { flashToast } from '../atoms/Toast'

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
  { id: 'claude-code', name: 'Claude Code', glyph: 'CC', installPath: 'claude-code', configPath: '~/.claude/settings.json' },
  { id: 'cursor', name: 'Cursor', glyph: 'Cu', installPath: 'cursor', configPath: '~/.cursor/mcp.json' },
  { id: 'codex-cli', name: 'Codex CLI', glyph: 'Cx', installPath: 'codex-cli', configPath: '~/.codex/skills/' },
  { id: 'copilot', name: 'GH Copilot', glyph: 'Co', installPath: 'copilot', configPath: '~/.github/copilot/' },
  { id: 'windsurf', name: 'Windsurf', glyph: 'Wd', installPath: 'windsurf', configPath: '~/.windsurf/' },
  { id: 'cline', name: 'Cline', glyph: 'Cl', installPath: 'cline', configPath: '~/.cline/skills/' },
  { id: 'gemini-cli', name: 'Gemini CLI', glyph: 'Gm', installPath: 'gemini-cli', configPath: '~/.gemini/config/' },
  { id: 'openclaw', name: 'OpenClaw', glyph: 'OC', installPath: 'openclaw', configPath: 'openclaw.json' },
]

/**
 * Install demo terminal (macOS-window + sidebar agent picker), Phase A2
 * rewrite per the canonical hi-fi `iw-window` vocabulary.
 *
 * Structure:
 *   .iw-window
 *     .iw-chrome  — mac-traffic + .iw-title (centered) + .copy-slot > .mt-copy
 *     .iw-grid
 *       .iw-side  — .side-head + N × <button.iw-row> (agent picker, role=tablist)
 *       .iw-main  — .iw-bread + .mt-body (terminal output)
 *
 * The copy button is inlined as `.mt-copy` (not the generic CopyButton atom)
 * to honor the mockup's slightly different chrome silhouette + SVG icon. The
 * shared Toast atom still flashes the confirmation per Phase A1 convention.
 */
export default function InstallTabs({
  agents = DEFAULT_AGENTS,
  defaultAgent,
  scanSlug = 'github-mcp',
}: Props) {
  const [active, setActive] = useState(defaultAgent ?? agents[0].id)
  const agent = agents.find((a) => a.id === active) ?? agents[0]
  const command = `npx saferskills install ${scanSlug} --to ${agent.installPath}`
  const installDir = agent.configPath ?? `~/.${agent.id}/skills/`

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(command)
      flashToast('Copied to clipboard')
    } catch {
      flashToast('Copy failed — please copy manually')
    }
  }

  return (
    <div className="iw-window">
      <div className="iw-chrome">
        <span className="mac-traffic" aria-hidden="true">
          <span className="l-r" />
          <span className="l-y" />
          <span className="l-g" />
        </span>
        <div className="iw-title">
          <span>saferskills install</span>
          <span className="iw-title-sep">—</span>
          <span className="iw-title-agent">{agent.name}</span>
        </div>
        <div className="copy-slot">
          <button
            type="button"
            className="mt-copy"
            onClick={onCopy}
            aria-label={`Copy command: ${command}`}
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2.2}
              aria-hidden="true"
            >
              <rect x="8" y="8" width="13" height="13" rx="2" />
              <path d="M5 16V5a2 2 0 0 1 2-2h11" />
            </svg>
            Copy command
          </button>
        </div>
      </div>
      <div className="iw-grid">
        <div className="iw-side" role="tablist" aria-label="Choose an agent">
          <div className="side-head">AGENTS · {agents.length}</div>
          {agents.map((a) => (
            <button
              type="button"
              key={a.id}
              role="tab"
              aria-selected={a.id === active}
              aria-controls={`install-pane-${a.id}`}
              className={`iw-row ${a.id === active ? 'active' : ''}`.trim()}
              data-id={a.id}
              onClick={() => setActive(a.id)}
            >
              <span className="iw-mono" aria-hidden="true">{a.glyph}</span>
              <span className="iw-name">{a.name}</span>
              <span className="iw-sub">--to {a.installPath}</span>
            </button>
          ))}
        </div>
        <div
          className="iw-main"
          role="tabpanel"
          id={`install-pane-${agent.id}`}
          aria-label={`${agent.name} install preview`}
        >
          <div className="iw-bread">
            <span className="crumb">~</span>
            <span className="sep">/</span>
            <span className="crumb">saferskills</span>
            <span className="sep">/</span>
            <span className="crumb">install</span>
            <span className="sep">/</span>
            <span className="crumb cur">{agent.id}</span>
          </div>
          <div className="mt-body">
            <div className="ln">
              <span className="prompt-sigil">$</span>{' '}
              <span className="cmd">npx</span>{' '}
              <span className="cmd-rest">saferskills install {scanSlug}</span>{' '}
              <span className="arg">--to {agent.installPath}</span>
            </div>
            <div className="ln">
              <span className="ok">✓</span> Verifying score:{' '}
              <span className="num">87/100</span> <span className="dim">(</span>
              <span className="green-tag">Green</span>
              <span className="dim">)</span>
            </div>
            <div className="ln">
              <span className="ok">✓</span> Installed to <span className="path">{installDir}{scanSlug}/</span>
            </div>
            <div className="ln">
              <span className="ok">✓</span> Updated <span className="file">{installDir}</span>
            </div>
            <div className="ln done-line">
              Done. <span className="green-tag">{scanSlug}</span> is available in {agent.name}.
              <span className="caret" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
