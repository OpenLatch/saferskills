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

/** I-5.7 §2a two-line hero: each `baseLines` entry is its own block line; the
 *  last line carries the rotator inline. */
export const TwoLines: Story = () => (
  <RotatingHeadline
    baseLines={['Audit every capability.', 'Scan the whole agent against']}
    nouns={NOUNS}
    trailing="."
    cycleMs={2600}
  />
)
