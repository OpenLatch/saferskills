import { useId, useRef, useState } from 'react'

/**
 * Per-agent install-path tabs for the docs — replaces the Starlight
 * `<Tabs syncKey="agent">` in `install-a-skill.mdx`. Reuses the
 * design-system `.seg`/`.seg-tab` segmented-tablist look + a roving-tabindex
 * keyboard model (←/→/Home/End). Local state only — the Starlight cross-page
 * `syncKey` sync is dropped (single-page benefit, needed a shared store).
 */
interface Agent {
  id: string
  name: string
  installPath: string
  configPath: string
}

export default function AgentTabs({ agents }: { agents: Agent[] }) {
  const [active, setActive] = useState(0)
  const base = useId()
  const tabs = useRef<(HTMLButtonElement | null)[]>([])

  const move = (next: number) => {
    const i = (next + agents.length) % agents.length
    setActive(i)
    tabs.current[i]?.focus()
  }
  const onKeyDown = (e: React.KeyboardEvent) => {
    const delta: Record<string, number> = {
      ArrowRight: active + 1,
      ArrowLeft: active - 1,
      Home: 0,
      End: agents.length - 1,
    }
    if (e.key in delta) {
      e.preventDefault()
      move(delta[e.key])
    }
  }

  const agent = agents[active]
  return (
    <div className="agent-tabs">
      <div className="seg" role="tablist" aria-label="Agent" onKeyDown={onKeyDown}>
        {agents.map((a, i) => (
          <button
            key={a.id}
            ref={(el) => {
              tabs.current[i] = el
            }}
            type="button"
            role="tab"
            id={`${base}-tab-${a.id}`}
            aria-selected={i === active}
            aria-controls={`${base}-panel`}
            tabIndex={i === active ? 0 : -1}
            className={`seg-tab${i === active ? ' on' : ''}`}
            onClick={() => setActive(i)}
          >
            {a.name}
          </button>
        ))}
      </div>
      <div
        className="agent-tabs-panel"
        role="tabpanel"
        id={`${base}-panel`}
        aria-labelledby={`${base}-tab-${agent.id}`}
      >
        Install path: <code>{agent.installPath}</code> · config: <code>{agent.configPath}</code>.
        After the score gate passes, the CLI writes the capability to this path; run{' '}
        <code>npx saferskills list</code> to confirm it landed.
      </div>
    </div>
  )
}
