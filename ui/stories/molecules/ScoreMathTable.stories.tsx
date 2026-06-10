import type { Story } from '@ladle/react'
import ScoreMathTable from '../../components/molecules/ScoreMathTable'

export const Capped: Story = () => (
  <div style={{ padding: 40, maxWidth: 520 }}>
    <ScoreMathTable
      base={100}
      modifiers={[
        { testId: 'AS-06', severity: 'critical', delta: -40, emphasized: true },
        { testId: 'AS-09', severity: 'high', delta: -25 },
        { testId: 'AS-17', severity: 'high', delta: -25 },
      ]}
      cap={{ label: 'Worst-finding cap', value: 15 }}
      finalScore={15}
    />
  </div>
)

export const NoCap: Story = () => (
  <div style={{ padding: 40, maxWidth: 520 }}>
    <ScoreMathTable
      base={100}
      modifiers={[
        { testId: 'AS-06', severity: 'critical', delta: -40, emphasized: true },
        { testId: 'AS-09', severity: 'high', delta: -25 },
        { testId: 'AS-17', severity: 'high', delta: -25 },
      ]}
      finalScore={10}
    />
  </div>
)
