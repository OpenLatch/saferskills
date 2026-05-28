import type { Story } from '@ladle/react'
import InstallTabs from '../../components/molecules/InstallTabs'
import Toast from '../../components/atoms/Toast'

export const Default: Story = () => (
  <>
    <InstallTabs scanSlug="github-mcp" />
    <Toast />
  </>
)

export const Cursor: Story = () => (
  <>
    <InstallTabs scanSlug="linear-mcp" defaultAgent="cursor" />
    <Toast />
  </>
)
