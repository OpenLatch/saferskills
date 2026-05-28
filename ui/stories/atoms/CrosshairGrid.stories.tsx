import type { Story } from '@ladle/react'
import type { ReactNode } from 'react'
import CrosshairGrid from '../../components/atoms/CrosshairGrid'

const Frame = ({ children }: { children: ReactNode }) => (
  <div
    style={{
      position: 'relative',
      width: '100%',
      height: 480,
      background: 'var(--color-paper)',
      overflow: 'hidden',
    }}
  >
    {children}
  </div>
)

export const Default: Story = () => (
  <Frame>
    <CrosshairGrid />
  </Frame>
)

export const Dense: Story = () => (
  <Frame>
    <CrosshairGrid spacing={32} />
  </Frame>
)

export const StrongerPush: Story = () => (
  <Frame>
    <CrosshairGrid pushMax={20} pushRadius={220} />
  </Frame>
)
