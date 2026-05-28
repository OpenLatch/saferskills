import type { Story } from '@ladle/react'
import BracketLabel from '../../components/atoms/BracketLabel'

export const Default: Story = () => <BracketLabel>section · 03</BracketLabel>
export const Cluster: Story = () => (
  <div style={{ display: 'flex', gap: 24 }}>
    <BracketLabel>plan</BracketLabel>
    <BracketLabel>scope</BracketLabel>
    <BracketLabel>section · 03</BracketLabel>
  </div>
)
