import type { Story } from '@ladle/react'
import DotStrip from '../../components/atoms/DotStrip'

export const Green: Story = () => <DotStrip value={87} tier="green" />
export const Yellow: Story = () => <DotStrip value={72} tier="yellow" />
export const Orange: Story = () => <DotStrip value={48} tier="orange" />
export const Red: Story = () => <DotStrip value={29} tier="red" />
export const FullRange: Story = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
    <DotStrip value={100} tier="green" />
    <DotStrip value={80} tier="green" />
    <DotStrip value={60} tier="yellow" />
    <DotStrip value={40} tier="orange" />
    <DotStrip value={20} tier="red" />
    <DotStrip value={0} tier="red" />
  </div>
)
