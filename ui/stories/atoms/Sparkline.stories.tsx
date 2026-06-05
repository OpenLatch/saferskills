import type { Story } from '@ladle/react'
import Sparkline from '../../components/atoms/Sparkline'

const RISING = [0, 1, 1, 2, 3, 2, 4, 5, 4, 6, 8, 7, 9]
const SPIKY = [2, 0, 5, 1, 0, 8, 3, 0, 0, 6, 2, 9, 1]
const FLAT = new Array(13).fill(0)

export const Rising: Story = () => <Sparkline values={RISING} />
export const Spiky: Story = () => <Sparkline values={SPIKY} />
export const FlatEmpty: Story = () => <Sparkline values={FLAT} />
export const Placeholder: Story = () => <Sparkline values={[1, 1, 2, 2, 3, 3, 2, 2, 3, 4, 3, 4, 5]} placeholder />

export const InRow: Story = () => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
    <Sparkline values={RISING} />
    <Sparkline values={SPIKY} />
    <Sparkline values={[2, 2, 3, 2, 4, 3, 5, 4, 6, 5, 7, 6, 8]} placeholder />
    <Sparkline values={FLAT} />
  </div>
)
