import type { Story } from '@ladle/react'
import CtaBand from '../../components/molecules/CtaBand'

export const Default: Story = () => (
  <CtaBand
    title="Scan a repo. Read the report. Decide."
    lead="Free. No account. Methodology is open source. Every verdict is appealable."
    primaryAction={{ label: 'Scan a repo', href: '/scan' }}
    secondaryAction={{ label: 'Read methodology', href: '/methodology' }}
  />
)

export const NoLead: Story = () => (
  <CtaBand
    title="One catalog. One install command. Eight agents."
    primaryAction={{ label: 'Browse catalog', href: '/catalog' }}
  />
)
