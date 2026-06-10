import type { Story } from '@ladle/react'
import StalePackBanner from '../../components/atoms/StalePackBanner'

export const Default: Story = () => (
  <div style={{ padding: 40, maxWidth: 720 }}>
    <StalePackBanner text="pack v2026.07.01 adds a test for your family — re-scan" />
  </div>
)
