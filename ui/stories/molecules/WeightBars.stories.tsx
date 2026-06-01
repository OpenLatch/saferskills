import type { Story } from '@ladle/react'
import WeightBars from '../../components/molecules/WeightBars'

/**
 * WeightBars — the shared "how it's weighted" sub-score visual (scan preview +
 * methodology formula panel). Framed by default; pass `framed={false}` to drop
 * the outer hairline when nesting inside an existing panel.
 */

const ROWS = [
  { label: 'Security', weight: 35, rules: 'SS-MCP-POISON-UNICODE-TAG-01 · SS-HOOKS-RCE-CURL-PIPE-01' },
  { label: 'Supply chain', weight: 20, rules: 'SS-MCP-SUPPLY-CHAIN-TYPOSQUAT-01' },
  { label: 'Maintenance', weight: 15, rules: 'SS-SKILL-MAINTENANCE-COMMIT-RECENCY-01' },
  { label: 'Transparency', weight: 15, rules: 'SS-RULES-TRANSPARENCY-MANIFEST-01' },
  { label: 'Community', weight: 15, rules: 'SS-SKILL-COMMUNITY-STARS-01' },
]

export const Framed: Story = () => (
  <div style={{ maxWidth: 560 }}>
    <WeightBars rows={ROWS} />
  </div>
)

export const Bare: Story = () => (
  <div style={{ maxWidth: 560, border: '1px solid var(--color-ink)', padding: 22 }}>
    <WeightBars rows={ROWS} framed={false} />
  </div>
)

export const NoSubLabels: Story = () => (
  <div style={{ maxWidth: 420 }}>
    <WeightBars rows={ROWS.map(({ label, weight }) => ({ label, weight }))} />
  </div>
)
