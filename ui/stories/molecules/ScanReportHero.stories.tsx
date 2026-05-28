import type { Story } from '@ladle/react'
import ScanReportHero from '../../components/molecules/ScanReportHero'

const subScores = [
  { label: 'Security', key: 'security', value: 78, weight: 35 },
  { label: 'Supply chain', key: 'supply_chain', value: 92, weight: 20 },
  { label: 'Maintenance', key: 'maintenance', value: 80, weight: 15 },
  { label: 'Transparency', key: 'transparency', value: 70, weight: 15 },
  { label: 'Community', key: 'community', value: 88, weight: 15 },
]

export const Green: Story = () => <ScanReportHero score={87} tier="green" subScores={subScores} />

export const Yellow: Story = () => <ScanReportHero score={72} tier="yellow" subScores={subScores} />

export const Red: Story = () => (
  <ScanReportHero
    score={32}
    tier="red"
    subScores={[
      { label: 'Security', key: 'security', value: 40, weight: 35, criticalFloorApplied: true },
      ...subScores.slice(1),
    ]}
  />
)
