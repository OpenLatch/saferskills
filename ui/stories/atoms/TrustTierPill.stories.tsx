import type { Story } from '@ladle/react'
import TrustTierPill from '../../components/atoms/TrustTierPill'

export const Launch: Story = () => (
  <div style={{ padding: 80 }}>
    <TrustTierPill labels={['cloud-validated', 'client-administered']} />
  </div>
)
