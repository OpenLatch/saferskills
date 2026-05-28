import type { Story } from '@ladle/react'
import Button from '../../components/atoms/Button'

export const Default: Story = () => <Button>Default</Button>
export const Primary: Story = () => <Button variant="primary">Scan a repo</Button>
export const Paper: Story = () => <Button variant="paper">Methodology</Button>
export const Dark: Story = () => <Button variant="dark">Dark</Button>
export const Ghost: Story = () => <Button variant="ghost">Ghost link</Button>
export const Small: Story = () => <Button size="sm" variant="primary">Small</Button>
export const Large: Story = () => <Button size="lg" variant="primary">Scan a repo</Button>
export const Anchor: Story = () => (
  <Button as="a" href="/catalog" variant="primary">
    Browse catalog
  </Button>
)
export const AllVariants: Story = () => (
  <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
    <Button>Default</Button>
    <Button variant="primary">Primary</Button>
    <Button variant="paper">Paper</Button>
    <Button variant="dark">Dark</Button>
    <Button variant="ghost">Ghost</Button>
  </div>
)
