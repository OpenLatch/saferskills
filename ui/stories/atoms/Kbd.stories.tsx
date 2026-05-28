import type { Story } from '@ladle/react'
import Kbd from '../../components/atoms/Kbd'

export const CommandK: Story = () => <Kbd>⌘K</Kbd>
export const CtrlK: Story = () => <Kbd>Ctrl+K</Kbd>
export const SingleKey: Story = () => <Kbd>/</Kbd>
export const Cluster: Story = () => (
  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
    <Kbd>⌘K</Kbd>
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>or</span>
    <Kbd>Ctrl+K</Kbd>
  </div>
)
