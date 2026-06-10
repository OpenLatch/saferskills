import type { Story } from '@ladle/react'
import AgentVerb, { type AgentVerbBand } from '../../components/atoms/AgentVerb'

const BANDS: { band: AgentVerbBand; cell: string }[] = [
  { band: 'green', cell: 'g' },
  { band: 'yellow', cell: 'y' },
  { band: 'orange', cell: 'o' },
  { band: 'red', cell: 'r' },
]

export const AllBands: Story = () => (
  <div style={{ display: 'grid', gap: 12, padding: 40 }}>
    {BANDS.map(({ band, cell }) => (
      <div key={band} className={`score-cell ${cell}`}>
        <AgentVerb band={band} />
      </div>
    ))}
  </div>
)
