import type { Story } from '@ladle/react'
import GhStar from '../../components/atoms/GhStar'

export const Default: Story = () => <GhStar count={26908} />
export const Small: Story = () => <GhStar repo="OpenLatch/saferskills" count={847} />
export const Million: Story = () => <GhStar repo="OpenLatch/saferskills" count={1247000} />
