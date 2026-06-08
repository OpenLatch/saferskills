import type { Story } from '@ladle/react'
import InstallTabs from '../../components/molecules/InstallTabs'
import Toast from '../../components/atoms/Toast'

export const Default: Story = () => (
  <>
    <InstallTabs scanSlug="github-mcp" />
    <Toast />
  </>
)

export const ScanLocalAudit: Story = () => (
  <>
    <InstallTabs scanSlug="github-mcp" defaultVerb="scan" />
    <Toast />
  </>
)

export const ListInventory: Story = () => (
  <>
    <InstallTabs scanSlug="github-mcp" defaultVerb="list" />
    <Toast />
  </>
)

export const InfoReport: Story = () => (
  <>
    <InstallTabs scanSlug="github-mcp" defaultVerb="info" />
    <Toast />
  </>
)

export const Cursor: Story = () => (
  <>
    <InstallTabs scanSlug="linear-mcp" defaultAgent="cursor" />
    <Toast />
  </>
)
