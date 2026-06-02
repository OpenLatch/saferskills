import type { Story } from '@ladle/react'
import RotatingHeadline from '../../components/atoms/RotatingHeadline'

const NOUNS = ['Secrets Leaks', 'Prompt Injection', 'Supply-Chain Attacks', 'Tool Poisoning']

export const Default: Story = () => (
  <RotatingHeadline
    base="Every AI capability, independently audited against"
    nouns={NOUNS}
  />
)

export const Fast: Story = () => (
  <RotatingHeadline
    base="Every AI capability, audited against"
    nouns={NOUNS}
    cycleMs={1500}
  />
)

export const Single: Story = () => (
  <RotatingHeadline
    base="Every AI capability, audited against"
    nouns={['Prompt Injection']}
  />
)
