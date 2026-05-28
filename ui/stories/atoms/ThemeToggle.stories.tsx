import type { Story } from '@ladle/react'
import ThemeToggle from '../../components/atoms/ThemeToggle'

export const Default: Story = () => (
  <div style={{ padding: 16, background: '#0F172A' }}>
    <ThemeToggle />
  </div>
)

export const OnPaper: Story = () => (
  <div style={{ padding: 16, background: '#F8FAFC', border: '1px solid #CBD5E1' }}>
    <ThemeToggle />
  </div>
)
