import type { Story } from '@ladle/react'
import CorpusRiskMeter from '../../components/molecules/CorpusRiskMeter'

export const Published: Story = () => (
  <div style={{ padding: 40, maxWidth: 520 }}>
    <CorpusRiskMeter pctWithCritical={41} gateMet corpusCount={812} gateTarget={500} />
  </div>
)

export const Collecting: Story = () => (
  <div style={{ padding: 40, maxWidth: 520 }}>
    <CorpusRiskMeter pctWithCritical={null} gateMet={false} corpusCount={134} gateTarget={500} />
  </div>
)
