import type { Story } from '@ladle/react'
import Button from '../../components/atoms/Button'
import ButtonPair from '../../components/atoms/ButtonPair'

export const Default: Story = () => (
  <ButtonPair>
    <Button variant="primary">Scan a repo</Button>
    <Button variant="paper">Browse catalog</Button>
  </ButtonPair>
)

export const Reversed: Story = () => (
  <ButtonPair>
    <Button variant="dark">Read methodology</Button>
    <Button variant="primary">Get started</Button>
  </ButtonPair>
)
