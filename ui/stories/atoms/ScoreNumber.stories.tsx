import type { Story } from '@ladle/react'
import ScoreNumber from '../../components/atoms/ScoreNumber'

export const Hero: Story = () => <ScoreNumber value={87} size="hero" />
export const Large: Story = () => <ScoreNumber value={42} size="lg" />
export const Medium: Story = () => <ScoreNumber value={94} size="md" />
export const Small: Story = () => <ScoreNumber value={66} size="sm" />
export const CustomMax: Story = () => <ScoreNumber value={47} max={50} size="md" />
export const ScoreScale: Story = () => (
  <div style={{ display: 'flex', gap: 32, alignItems: 'baseline' }}>
    <ScoreNumber value={95} size="hero" />
    <ScoreNumber value={72} size="hero" />
    <ScoreNumber value={48} size="hero" />
    <ScoreNumber value={29} size="hero" />
  </div>
)
