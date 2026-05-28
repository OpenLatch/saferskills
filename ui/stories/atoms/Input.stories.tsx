import type { Story } from '@ladle/react'
import Input from '../../components/atoms/Input'

export const Default: Story = () => (
  <div style={{ maxWidth: 480 }}>
    <Input placeholder="Search the catalog…" aria-label="Search" />
  </div>
)

export const WithPrefix: Story = () => (
  <div style={{ maxWidth: 480 }}>
    <Input prefix="github.com/" placeholder="org/repo" aria-label="Repository URL" />
  </div>
)

export const Focused: Story = () => (
  <div style={{ maxWidth: 480 }}>
    <Input
      prefix="⌘K"
      placeholder="Search 12,847 indexed skills"
      autoFocus
      aria-label="Catalog search"
    />
  </div>
)
