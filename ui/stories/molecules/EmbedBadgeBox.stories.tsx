import type { Story } from '@ladle/react'
import EmbedBadgeBox from '../../components/molecules/EmbedBadgeBox'

export const Default: Story = () => (
  <EmbedBadgeBox
    scanId="018e7c8b-9999-7000-8000-000000000001"
    score={87}
    tier="green"
    slug="anthropics--skills"
  />
)

export const Red: Story = () => (
  <EmbedBadgeBox
    scanId="018e7c8b-9999-7000-8000-000000000099"
    score={32}
    tier="red"
    slug="acme--bad-skill"
  />
)
