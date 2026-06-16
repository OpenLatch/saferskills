import type { Story } from '@ladle/react'
import { useState } from 'react'
import MultiSelect from '../../components/molecules/MultiSelect'

const OPTIONS = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'info', label: 'Info' },
  { value: 'no-findings', label: 'No findings' },
]

export const Default: Story = () => {
  const [selected, setSelected] = useState<string[]>(['critical'])
  return (
    <div style={{ padding: 40 }}>
      <MultiSelect
        label="Findings"
        allLabel="Any"
        ariaLabel="Filter by findings severity"
        options={OPTIONS}
        selected={selected}
        onChange={setSelected}
      />
    </div>
  )
}
