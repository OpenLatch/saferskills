import { type ReactNode, useState } from 'react'
import { flashToast } from '../atoms/Toast'

interface Agent {
  id: string
  name: string
  glyph: string
  installPath: string
  configPath?: string
  preview?: string[]
}

type Verb = 'install' | 'scan' | 'list' | 'info'

interface VerbDef {
  id: Verb
  glyph: string
  label: string
}

interface Props {
  agents?: Agent[]
  defaultAgent?: string
  defaultVerb?: Verb
  scanSlug?: string
}

const DEFAULT_AGENTS: Agent[] = [
  { id: 'claude-code', name: 'Claude Code', glyph: 'CC', installPath: 'claude-code', configPath: '~/.claude/settings.json' },
  { id: 'cursor', name: 'Cursor', glyph: 'Cu', installPath: 'cursor', configPath: '~/.cursor/mcp.json' },
  { id: 'codex', name: 'Codex CLI', glyph: 'Cx', installPath: 'codex', configPath: '~/.codex/skills/' },
  { id: 'copilot', name: 'GH Copilot', glyph: 'Co', installPath: 'copilot', configPath: '~/.github/copilot/' },
  { id: 'windsurf', name: 'Windsurf', glyph: 'Wd', installPath: 'windsurf', configPath: '~/.windsurf/' },
  { id: 'cline', name: 'Cline', glyph: 'Cl', installPath: 'cline', configPath: '~/.cline/skills/' },
  { id: 'gemini', name: 'Gemini CLI', glyph: 'Gm', installPath: 'gemini', configPath: '~/.gemini/config/' },
  { id: 'openclaw', name: 'OpenClaw', glyph: 'OC', installPath: 'openclaw', configPath: 'openclaw.json' },
]

// Journey order is install-first (the section IS the install demo), per the
// homepage brief — the strip uses middot separators, not arrows, so it does
// not misread as a chronological sequence.
const VERBS: VerbDef[] = [
  { id: 'install', glyph: 'It', label: 'install' },
  { id: 'scan', glyph: 'Sc', label: 'scan' },
  { id: 'list', glyph: 'Ls', label: 'list' },
  { id: 'info', glyph: 'In', label: 'info' },
]

/** Two-line SaferSkills banner — the CLI prints this on stderr for every verb. */
function Banner() {
  return (
    <>
      <div className="ln">
        <span className="green-tag b">SaferSkills</span>
      </div>
      <div className="ln dim">v0.1.0 · An OpenLatch project</div>
    </>
  )
}

/** A heatmap square as the CLI renders before each category number. */
function Heat({ tone }: { tone: 'g' | 'y' | 'r' }) {
  return <span className={`hbox ${tone}`} aria-hidden="true" />
}

function CategoryRow({ name, tone, value }: { name: string; tone: 'g' | 'y' | 'r'; value: number }) {
  // 13-wide label column keeps the heat squares + numbers aligned (monospace).
  return (
    <div className="ln">
      {`  ${name}`.padEnd(16)}
      <Heat tone={tone} /> <span className={tone === 'r' ? 'red b' : tone === 'y' ? 'yellow b' : 'b'}>{value}</span>
    </div>
  )
}

const CATS_CLEAN = [
  { name: 'Security', tone: 'g' as const, value: 97 },
  { name: 'Supply chain', tone: 'g' as const, value: 100 },
  { name: 'Maintenance', tone: 'g' as const, value: 100 },
  { name: 'Transparency', tone: 'g' as const, value: 100 },
  { name: 'Community', tone: 'g' as const, value: 100 },
]

const CATS_FLAGGED = [
  { name: 'Security', tone: 'r' as const, value: 25 },
  { name: 'Supply chain', tone: 'g' as const, value: 100 },
  { name: 'Maintenance', tone: 'g' as const, value: 100 },
  { name: 'Transparency', tone: 'g' as const, value: 100 },
  { name: 'Community', tone: 'g' as const, value: 100 },
]

const WORST = [
  { dot: 'y' as const, tier: 'Yellow', score: 74, name: 'instrument-integration', sev: 'red', sevTxt: '3 high', tail: ' · 3 findings' },
  { dot: 'g' as const, tier: 'Green', score: 83, name: 'claude-api', sev: 'red', sevTxt: '1 high', tail: ' · 3 findings' },
  { dot: 'g' as const, tier: 'Green', score: 83, name: 'rescue', sev: 'yellow', sevTxt: '4 medium', tail: '' },
  { dot: 'g' as const, tier: 'Green', score: 91, name: 'babysit-pr', sev: 'red', sevTxt: '1 high', tail: ' · 1 findings' },
]

