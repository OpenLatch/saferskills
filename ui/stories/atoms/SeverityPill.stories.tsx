import type { Story } from '@ladle/react'
import SeverityPill from '../../components/atoms/SeverityPill'

export const Critical: Story = () => <SeverityPill severity="critical" />
export const High: Story = () => <SeverityPill severity="high" />
export const Medium: Story = () => <SeverityPill severity="medium" />
export const Low: Story = () => <SeverityPill severity="low" />
export const Info: Story = () => <SeverityPill severity="info" />
export const CustomLabel: Story = () => <SeverityPill severity="high" label="HIGH RISK" />
export const Ladder: Story = () => (
  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
    <SeverityPill severity="critical" />
    <SeverityPill severity="high" />
    <SeverityPill severity="medium" />
    <SeverityPill severity="low" />
    <SeverityPill severity="info" />
  </div>
)
