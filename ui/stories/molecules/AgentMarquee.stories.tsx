import type { Story } from '@ladle/react'
import AgentMarquee from '../../components/molecules/AgentMarquee'

export const Default: Story = () => <AgentMarquee />

export const Subset: Story = () => (
  <AgentMarquee
    agents={[
      { id: 'claude-code', name: 'Claude Code' },
      { id: 'cursor', name: 'Cursor' },
      { id: 'codex', name: 'Codex CLI' },
    ]}
  />
)

export const FallbackInitials: Story = () => (
  <AgentMarquee
    agents={[
      { id: 'claude-code', name: 'Claude Code' },
      { id: 'unknown-agent', name: 'Mystery Agent', glyph: 'MA' },
    ]}
  />
)

export const Dark: Story = () => (
  <div className="dark" style={{ background: 'var(--color-paper-deep)', padding: '24px 0' }}>
    <AgentMarquee />
  </div>
)
