import type { Story } from '@ladle/react'
import AgentMarquee from '../../components/molecules/AgentMarquee'

export const Default: Story = () => <AgentMarquee />
export const Subset: Story = () => (
  <AgentMarquee
    agents={[
      { id: 'claude-code', name: 'Claude Code', glyph: 'CC' },
      { id: 'cursor', name: 'Cursor', glyph: 'C' },
      { id: 'codex-cli', name: 'Codex CLI', glyph: '><' },
    ]}
  />
)
