import type { Story } from '@ladle/react'
import { useState } from 'react'
import Select from '../../components/atoms/Select'

const SORT_OPTIONS = [
  { value: 'most_installed', label: 'Most installed' },
  { value: 'recent', label: 'Recently updated' },
  { value: 'highest_score', label: 'Highest score' },
  { value: 'lowest_score', label: 'Lowest score' },
  { value: 'most_starred', label: 'Most starred' },
]

export const Default: Story = () => {
  const [value, setValue] = useState('most_installed')
  return (
    <div style={{ padding: 80 }}>
      <Select value={value} options={SORT_OPTIONS} onChange={setValue} ariaLabel="Sort catalog" />
    </div>
  )
}

export const SecondSelected: Story = () => {
  const [value, setValue] = useState('highest_score')
  return (
    <div style={{ padding: 80 }}>
      <Select value={value} options={SORT_OPTIONS} onChange={setValue} ariaLabel="Sort catalog" />
    </div>
  )
}
