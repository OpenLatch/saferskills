import type { Story } from '@ladle/react'
import Badge from '../../components/atoms/Badge'

export const Default: Story = () => <Badge>INDEXED</Badge>
export const Live: Story = () => <Badge variant="live">LIVE</Badge>
export const Cluster: Story = () => (
  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
    <Badge variant="live">LIVE · INDEXING</Badge>
    <Badge>TOP 50</Badge>
    <Badge>NEW</Badge>
  </div>
)
