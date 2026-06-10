import type { Story } from '@ladle/react'
import RuntimeMonogram, { RUNTIME_IDS } from '../../components/atoms/RuntimeMonogram'

export const AllRuntimes: Story = () => (
  <div style={{ display: 'grid', gap: 10, padding: 40 }}>
    {RUNTIME_IDS.map((id) => (
      <RuntimeMonogram key={id} runtime={id} showName />
    ))}
  </div>
)

export const MonogramOnly: Story = () => (
  <div style={{ display: 'flex', gap: 10, padding: 40 }}>
    {RUNTIME_IDS.map((id) => (
      <RuntimeMonogram key={id} runtime={id} />
    ))}
  </div>
)
