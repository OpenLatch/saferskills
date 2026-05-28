import type { Story } from '@ladle/react'
import DetectorCard from '../../components/molecules/DetectorCard'

export const Running: Story = () => (
  <DetectorCard ruleId="SS-MCP-POISON-UNICODE-TAG-01" status="running" filePath="tools/manifest.json" elapsedMs={840} />
)

export const Completed: Story = () => (
  <DetectorCard ruleId="SS-HOOKS-RCE-CURL-PIPE-01" status="completed" filePath=".claude/hooks/SessionStart.sh" elapsedMs={120} />
)

export const Queued: Story = () => <DetectorCard ruleId="SS-SKILL-INJECT-FENCED-RUN-01" status="queued" />

export const Skipped: Story = () => (
  <DetectorCard ruleId="SS-SKILL-MAINTENANCE-COMMIT-RECENCY-01" status="skipped" />
)
