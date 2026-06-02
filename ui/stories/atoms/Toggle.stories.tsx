import type { Story } from '@ladle/react'
import { useState } from 'react'
import Toggle from '../../components/atoms/Toggle'

export const On: Story = () => {
  const [on, setOn] = useState(true)
  return <Toggle checked={on} onChange={setOn} label="Make results public" />
}

export const Off: Story = () => {
  const [on, setOn] = useState(false)
  return <Toggle checked={on} onChange={setOn} label="Make results public" />
}

export const OrangeTone: Story = () => {
  const [on, setOn] = useState(true)
  return <Toggle checked={on} onChange={setOn} label="Make results public" tone="orange" />
}

export const Compact: Story = () => {
  const [on, setOn] = useState(true)
  return <Toggle checked={on} onChange={setOn} label="Make results public" compact />
}

export const Disabled: Story = () => (
  <Toggle checked onChange={() => {}} label="Make results public" disabled />
)

export const WithHelper: Story = () => {
  const [on, setOn] = useState(true)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxWidth: 360 }}>
      <Toggle checked={on} onChange={setOn} label="Make results public" describedById="t-help" />
      <span id="t-help" style={{ fontFamily: 'monospace', fontSize: 10.5, color: '#64748B' }}>
        Private results are unlisted, link-only, and expire in 90 days.
      </span>
    </div>
  )
}
