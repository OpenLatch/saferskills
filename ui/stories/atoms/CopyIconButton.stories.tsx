import type { Story } from '@ladle/react'
import CopyIconButton from '../../components/atoms/CopyIconButton'

export const Default: Story = () => (
  <span style={{ fontFamily: 'monospace', display: 'inline-flex', alignItems: 'center' }}>
    SHA-256 d81c…095c
    <CopyIconButton value="d81cf1fcc5990a7b3c2d1e5f4a7b3c2d1e5f4a7b3c2d1e5f4a7b3c2d1e5f4095c" label="Copy SHA-256" />
  </span>
)

export const NextToScanId: Story = () => (
  <span style={{ fontFamily: 'monospace', display: 'inline-flex', alignItems: 'center' }}>
    scn_4bf8915066d4
    <CopyIconButton value="scn_4bf8915066d4" label="Copy scan id" />
  </span>
)
