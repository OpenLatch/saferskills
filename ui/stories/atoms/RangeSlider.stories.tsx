import type { Story } from '@ladle/react'
import { useState } from 'react'
import RangeSlider from '../../components/atoms/RangeSlider'

function Frame({ initialMin = 40, initialMax = 90 }: { initialMin?: number; initialMax?: number }) {
  const [range, setRange] = useState<[number, number]>([initialMin, initialMax])
  return (
    <div style={{ width: 280, padding: 40 }}>
      {/* Mirrors the catalog wrapper the consumer keeps. */}
      <div className="grp">
        <h6>Score range</h6>
        <RangeSlider
          min={range[0]}
          max={range[1]}
          onChange={(lo, hi) => setRange([lo, hi])}
          minAriaLabel="Minimum score"
          maxAriaLabel="Maximum score"
        />
      </div>
    </div>
  )
}

export const Default: Story = () => <Frame />
export const FullRange: Story = () => <Frame initialMin={0} initialMax={100} />
export const NarrowBand: Story = () => <Frame initialMin={70} initialMax={75} />