const LIST_ROWS = [
  { name: 'hooks', kind: 'Hook', agent: 'claude-code', score: '100', tier: 'Green', when: 'just now', path: '~/.claude/plugins/cache/…/posthog/1.1.31/hooks/hooks.json' },
  { name: 'settings', kind: 'Hook', agent: 'claude-code', score: '100', tier: 'Green', when: 'just now', path: '~/.claude/settings.json' },
  { name: 'node_repl', kind: 'MCP', agent: 'codex', score: '100', tier: 'Green', when: 'just now', path: '~/.codex/config.toml' },
  { name: 'posthog', kind: 'MCP', agent: 'claude-code', score: '100', tier: 'Green', when: 'just now', path: '~/.claude/plugins/cache/…/posthog/1.1.31/.mcp.json' },
  { name: 'code-simplifier', kind: 'Plugin', agent: 'claude-code', score: '100', tier: 'Green', when: 'just now', path: '~/.claude/plugins/cache/…/code-simplifier/1.0.0' },
  { name: 'github', kind: 'Plugin', agent: 'claude-code', score: '100', tier: 'Green', when: 'just now', path: '~/.claude/plugins/cache/…/github/unknown' },
  { name: 'security-guidance', kind: 'Plugin', agent: 'claude-code', score: '100', tier: 'Green', when: 'just now', path: '~/.claude/plugins/cache/…/security-guidance/2.0.3' },
  { name: 'adversarial-review', kind: 'Skill', agent: 'claude-code', score: '92', tier: 'Green', when: 'just now', path: '~/.claude/plugins/cache/…/codex/1.0.4/commands/adversarial-review.md' },
  { name: 'babysit-pr', kind: 'Skill', agent: 'claude-code', score: '91', tier: 'Green', when: 'just now', path: '~/.claude/skills/babysit-pr' },
  { name: 'claude-api', kind: 'Skill', agent: 'claude-code', score: '83', tier: 'Green', when: 'just now', path: '~/.claude/plugins/cache/…/skills/claude-api' },
  { name: 'canvas-design', kind: 'Skill', agent: 'claude-code', score: '100', tier: 'Green', when: 'just now', path: '~/.claude/plugins/cache/…/skills/canvas-design' },
  { name: 'creating-experiments', kind: 'Skill', agent: 'claude-code', score: '96', tier: 'Green', when: 'just now', path: '~/.claude/plugins/cache/…/posthog/1.1.31/skills/creating-experiments' },
  { name: 'instrument-integration', kind: 'Skill', agent: 'claude-code', score: '74', tier: 'Yellow', when: 'just now', path: '~/.claude/plugins/cache/…/posthog/1.1.31/skills/instrument-integration' },
]

const tierClass = (tier: string) => (tier === 'Yellow' ? 'yellow' : tier === 'Red' ? 'red' : 'green')

/**
 * Install demo terminal (macOS-window + agent sidebar + a verb journey strip).
 *
 * The left sidebar still picks the install target agent (unchanged); a new
 * horizontal journey strip at the top of the terminal body rotates the body
 * through the four real CLI verbs — install · scan · list · info — each
 * reproducing the CLI's actual output (banner, tier dots, category breakdown,
 * SS-… findings, the Report link). The terminal width + height stay constant
 * across verbs; long output (scan / list) scrolls inside the fixed body.
 *
 * Structure:
 *   .iw-window
 *     .iw-chrome  — mac-traffic + .iw-title (centered) + .copy-slot > .mt-copy
 *     .iw-grid
 *       .iw-side  — .side-head + N × <button.iw-row> (agent picker)
 *       .iw-main  — .iw-journey (verb tablist) + .iw-bread + .mt-body (tabpanel)
 */
