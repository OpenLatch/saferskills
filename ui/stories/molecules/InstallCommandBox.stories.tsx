import type { Story } from '@ladle/react'
import InstallCommandBox from '../../components/molecules/InstallCommandBox'

export const Default: Story = () => <InstallCommandBox slug="anthropics--skills" />

export const WithAgentLabel: Story = () => (
  <InstallCommandBox slug="acme--linear-mcp" agentLabel="Claude Code" />
)
