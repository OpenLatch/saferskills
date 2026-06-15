import type { Story } from '@ladle/react'
import AgentCleanVerdict from '../../components/molecules/AgentCleanVerdict'

export const Default: Story = () => (
  <div style={{ padding: 40, maxWidth: 820 }}>
    <AgentCleanVerdict
      testsPassed={20}
      totalTests={20}
      familiesProbed={18}
      packLabel="saferskills-agent-baseline @ 2026.06.09"
    />
  </div>
)

export const SmallPack: Story = () => (
  <div style={{ padding: 40, maxWidth: 820 }}>
    <AgentCleanVerdict
      testsPassed={8}
      totalTests={8}
      familiesProbed={7}
      packLabel="saferskills-agent-baseline @ 2026.06.09"
    />
  </div>
)