export default function InstallTabs({
  agents = DEFAULT_AGENTS,
  defaultAgent,
  defaultVerb = 'install',
  scanSlug = 'github-mcp',
}: Props) {
  const [active, setActive] = useState(defaultAgent ?? agents[0].id)
  const [verb, setVerb] = useState<Verb>(defaultVerb)
  const agent = agents.find((a) => a.id === active) ?? agents[0]
  // Where the capability lands (a dir → append the slug; a file/URL target → as-is)
  // vs the config file the install touches. Keeps the transcript correct for every
  // agent path shape (dir, mcp.json, vscode:// URL).
  const installTarget = agent.installPath.endsWith('/')
    ? `${agent.installPath}${scanSlug}/`
    : agent.installPath
  const updatedFile = agent.configPath ?? `~/.${agent.id}/settings.json`

  // Per-verb command (what the Copy button copies) + chrome title + breadcrumb tail.
  const command: Record<Verb, string> = {
    install: `npx saferskills install ${scanSlug} --to ${agent.id}`,
    scan: 'npx saferskills scan',
    list: 'npx saferskills list',
    info: 'npx saferskills info instrument-integration',
  }
  const title: Record<Verb, ReactNode> = {
    install: (
      <>
        <span>saferskills install</span>
        <span className="iw-title-sep">—</span>
        <span className="iw-title-agent">{agent.name}</span>
      </>
    ),
    scan: (
      <>
        <span>saferskills scan</span>
        <span className="iw-title-sep">—</span>
        <span className="iw-title-agent">local audit</span>
      </>
    ),
    list: (
      <>
        <span>saferskills list</span>
        <span className="iw-title-sep">—</span>
        <span className="iw-title-agent">inventory</span>
      </>
    ),
    info: (
      <>
        <span>saferskills info</span>
        <span className="iw-title-sep">—</span>
        <span className="iw-title-agent">instrument-integration</span>
      </>
    ),
  }
  const breadTail: Record<Verb, ReactNode> = {
    install: (
      <>
        <span className="crumb">install</span>
        <span className="sep">/</span>
        <span className="crumb cur">{agent.id}</span>
      </>
    ),
    scan: <span className="crumb cur">scan</span>,
    list: <span className="crumb cur">list</span>,
    info: (
      <>
        <span className="crumb">info</span>
        <span className="sep">/</span>
        <span className="crumb cur">instrument-integration</span>
      </>
    ),
  }

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(command[verb])
      flashToast('Copied to clipboard')
    } catch {
      flashToast('Copy failed — please copy manually')
    }
  }

  // ── Per-verb terminal bodies ──────────────────────────────────────────────
  function installBody() {
    return (
      <>
        <div className="ln">
          <span className="prompt-sigil">$</span> <span className="cmd">npx</span>{' '}
          <span className="cmd-rest">saferskills install {scanSlug}</span>{' '}
          <span className="arg">--to {agent.id}</span>
        </div>
        <Banner />
        <div className="ln">&nbsp;</div>
        <div className="ln">
          <span className="b">{scanSlug}</span> <span className="green">●</span>{' '}
          <span className="green b">Green</span> <span className="num">87</span>
          <span className="dim">/100</span>
        </div>
        <div className="ln">
          <span className="ok">✓</span> Installed to <span className="path">{installTarget}</span>
        </div>
        <div className="ln">
          <span className="ok">✓</span> Updated <span className="file">{updatedFile}</span>
        </div>
        <div className="ln done-line">
          Done. <span className="green-tag">{scanSlug}</span> is available in {agent.name}.
          <span className="caret" />
        </div>
      </>
    )
  }

  function scanBody() {
    return (
      <>
        <div className="ln">
          <span className="prompt-sigil">$</span> <span className="cmd">npx</span>{' '}
          <span className="cmd-rest">saferskills scan</span>
        </div>
        <Banner />
        <div className="mt-pre">
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="ok">✓</span> Found <span className="num">144</span> capabilities across{' '}
            <span className="num">2</span> agents
            <span className="dim"> · 128 from plugins · 2 mcp_server · 125 skill · 4 hook · 13 plugin · bundle 10.5 MiB</span>
          </div>
          <div className="ln">
            <span className="warn">⚠</span>{' '}
            <span className="dim">Excluded 58 item(s) from the bundle: 56 binary, 1 nested archive, 1 vendor dir</span>
          </div>
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="label">SaferSkills · local audit</span>
          </div>
          <div className="ln">
            {'  '}
            <span className="green">●</span> <span className="green b">Green</span>
            {'  '}
            <span className="num">99</span>
            <span className="dim">/100</span>
            {'      '}
            <span className="dim">151 capabilities · 2 agents</span>
          </div>
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="label">Category breakdown</span> <span className="dim">(mean across capabilities)</span>
          </div>
          {CATS_CLEAN.map((c) => (
            <CategoryRow key={c.name} {...c} />
          ))}
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="label">Agents detected</span>
          </div>
          <div className="ln">
            {'  Claude Code    '}
            <span className="dim">~/.claude</span>
            {'    '}
            <span className="dim">143 capabilities</span>
          </div>
          <div className="ln">
            {'  Codex          '}
            <span className="dim">~/.codex</span>
            {'     '}
            <span className="dim">1 capability</span>
          </div>
          <div className="ln">
            {'  GitHub Copilot '}
            <span className="dim">~/.copilot</span>
            {'   '}
            <span className="muted">no capabilities found</span>
          </div>
          <div className="ln">
            {'  Gemini         '}
            <span className="dim">~/.gemini</span>
            {'    '}
            <span className="muted">no capabilities found</span>
          </div>
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="label">Capabilities</span> <span className="dim">(worst first)</span>
          </div>
          {WORST.map((w) => (
            <div className="ln" key={w.name}>
              {'  '}
              <span className={w.dot === 'y' ? 'yellow' : 'green'}>{w.dot === 'y' ? '◌' : '●'}</span>{' '}
              <span className={w.dot === 'y' ? 'yellow' : 'green'}>{w.tier.padEnd(7)}</span>
              <span className="num">{String(w.score).padEnd(4)}</span>
              <span className="dim">Skill</span>
              {'  '}
              {w.name.padEnd(24)}
              <span className={w.sev}>{w.sevTxt}</span>
              <span className="dim">{w.tail}</span>
            </div>
          ))}
          <div className="ln dim">{'  · 143 more — see the full report'}</div>
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="label">Most problematic findings</span>
          </div>
          <div className="ln">
            {'  '}
            <span className="red">▲ HIGH</span> Fenced code block that tells the agent to run a command
          </div>
          <div className="ln">
            {'         '}
            <span className="dim">SS-SKILL-INJECT-FENCED-RUN-01 · babysit-pr · </span>
            <span className="path">claude-code/skills/babysit-pr/SKILL.md</span>
            <span className="dim">:50</span>
          </div>
          <div className="ln">
            {'  '}
            <span className="red">▲ HIGH</span> Fenced code block that tells the agent to run a command
          </div>
          <div className="ln">
            {'         '}
            <span className="dim">SS-SKILL-INJECT-FENCED-RUN-01 · claude-api · </span>
            <span className="path">claude-code/plugins/…/claude-api/csharp/claude-api.md</span>
            <span className="dim">:7</span>
          </div>
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="label">Next</span>
            {'   '}
            <span className="dim">Review babysit-pr (high) before keeping it installed.</span>
          </div>
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="label">Report</span> <span className="dim">→</span>{' '}
            <span className="path">http://localhost:5173/scans/27d899e3-c009-4b19-9068-f3c401c1ffa4</span>
            <span className="caret" />
          </div>
        </div>
      </>
    )
  }

  function listBody() {
    return (
      <>
        <div className="ln">
          <span className="prompt-sigil">$</span> <span className="cmd">npx</span>{' '}
          <span className="cmd-rest">saferskills</span> <span className="arg">list</span>
        </div>
        <Banner />
        <div className="mt-pre">
          <div className="ln">&nbsp;</div>
          <div className="ln dim">
            {'NAME'.padEnd(24)}
            {'KIND'.padEnd(8)}
            {'AGENT'.padEnd(13)}
            {'SCORE'.padEnd(9)}
            {'STATUS'.padEnd(9)}
            {'WHEN'.padEnd(10)}
            {'PATH'}
          </div>
          {LIST_ROWS.map((r) => (
            <div className="ln" key={r.name + r.path}>
              <span className="b">{r.name.padEnd(24)}</span>
              <span className="dim">{r.kind.padEnd(8)}</span>
              <span className="dim">{r.agent.padEnd(13)}</span>
              <span className="num">{`${r.score}/100`.padEnd(9)}</span>
              <span className={tierClass(r.tier)}>{`● ${r.tier}`.padEnd(9)}</span>
              <span className="dim">{r.when.padEnd(10)}</span>
              <span className="path">{r.path}</span>
            </div>
          ))}
          <div className="ln dim">· 137 more</div>
          <div className="ln">
            <span className="caret" />
          </div>
        </div>
      </>
    )
  }

  function infoBody() {
    return (
      <>
        <div className="ln">
          <span className="prompt-sigil">$</span> <span className="cmd">npx</span>{' '}
          <span className="cmd-rest">saferskills</span> <span className="arg">info instrument-integration</span>
        </div>
        <Banner />
        <div className="mt-pre">
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="b">instrument-integration</span> <span className="dim">skill</span>
          </div>
          <div className="ln">
            {'  '}
            <span className="yellow">◌</span> <span className="yellow b">Yellow</span>
            {'  '}
            <span className="num">74</span>
            <span className="dim">/100</span>
          </div>
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="label">Category breakdown</span>
          </div>
          {CATS_FLAGGED.map((c) => (
            <CategoryRow key={c.name} {...c} />
          ))}
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="b">3 finding(s):</span>
          </div>
          {[
            { f: 'js.md', range: ':32-305' },
            { f: 'node.md', range: ':13-271' },
            { f: 'python.md', range: ':15-190' },
          ].map((x) => (
            <div key={x.f}>
              <div className="ln">
                {'  '}
                <span className="red">▲ HIGH</span> Fenced code block that tells the agent to run a command
              </div>
              <div className="ln">
                {'         '}
                <span className="dim">SS-SKILL-INJECT-FENCED-RUN-01 · </span>
                <span className="path">…/instrument-integration/references/{x.f}</span>
                <span className="dim">{x.range}</span>
              </div>
              <div className="ln dim">{'             ```bash'}</div>
            </div>
          ))}
          <div className="ln">&nbsp;</div>
          <div className="ln">
            <span className="label">Report:</span>{' '}
            <span className="path">http://localhost:8000/items/upload--39fd32d6--skill-instrument-integration</span>
            <span className="caret" />
          </div>
        </div>
      </>
    )
  }

  const bodies: Record<Verb, () => ReactNode> = {
    install: installBody,
    scan: scanBody,
    list: listBody,
    info: infoBody,
  }

  return (
    <div className="iw-window">
      <div className="iw-chrome">
        <span className="mac-traffic" aria-hidden="true">
          <span className="l-r" />
          <span className="l-y" />
          <span className="l-g" />
        </span>
        <div className="iw-title">{title[verb]}</div>
        <div className="copy-slot">
          <button
            type="button"
            className="mt-copy"
            onClick={onCopy}
            aria-label={`Copy command: ${command[verb]}`}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} aria-hidden="true">
              <rect x="8" y="8" width="13" height="13" rx="2" />
              <path d="M5 16V5a2 2 0 0 1 2-2h11" />
            </svg>
            Copy command
          </button>
        </div>
      </div>
      <div className="iw-grid">
        <div className="iw-side" role="group" aria-label="Install target agent">
          <div className="side-head">AGENTS · {agents.length}</div>
          {agents.map((a) => (
            <button
              type="button"
              key={a.id}
              aria-pressed={a.id === active}
              className={`iw-row ${a.id === active ? 'active' : ''}`.trim()}
              data-id={a.id}
              onClick={() => setActive(a.id)}
            >
              <span className="iw-mono" aria-hidden="true">{a.glyph}</span>
              <span className="iw-name">{a.name}</span>
              <span className="iw-sub">--to {a.id}</span>
            </button>
          ))}
        </div>
        <div className="iw-main">
          <div className="iw-journey" role="tablist" aria-label="CLI command">
            {VERBS.map((v, i) => (
              <span className="iw-step-wrap" key={v.id}>
                {i > 0 && (
                  <span className="iw-sep" aria-hidden="true">
                    ·
                  </span>
                )}
                <button
                  type="button"
                  role="tab"
                  id={`iw-step-${v.id}`}
                  aria-selected={v.id === verb}
                  aria-controls="iw-pane"
                  tabIndex={v.id === verb ? 0 : -1}
                  className={`iw-step ${v.id === verb ? 'active' : ''}`.trim()}
                  onClick={() => setVerb(v.id)}
                >
                  <span className="iw-step-glyph" aria-hidden="true">{v.glyph}</span>
                  {v.label}
                </button>
              </span>
            ))}
          </div>
          <div className="iw-bread">
            <span className="crumb">~</span>
            <span className="sep">/</span>
            <span className="crumb">saferskills</span>
            <span className="sep">/</span>
            {breadTail[verb]}
          </div>
          <div className="mt-body" role="tabpanel" id="iw-pane" aria-labelledby={`iw-step-${verb}`}>
            {bodies[verb]()}
          </div>
        </div>
      </div>
    </div>
  )
}
