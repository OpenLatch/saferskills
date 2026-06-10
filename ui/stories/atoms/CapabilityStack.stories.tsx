import type { Story } from '@ladle/react'
import CapabilityStack from '../../components/atoms/CapabilityStack'

export const Mixed: Story = () => (
  <div style={{ padding: 40 }}>
    <CapabilityStack tally={{ skill: 2, mcp: 1, hook: 0, plugin: 1, rules: 0 }} />
  </div>
)

export const Empty: Story = () => (
  <div style={{ padding: 40 }}>
    {/* renders nothing — the data-starved launch state */}
    <CapabilityStack tally={{ skill: 0, mcp: 0, hook: 0, plugin: 0, rules: 0 }} />
    <span>(nothing above)</span>
  </div>
)
