import type { Story } from '@ladle/react'
import { useState } from 'react'
import AgentFilterBar, {
  type AgentFilters,
  DEFAULT_AGENT_FILTERS,
} from '../../components/molecules/AgentFilterBar'

export const Default: Story = () => {
  const [filters, setFilters] = useState<AgentFilters>(DEFAULT_AGENT_FILTERS)
  return (
    <div style={{ padding: 40 }}>
      <AgentFilterBar value={filters} onChange={(patch) => setFilters((f) => ({ ...f, ...patch }))} />
    </div>
  )
}
