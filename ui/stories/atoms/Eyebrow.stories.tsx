import type { Story } from '@ladle/react'
import Eyebrow from '../../components/atoms/Eyebrow'

export const Default: Story = () => <Eyebrow>FEEDS · 04</Eyebrow>
export const NoRule: Story = () => <Eyebrow withRule={false}>methodology · open source</Eyebrow>
export const Stack: Story = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
    <Eyebrow>SCORES · 5 SUB-CATEGORIES</Eyebrow>
    <Eyebrow>AGENTS · 8 SUPPORTED</Eyebrow>
    <Eyebrow>METHODOLOGY · OPEN SOURCE</Eyebrow>
  </div>
)
