import type { Story } from '@ladle/react'
import CapCallout from '../../components/atoms/CapCallout'

export const CappedRed: Story = () => (
  <div className="score-cell r" style={{ padding: 40, maxWidth: 520 }}>
    <CapCallout
      band="red"
      text="Capped to Red — 1 critical finding; the worst-finding cap overrides the weighted average"
    />
  </div>
)

export const CleanGreen: Story = () => (
  <div className="score-cell g" style={{ padding: 40, maxWidth: 520 }}>
    <CapCallout band="green" text="No cap applied — no critical or high findings observed." />
  </div>
)
