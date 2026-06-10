import type { Story } from '@ladle/react'
import DossierCard from '../../components/molecules/DossierCard'

const EMPTY_TALLY = { skill: 0, hook: 0, mcp: 0, plugin: 0, rules: 0 }

export const Critical: Story = () => (
  <div style={{ padding: 40, maxWidth: 340 }}>
    <DossierCard
      agentName="acme-coding-agent"
      runtime="claude-code"
      score={34}
      band="red"
      scannedAt="2026-06-09T12:00:00Z"
      capabilityTally={{ ...EMPTY_TALLY, skill: 2, mcp: 1 }}
      findings={{ critical: 1, high: 2, info: 0, total: 3 }}
      trustTier="cloud-validated"
      href="/agents/demo"
      isNewest
    />
  </div>
)

export const Clean: Story = () => (
  <div style={{ padding: 40, maxWidth: 340 }}>
    <DossierCard
      agentName="safe-agent"
      runtime="cursor"
      score={92}
      band="green"
      scannedAt="2026-06-08T12:00:00Z"
      capabilityTally={EMPTY_TALLY}
      findings={{ critical: 0, high: 0, info: 0, total: 0 }}
      trustTier="cloud-validated"
      href="/agents/demo2"
    />
  </div>
)
