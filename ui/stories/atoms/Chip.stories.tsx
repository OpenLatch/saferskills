import type { Story } from '@ladle/react'
import Chip from '../../components/atoms/Chip'

export const Default: Story = () => <Chip>mcp</Chip>
export const Green: Story = () => <Chip variant="g">≥80</Chip>
export const Yellow: Story = () => <Chip variant="y">60-79</Chip>
export const Orange: Story = () => <Chip variant="o">40-59</Chip>
export const Red: Story = () => <Chip variant="r">&lt;40</Chip>
export const Cluster: Story = () => (
  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
    <Chip variant="g">scan tier</Chip>
    <Chip>skill</Chip>
    <Chip>mcp_server</Chip>
    <Chip variant="o">deepscan</Chip>
  </div>
)
