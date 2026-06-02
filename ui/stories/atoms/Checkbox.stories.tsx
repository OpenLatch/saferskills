import type { Story } from '@ladle/react'
import { useState } from 'react'
import Checkbox from '../../components/atoms/Checkbox'

export const Checked: Story = () => {
  const [on, setOn] = useState(true)
  return <Checkbox checked={on} onChange={setOn} label="Trigger an immediate re-scan" />
}

export const Unchecked: Story = () => {
  const [on, setOn] = useState(false)
  return <Checkbox checked={on} onChange={setOn} label="Trigger an immediate re-scan" />
}

export const Radio: Story = () => {
  const [on, setOn] = useState(true)
  return <Checkbox variant="radio" checked={on} onChange={setOn} label="All sources" />
}

export const FilterRowWithCount: Story = () => {
  const [on, setOn] = useState(true)
  return (
    <div style={{ width: 240 }}>
      <Checkbox block checked={on} onChange={setOn} label="Skill" count={10} />
    </div>
  )
}

export const WithAdornment: Story = () => {
  const [on, setOn] = useState(true)
  return (
    <div style={{ width: 240 }}>
      <Checkbox
        block
        checked={on}
        onChange={setOn}
        label="80–100 · Green"
        count={16}
        adornment={
          <span
            aria-hidden="true"
            style={{ width: 10, height: 10, background: 'var(--score-green)' }}
          />
        }
      />
    </div>
  )
}
