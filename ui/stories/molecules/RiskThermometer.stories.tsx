import type { Story } from '@ladle/react'
import RiskThermometer from '../../components/molecules/RiskThermometer'

export const Populated: Story = () => (
  <div style={{ padding: 40, maxWidth: 560 }}>
    <RiskThermometer
      windowLabel="Whole corpus · Last 3 months"
      corpusCount={812}
      distribution={{
        red: { pct: 41, count: 333 },
        orange: { pct: 19, count: 154 },
        yellow: { pct: 22, count: 179 },
        green: { pct: 18, count: 146 },
      }}
    />
  </div>
)
