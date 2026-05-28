import type { Story } from '@ladle/react'
import BandPill from '../../components/atoms/BandPill'

export const Green: Story = () => <BandPill tier="green" />
export const Yellow: Story = () => <BandPill tier="yellow" />
export const Orange: Story = () => <BandPill tier="orange" />
export const Red: Story = () => <BandPill tier="red" />
export const CustomLabel: Story = () => <BandPill tier="green" label="passed" />
export const Cluster: Story = () => (
  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
    <BandPill tier="green" />
    <BandPill tier="yellow" />
    <BandPill tier="orange" />
    <BandPill tier="red" />
  </div>
)
