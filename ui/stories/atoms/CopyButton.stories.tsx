import type { Story } from '@ladle/react'
import CopyButton from '../../components/atoms/CopyButton'
import Toast from '../../components/atoms/Toast'

export const Default: Story = () => (
  <>
    <CopyButton value="npx saferskills install github-mcp" />
    <Toast />
  </>
)

export const Primary: Story = () => (
  <>
    <CopyButton value="https://saferskills.ai/scans/abc123" variant="primary" label="Copy link" />
    <Toast />
  </>
)

export const Inline: Story = () => (
  <>
    <code style={{ fontFamily: 'monospace' }}>npx saferskills install github-mcp</code>
    <span style={{ marginLeft: 12 }}>
      <CopyButton value="npx saferskills install github-mcp" size="sm" />
    </span>
    <Toast />
  </>
)
