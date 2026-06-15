import type { Story } from '@ladle/react'
import CorpusRiskMeter from '../../components/molecules/CorpusRiskMeter'

export const Published: Story = () => (
  <div style={{ padding: 40, maxWidth: 520 }}>
    <CorpusRiskMeter
      pctWithCritical={41}
      gateMet
      corpusCount={812}
      gateTarget={500}
      packTestCount={17}
    />
  </div>
)

/** Below the gate: the full-width methodology instrument (no published rate). */
export const Collecting: Story = () => (
  <div style={{ padding: 40, maxWidth: 920 }}>
    <CorpusRiskMeter
      pctWithCritical={null}
      gateMet={false}
      corpusCount={134}
      gateTarget={500}
      packTestCount={17}
    />
  </div>
)
